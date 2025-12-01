"""Pydantic models for MXCP SDK policy enforcement.

This module contains the Pydantic model definitions for policy rules and sets.
"""

from enum import Enum

from pydantic import Field

from mxcp.sdk.models import SdkBaseModel


class PolicyAction(Enum):
    """Available policy actions for controlling access and data filtering.

    Actions determine what happens when a policy condition evaluates to true:

    - DENY: Reject the request entirely
    - FILTER_FIELDS: Remove specified fields from output
    - MASK_FIELDS: Replace field values with '****'
    - FILTER_SENSITIVE_FIELDS: Remove fields marked as sensitive in schema
    """

    DENY = "deny"
    FILTER_FIELDS = "filter_fields"
    MASK_FIELDS = "mask_fields"
    FILTER_SENSITIVE_FIELDS = "filter_sensitive_fields"


class PolicyDefinitionModel(SdkBaseModel):
    """Definition of a single policy rule.

    A policy rule consists of a CEL condition that determines when the policy
    applies, an action to take when the condition is met, and optional
    additional parameters based on the action type.

    Attributes:
        condition: CEL expression that determines when this policy applies.
            The expression has access to 'user' (user context) and either
            input parameters or 'response' (output data).
        action: The action to take when the condition evaluates to true.
        reason: Human-readable reason for the action (used for DENY actions).
        fields: List of field names (used for FILTER_FIELDS and MASK_FIELDS).

    Example:
        >>> policy = PolicyDefinitionModel(
        ...     condition='user.role != "admin"',
        ...     action=PolicyAction.DENY,
        ...     reason="Admin access required"
        ... )
    """

    condition: str
    action: PolicyAction
    reason: str | None = None
    fields: list[str] | None = None


class PolicySetModel(SdkBaseModel):
    """Set of policies for input and output validation.

    A PolicySet groups input policies (applied before execution) and output
    policies (applied after execution). Policies within each group are
    evaluated in order.

    Attributes:
        input_policies: Policies applied to input parameters before execution.
            These typically check user permissions or validate parameters.
        output_policies: Policies applied to output data after execution.
            These can filter, mask, or deny access to results.

    Example:
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
        ...             fields=["sensitive_data"]
        ...         )
        ...     ]
        ... )
    """

    input_policies: list[PolicyDefinitionModel] = Field(default_factory=list)
    output_policies: list[PolicyDefinitionModel] = Field(default_factory=list)


class PolicyEnforcementError(Exception):
    """Raised when a policy denies access to a resource.

    This exception is raised during policy enforcement when a DENY action
    is triggered. The reason attribute provides a human-readable explanation.

    Attributes:
        reason: Human-readable reason for the denial.

    Example:
        >>> try:
        ...     enforcer.enforce_input_policies(user_context, params)
        ... except PolicyEnforcementError as e:
        ...     print(f"Access denied: {e.reason}")
    """

    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)
