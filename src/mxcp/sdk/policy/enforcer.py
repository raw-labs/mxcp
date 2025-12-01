"""Policy enforcement engine for MXCP SDK.

This module provides the core policy enforcement logic without any
configuration parsing or loading functionality.
"""

import logging
from typing import TYPE_CHECKING, Any, Optional

import celpy
from celpy.adapter import json_to_cel

from mxcp.sdk.telemetry import record_counter, traced_operation

from .models import PolicyAction, PolicyEnforcementError, PolicySetModel

if TYPE_CHECKING:
    from mxcp.sdk.auth import UserContextModel

logger = logging.getLogger(__name__)


class PolicyEnforcer:
    """Enforces policies on endpoint execution.

    This class provides the core policy enforcement logic for input validation
    and output filtering based on CEL (Common Expression Language) conditions.

    Example usage:
        >>> from mxcp.sdk.policy import PolicyEnforcer, PolicySetModel, PolicyDefinitionModel, PolicyAction
        >>> from mxcp.sdk.auth import UserContextModel
        >>>
        >>> # Create a policy set
        >>> policy_set = PolicySetModel(
        ...     input_policies=[
        ...         PolicyDefinitionModel(
        ...             condition='user.role != "admin"',
        ...             action=PolicyAction.DENY,
        ...             reason="Admin access required"
        ...         )
        ...     ],
        ...     output_policies=[
        ...         PolicyDefinitionModel(
        ...             condition='user.role == "guest"',
        ...             action=PolicyAction.FILTER_FIELDS,
        ...             fields=["sensitive_data", "internal_id"]
        ...         )
        ...     ]
        ... )
        >>>
        >>> # Create enforcer
        >>> enforcer = PolicyEnforcer(policy_set)
        >>>
        >>> # Create user context (role is extracted from raw_profile)
        >>> user_context = UserContextModel(
        ...     provider="example", user_id="john-123", username="john",
        ...     raw_profile={"role": "guest"}
        ... )
        >>>
        >>> # Enforce input policies
        >>> enforcer.enforce_input_policies(user_context, {"param1": "value1"})
        >>>
        >>> # Enforce output policies
        >>> output = {"data": "public", "sensitive_data": "secret"}
        >>> filtered_output, action = enforcer.enforce_output_policies(user_context, output)
    """

    def __init__(self, policy_set: PolicySetModel):
        """Initialize the policy enforcer.

        Args:
            policy_set: The set of policies to enforce
        """
        self.policy_set = policy_set
        self._cel_env = self._create_cel_environment()
        # Track policy evaluation results for audit logging
        self.policies_evaluated: list[str] = []
        self.last_policy_decision: str | None = None
        self.last_policy_reason: str | None = None

    def _create_cel_environment(self) -> celpy.Environment:
        """Create CEL environment with custom functions."""
        # Create CEL environment with standard functions
        env = celpy.Environment()

        # Add custom functions if needed
        # For example: env.add_function("custom_func", custom_implementation)

        return env

    def _evaluate_condition(self, condition: str, context: dict[str, Any]) -> bool:
        """Evaluate a CEL condition against the given context.

        Args:
            condition: CEL expression to evaluate
            context: Variables available in the expression

        Returns:
            True if condition passes, False otherwise
        """
        try:
            # Parse the CEL expression
            ast = self._cel_env.compile(condition)
            # Create program
            program = self._cel_env.program(ast)
            # Convert Python context to CEL format
            cel_context = self._python_to_cel_context(context)
            # Evaluate with context
            result = program.evaluate(cel_context)
            return bool(result)
        except Exception as e:
            logger.error(f"Error evaluating CEL condition '{condition}': {e}")
            # On error, default to denying access for safety
            return False

    def _python_to_cel_context(self, context: dict[str, Any]) -> dict[str, Any]:
        """Convert Python context to CEL-compatible format."""
        cel_context = {}
        for key, value in context.items():
            cel_context[key] = json_to_cel(value)
        return cel_context

    def _user_context_to_dict(self, user_context: Optional["UserContextModel"]) -> dict[str, Any]:
        """Convert UserContextModel to a dictionary for CEL evaluation."""
        if user_context is None:
            return {
                "role": "anonymous",
                "permissions": [],
                "user_id": None,
                "username": None,
                "email": None,
                "provider": None,
            }

        # Extract basic fields
        user_dict: dict[str, Any] = {
            "user_id": user_context.user_id,
            "username": user_context.username,
            "email": user_context.email,
            "provider": user_context.provider,
            "name": user_context.name,
            "role": "user",  # Default role
            "permissions": [],  # Default permissions
        }

        # Extract role and permissions from raw_profile if available
        if user_context.raw_profile:
            user_dict["role"] = user_context.raw_profile.get("role", "user")
            user_dict["permissions"] = user_context.raw_profile.get("permissions", [])

        return user_dict

    def enforce_input_policies(
        self, user_context: Optional["UserContextModel"], params: dict[str, Any]
    ) -> None:
        """Enforce input policies.

        Args:
            user_context: The user context from authentication
            params: The input parameters

        Raises:
            PolicyEnforcementError: If a policy denies access
        """
        with traced_operation(
            "mxcp.policy.enforce_input",
            attributes={
                "mxcp.policy.count": len(self.policy_set.input_policies),
                "mxcp.policy.has_user": user_context is not None,
            },
        ) as span:
            # Reset tracking for this enforcement cycle
            self.policies_evaluated = []
            self.last_policy_decision = "allow"  # Default to allow if no policies
            self.last_policy_reason = None

            # Build context for CEL evaluation
            # IMPORTANT: User context is nested under "user" to prevent collision
            # with query parameters that might also be named "user"

            # Check for dangerous naming collision
            if "user" in params:
                logger.warning(
                    "Query parameter 'user' conflicts with user context namespace. This may cause policy evaluation issues."
                )
                # For security, we prioritize user context over query parameters
                # Users should rename their parameter to avoid this collision

            # Build context with user context taking precedence over any "user" parameter
            context = {}
            context.update(params)  # Add parameters first
            context["user"] = self._user_context_to_dict(
                user_context
            )  # User context takes precedence

            # Evaluate each input policy
            for i, policy in enumerate(self.policy_set.input_policies):
                # Track that we evaluated this policy
                policy_desc = f"input[{i}]: {policy.condition}"
                self.policies_evaluated.append(policy_desc)

                with traced_operation(
                    f"mxcp.policy.evaluate_input[{i}]",
                    attributes={
                        "mxcp.policy.condition": policy.condition,
                        "mxcp.policy.action": policy.action.value if policy.action else None,
                    },
                ) as policy_span:
                    try:
                        condition_result = self._evaluate_condition(policy.condition, context)
                        if policy_span:
                            policy_span.set_attribute(
                                "mxcp.policy.condition_result", condition_result
                            )

                        if condition_result and policy.action == PolicyAction.DENY:
                            reason = policy.reason or "Access denied by policy"
                            self.last_policy_decision = "deny"
                            self.last_policy_reason = reason
                            if policy_span:
                                policy_span.set_attribute("mxcp.policy.denied", True)
                                policy_span.set_attribute("mxcp.policy.reason", reason)
                            if span:
                                span.set_attribute("mxcp.policy.decision", "deny")
                                span.set_attribute("mxcp.policy.denied_at", i)
                            logger.warning(f"Input policy denied access: {reason}")

                            # Record metrics before raising exception
                            record_counter(
                                "mxcp.policy.evaluations_total",
                                attributes={"type": "input", "decision": self.last_policy_decision},
                                description="Total policy evaluations",
                            )
                            record_counter(
                                "mxcp.policy.denials_total",
                                attributes={
                                    "type": "input",
                                    "reason": policy.action.value if policy.action else "unknown",
                                },
                                description="Total policy denials",
                            )

                            raise PolicyEnforcementError(reason)
                    except PolicyEnforcementError:
                        raise
                    except Exception as e:
                        if policy_span:
                            policy_span.set_attribute("mxcp.policy.error", str(e))
                        logger.error(f"Error evaluating policy {i}: {e}")
                        raise

            # If we get here, all policies passed
            if span:
                span.set_attribute("mxcp.policy.decision", self.last_policy_decision)
                span.set_attribute("mxcp.policy.evaluated_count", len(self.policies_evaluated))

            # Record successful evaluation metrics
            record_counter(
                "mxcp.policy.evaluations_total",
                attributes={"type": "input", "decision": self.last_policy_decision},
                description="Total policy evaluations",
            )

    def enforce_output_policies(
        self,
        user_context: Optional["UserContextModel"],
        output: Any,
        endpoint_def: dict[str, Any] | None = None,
    ) -> tuple[Any, str | None]:
        """Enforce output policies.

        Args:
            user_context: The user context from authentication
            output: The output data (can be list, dict, or scalar)
            endpoint_def: The endpoint definition containing type information

        Returns:
            Tuple of (modified output, policy action applied)

        Raises:
            PolicyEnforcementError: If a policy denies access
        """
        with traced_operation(
            "mxcp.policy.enforce_output",
            attributes={
                "mxcp.policy.count": len(self.policy_set.output_policies),
                "mxcp.policy.has_user": user_context is not None,
                "mxcp.policy.has_endpoint_def": endpoint_def is not None,
            },
        ) as span:
            # Build context for CEL evaluation
            # Note: Output policies don't have collision issues since they only use
            # "user" (user context) and "response" (output data) - no query parameters
            context = {"user": self._user_context_to_dict(user_context), "response": output}

            applied_action = None
            any_policy_applied = False

            # Evaluate each output policy
            for i, policy in enumerate(self.policy_set.output_policies):
                # Track that we evaluated this policy
                policy_desc = f"output[{i}]: {policy.condition}"
                self.policies_evaluated.append(policy_desc)

                with traced_operation(
                    f"mxcp.policy.evaluate_output[{i}]",
                    attributes={
                        "mxcp.policy.condition": policy.condition,
                        "mxcp.policy.action": policy.action.value if policy.action else None,
                    },
                ) as policy_span:
                    try:
                        condition_result = self._evaluate_condition(policy.condition, context)
                        if policy_span:
                            policy_span.set_attribute(
                                "mxcp.policy.condition_result", condition_result
                            )

                        if condition_result:
                            if policy.action == PolicyAction.DENY:
                                reason = policy.reason or "Output blocked by policy"
                                self.last_policy_decision = "deny"
                                self.last_policy_reason = reason
                                if policy_span:
                                    policy_span.set_attribute("mxcp.policy.denied", True)
                                    policy_span.set_attribute("mxcp.policy.reason", reason)
                                if span:
                                    span.set_attribute("mxcp.policy.decision", "deny")
                                    span.set_attribute("mxcp.policy.denied_at", i)
                                logger.warning(f"Output policy denied access: {reason}")

                                # Record metrics before raising exception
                                record_counter(
                                    "mxcp.policy.evaluations_total",
                                    attributes={
                                        "type": "output",
                                        "decision": self.last_policy_decision,
                                    },
                                    description="Total policy evaluations",
                                )
                                record_counter(
                                    "mxcp.policy.denials_total",
                                    attributes={
                                        "type": "output",
                                        "reason": (
                                            policy.action.value if policy.action else "unknown"
                                        ),
                                    },
                                    description="Total policy denials",
                                )

                                raise PolicyEnforcementError(reason)

                            elif policy.action == PolicyAction.FILTER_FIELDS and policy.fields:
                                output = self._filter_fields(output, policy.fields)
                                applied_action = "filter_fields"
                                any_policy_applied = True
                                if policy_span:
                                    policy_span.set_attribute(
                                        "mxcp.policy.action_applied", "filter_fields"
                                    )
                                    policy_span.set_attribute(
                                        "mxcp.policy.fields_filtered", len(policy.fields)
                                    )

                            elif policy.action == PolicyAction.MASK_FIELDS and policy.fields:
                                output = self._mask_fields(output, policy.fields)
                                applied_action = "mask_fields"
                                any_policy_applied = True
                                if policy_span:
                                    policy_span.set_attribute(
                                        "mxcp.policy.action_applied", "mask_fields"
                                    )
                                    policy_span.set_attribute(
                                        "mxcp.policy.fields_masked", len(policy.fields)
                                    )

                            elif policy.action == PolicyAction.FILTER_SENSITIVE_FIELDS:
                                if endpoint_def and "return" in endpoint_def:
                                    output = self._filter_sensitive_fields(
                                        output, endpoint_def["return"]
                                    )
                                    applied_action = "filter_sensitive_fields"
                                    any_policy_applied = True
                                    if policy_span:
                                        policy_span.set_attribute(
                                            "mxcp.policy.action_applied", "filter_sensitive_fields"
                                        )
                                else:
                                    logger.warning(
                                        "filter_sensitive_fields policy requires endpoint definition with return type"
                                    )
                                    if policy_span:
                                        policy_span.set_attribute(
                                            "mxcp.policy.warning", "missing_endpoint_def"
                                        )
                    except PolicyEnforcementError:
                        raise
                    except Exception as e:
                        if policy_span:
                            policy_span.set_attribute("mxcp.policy.error", str(e))
                        logger.error(f"Error evaluating output policy {i}: {e}")
                        raise

            # Update decision if output was modified
            if any_policy_applied and self.last_policy_decision == "allow":
                self.last_policy_decision = "warn"
                self.last_policy_reason = f"Output modified by {applied_action}"

            if span:
                span.set_attribute("mxcp.policy.decision", self.last_policy_decision)
                span.set_attribute("mxcp.policy.evaluated_count", len(self.policies_evaluated))
                if applied_action:
                    span.set_attribute("mxcp.policy.action_applied", applied_action)

            # Record successful evaluation metrics
            record_counter(
                "mxcp.policy.evaluations_total",
                attributes={"type": "output", "decision": self.last_policy_decision},
                description="Total policy evaluations",
            )

            return output, applied_action

    def _filter_fields(self, data: Any, fields: list[str]) -> Any:
        """Remove specified fields from the output.

        Args:
            data: The data to filter (list of dicts, dict, or scalar)
            fields: List of field names to remove

        Returns:
            Data with fields removed
        """
        if isinstance(data, list):
            # Handle list of dictionaries
            return [
                self._filter_dict_fields(item, fields) if isinstance(item, dict) else item
                for item in data
            ]
        elif isinstance(data, dict):
            # Handle single dictionary
            return self._filter_dict_fields(data, fields)
        else:
            # Scalar values remain unchanged
            return data

    def _filter_dict_fields(self, data: dict[str, Any], fields: list[str]) -> dict[str, Any]:
        """Remove fields from a dictionary."""
        return {k: v for k, v in data.items() if k not in fields}

    def _mask_fields(self, data: Any, fields: list[str]) -> Any:
        """Mask specified fields in the output.

        Args:
            data: The data to mask (list of dicts, dict, or scalar)
            fields: List of field names to mask

        Returns:
            Data with fields masked
        """
        if isinstance(data, list):
            # Handle list of dictionaries
            return [
                self._mask_dict_fields(item, fields) if isinstance(item, dict) else item
                for item in data
            ]
        elif isinstance(data, dict):
            # Handle single dictionary
            return self._mask_dict_fields(data, fields)
        else:
            # Scalar values remain unchanged
            return data

    def _mask_dict_fields(self, data: dict[str, Any], fields: list[str]) -> dict[str, Any]:
        """Mask fields in a dictionary."""
        result = data.copy()
        for field in fields:
            if field in result:
                result[field] = "****"
        return result

    def _filter_sensitive_fields(self, data: Any, type_def: dict[str, Any]) -> Any:
        """Recursively filter out fields marked as sensitive in the type definition.

        Args:
            data: The data to filter
            type_def: The type definition with sensitive flags

        Returns:
            Data with sensitive fields removed
        """
        # If the entire type is marked sensitive, remove it
        if type_def.get("sensitive", False):
            return None

        type_name = type_def.get("type")

        if type_name == "object" and isinstance(data, dict):
            # Handle object types
            properties = type_def.get("properties", {})
            result = {}

            for key, value in data.items():
                if key in properties:
                    # Check if this specific property is sensitive
                    prop_def = properties[key]
                    if not prop_def.get("sensitive", False):
                        # Recursively filter nested data
                        filtered = self._filter_sensitive_fields(value, prop_def)
                        if filtered is not None:
                            result[key] = filtered
                else:
                    # Keep non-defined properties if additionalProperties is true
                    if type_def.get("additionalProperties", True):
                        result[key] = value

            return result

        elif type_name == "array" and isinstance(data, list):
            # Handle array types
            items_def = type_def.get("items", {})
            array_result = []

            for item in data:
                filtered = self._filter_sensitive_fields(item, items_def)
                if filtered is not None:
                    array_result.append(filtered)

            return array_result

        else:
            # For scalar types, they should have been filtered at the property level
            # But we already checked sensitive at the top, so return as-is
            return data
