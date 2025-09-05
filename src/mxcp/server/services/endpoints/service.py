"""Shared SDK executor functionality for endpoint execution.

This module provides a unified interface for executing endpoints using the SDK executor system,
replacing the legacy DuckDBSession-based execution. This is used by CLI commands and testing.
"""

import logging
from typing import TYPE_CHECKING, Any, Optional, cast

if TYPE_CHECKING:
    from mxcp.server.interfaces.server.mcp import RAWMCP

from mxcp.sdk.auth import UserContext
from mxcp.sdk.executor.interfaces import ExecutionEngine
from mxcp.sdk.policy import (
    PolicyAction,
    PolicyDefinition,
    PolicyEnforcementError,
    PolicyEnforcer,
    PolicySet,
)
from mxcp.server.core.config._types import SiteConfig, UserConfig
from mxcp.server.core.config.site_config import find_repo_root
from mxcp.server.definitions.endpoints._types import PromptDefinition
from mxcp.server.definitions.endpoints.loader import EndpointLoader
from mxcp.server.executor.engine import create_runtime_environment
from mxcp.server.executor.runners.endpoint import (
    execute_code_with_engine,
    execute_prompt_with_validation,
)

logger = logging.getLogger(__name__)


def parse_policies_from_config(policies_config: dict[str, Any] | None) -> PolicySet | None:
    """Parse policy configuration into PolicySet.

    This function handles parsing of policy configuration from YAML/JSON format
    into the PolicySet structure used by the SDK.

    Args:
        policies_config: The policies section from endpoint configuration.
                        Expected format:
                        {
                            "input": [
                                {
                                    "condition": "user.role != 'admin'",
                                    "action": "deny",
                                    "reason": "Admin access required"
                                }
                            ],
                            "output": [
                                {
                                    "condition": "user.role == 'guest'",
                                    "action": "filter_fields",
                                    "fields": ["sensitive_data"]
                                }
                            ]
                        }

    Returns:
        PolicySet or None if no policies defined

    Example:
        >>> config = {
        ...     "input": [{
        ...         "condition": "user.role != 'admin'",
        ...         "action": "deny",
        ...         "reason": "Admin only"
        ...     }],
        ...     "output": [{
        ...         "condition": "true",
        ...         "action": "filter_fields",
        ...         "fields": ["password", "secret"]
        ...     }]
        ... }
        >>> policy_set = parse_policies_from_config(config)
        >>> from mxcp.sdk.policy import PolicyEnforcer
        >>> enforcer = PolicyEnforcer(policy_set)
    """
    if policies_config is None:
        return None

    input_policies = []
    output_policies = []

    # Parse input policies
    for policy_dict in policies_config.get("input", []):
        action = PolicyAction(policy_dict["action"])
        policy = PolicyDefinition(
            condition=policy_dict["condition"],
            action=action,
            reason=policy_dict.get("reason"),
            fields=policy_dict.get("fields"),
        )
        input_policies.append(policy)

    # Parse output policies
    for policy_dict in policies_config.get("output", []):
        action = PolicyAction(policy_dict["action"])
        policy = PolicyDefinition(
            condition=policy_dict["condition"],
            action=action,
            reason=policy_dict.get("reason"),
            fields=policy_dict.get("fields"),
        )
        output_policies.append(policy)

    # Return PolicySet even for empty dict (this allows for explicit empty config)
    return PolicySet(input_policies=input_policies, output_policies=output_policies)


async def execute_endpoint(
    endpoint_type: str,
    name: str,
    params: dict[str, Any],
    user_config: UserConfig,
    site_config: SiteConfig,
    profile_name: str,
    readonly: bool = False,
    skip_output_validation: bool = False,
    user_context: UserContext | None = None,
) -> Any:
    """Execute endpoint using SDK executor system.

    Args:
        endpoint_type: Type of endpoint ("tool", "resource", "prompt")
        name: Name of the endpoint to execute
        params: Parameters to pass to the endpoint
        user_config: User configuration
        site_config: Site configuration
        profile_name: Profile name to use
        readonly: Whether to use readonly database connection
        skip_output_validation: Whether to skip output schema validation
        user_context: User context for authentication/authorization

    Returns:
        The result of endpoint execution

    Raises:
        ValueError: If endpoint not found or invalid
        RuntimeError: If execution fails
    """

    # Create runtime environment
    runtime_env = create_runtime_environment(
        user_config, site_config, profile_name, readonly=readonly
    )

    try:
        # Delegate to the with_engine variant to avoid code duplication
        return await execute_endpoint_with_engine(
            endpoint_type=endpoint_type,
            name=name,
            params=params,
            user_config=user_config,
            site_config=site_config,
            execution_engine=runtime_env.execution_engine,
            skip_output_validation=skip_output_validation,
            user_context=user_context,
        )

    finally:
        # Shutdown the runtime environment
        runtime_env.shutdown()


async def execute_endpoint_with_engine_and_policy(
    endpoint_type: str,
    name: str,
    params: dict[str, Any],
    user_config: UserConfig,
    site_config: SiteConfig,
    execution_engine: ExecutionEngine,
    skip_output_validation: bool = False,
    user_context: UserContext | None = None,
    server_ref: Optional["RAWMCP"] = None,
) -> tuple[Any, dict[str, Any]]:
    """Execute endpoint and return both result and policy information.

    This is the full implementation that returns all execution details including
    policy enforcement information.

    Args:
        endpoint_type: Type of endpoint ("tool", "resource", "prompt")
        name: Name of the endpoint to execute
        params: Parameters to pass to the endpoint
        site_config: Site configuration (needed for EndpointLoader)
        execution_engine: Pre-created execution engine to reuse
        skip_output_validation: Whether to skip output schema validation
        user_context: User context for authentication/authorization

    Returns:
        Tuple of (result, policy_info) where policy_info contains:
            - policies_evaluated: List of policies that were evaluated
            - policy_decision: "allow", "deny", "warn", or None
            - policy_reason: Reason if denied or warned

    Raises:
        ValueError: If endpoint not found or invalid
        RuntimeError: If execution fails
    """

    # Find repository root
    repo_root = find_repo_root()
    if not repo_root:
        raise ValueError("Could not find repository root (no mxcp-site.yml found)")

    # Load the endpoint using EndpointLoader
    loader = EndpointLoader(site_config)
    endpoint_result = loader.load_endpoint(endpoint_type, name)

    if not endpoint_result:
        raise FileNotFoundError(f"Endpoint '{name}' not found in {endpoint_type}s")

    endpoint_file_path, endpoint_definition = endpoint_result

    # endpoint_definition is the raw dict containing the full endpoint structure
    # Extract the type-specific data with proper typing
    policy_enforcer = None

    if endpoint_type == "tool":
        tool_def = endpoint_definition.get("tool")
        if not tool_def:
            raise ValueError("No tool definition found in endpoint")

        policies_config = tool_def.get("policies")
        if policies_config:
            policy_set = parse_policies_from_config(cast(dict[str, Any], policies_config))
            if policy_set:
                policy_enforcer = PolicyEnforcer(policy_set)

    elif endpoint_type == "resource":
        resource_def = endpoint_definition.get("resource")
        if not resource_def:
            raise ValueError("No resource definition found in endpoint")

        policies_config = resource_def.get("policies")
        if policies_config:
            policy_set = parse_policies_from_config(cast(dict[str, Any], policies_config))
            if policy_set:
                policy_enforcer = PolicyEnforcer(policy_set)

    elif endpoint_type == "prompt":
        prompt_def = endpoint_definition.get("prompt")
        if not prompt_def:
            raise ValueError("No prompt definition found in endpoint")

        policies_config = prompt_def.get("policies")
        if policies_config:
            policy_set = parse_policies_from_config(cast(dict[str, Any], policies_config))
            if policy_set:
                policy_enforcer = PolicyEnforcer(policy_set)

    else:
        raise ValueError(f"Unknown endpoint type: {endpoint_type}")

    # Enforce input policies if policy enforcer exists
    if policy_enforcer:
        try:
            policy_enforcer.enforce_input_policies(user_context, params)
        except PolicyEnforcementError as e:
            raise ValueError(f"Policy enforcement failed: {e.reason}") from e

    # Dispatch to appropriate execution method based on endpoint type
    if endpoint_type == "prompt":
        # We already verified prompt_def exists above
        prompt_def = cast(PromptDefinition, endpoint_definition.get("prompt"))
        result = await execute_prompt_with_validation(prompt_def, params, skip_output_validation)
    else:
        result = await execute_code_with_engine(
            endpoint_definition,
            endpoint_type,
            endpoint_file_path,
            repo_root,
            params,
            execution_engine,
            skip_output_validation,
            user_config,
            site_config,
            user_context,
            server_ref,
        )

    # Enforce output policies (symmetry with input policy enforcement above)
    if policy_enforcer:
        try:
            # Get the appropriate definition for policy enforcement
            if endpoint_type == "tool":
                endpoint_def = cast(dict[str, Any], endpoint_definition.get("tool"))
            elif endpoint_type == "resource":
                endpoint_def = cast(dict[str, Any], endpoint_definition.get("resource"))
            else:  # prompt
                endpoint_def = cast(dict[str, Any], endpoint_definition.get("prompt"))

            result, action = policy_enforcer.enforce_output_policies(
                user_context, result, endpoint_def
            )
        except PolicyEnforcementError as e:
            raise ValueError(f"Output policy enforcement failed: {e.reason}") from e

    # Always return policy info
    if policy_enforcer:
        policy_info = {
            "policies_evaluated": policy_enforcer.policies_evaluated,
            "policy_decision": policy_enforcer.last_policy_decision,
            "policy_reason": policy_enforcer.last_policy_reason,
        }
    else:
        # No policies were defined
        policy_info = {
            "policies_evaluated": [],
            "policy_decision": None,
            "policy_reason": None,
        }

    return result, policy_info


async def execute_endpoint_with_engine(
    endpoint_type: str,
    name: str,
    params: dict[str, Any],
    user_config: UserConfig,
    site_config: SiteConfig,
    execution_engine: ExecutionEngine,
    skip_output_validation: bool = False,
    user_context: UserContext | None = None,
    server_ref: Optional["RAWMCP"] = None,
) -> Any:
    """Execute endpoint using an existing SDK execution engine.

    This is a convenience wrapper that only returns the execution result,
    discarding policy information. Use execute_endpoint_with_engine_and_policy
    if you need policy enforcement details.

    Args:
        endpoint_type: Type of endpoint ("tool", "resource", "prompt")
        name: Name of the endpoint to execute
        params: Parameters to pass to the endpoint
        user_config: User configuration
        site_config: Site configuration (needed for EndpointLoader)
        execution_engine: Pre-created execution engine to reuse
        skip_output_validation: Whether to skip output schema validation
        user_context: User context for authentication/authorization
        server_ref: Optional reference to the server (for runtime access)

    Returns:
        The result of endpoint execution

    Raises:
        ValueError: If endpoint not found or invalid
        RuntimeError: If execution fails
    """
    result, _ = await execute_endpoint_with_engine_and_policy(
        endpoint_type=endpoint_type,
        name=name,
        params=params,
        user_config=user_config,
        site_config=site_config,
        execution_engine=execution_engine,
        skip_output_validation=skip_output_validation,
        user_context=user_context,
        server_ref=server_ref,
    )
    return result
