"""MXCP SDK Policy module.

This module provides the core policy enforcement functionality for MXCP,
including CEL-based policy evaluation for input validation and output filtering.

Key components:
- PolicyAction: Enum of available policy actions (DENY, FILTER_FIELDS, etc.)
- PolicyDefinition: Definition of a single policy rule
- PolicySet: Collection of input and output policies
- PolicyEnforcer: Core enforcement engine
- PolicyEnforcementError: Exception raised when access is denied

Example usage:
    >>> from mxcp.sdk.policy import PolicyEnforcer, PolicySet, PolicyDefinition, PolicyAction
    >>> from mxcp.sdk.auth import UserContext
    >>>
    >>> # Define policies
    >>> policy_set = PolicySet(
    ...     input_policies=[
    ...         PolicyDefinition(
    ...             condition='user.role != "admin"',
    ...             action=PolicyAction.DENY,
    ...             reason="Admin access required"
    ...         )
    ...     ],
    ...     output_policies=[
    ...         PolicyDefinition(
    ...             condition='user.role == "guest"',
    ...             action=PolicyAction.FILTER_FIELDS,
    ...             fields=["sensitive_data"]
    ...         )
    ...     ]
    ... )
    >>>
    >>> # Create enforcer
    >>> enforcer = PolicyEnforcer(policy_set)
    >>>
    >>> # Use with user context
    >>> user = UserContext(username="john", role="guest")
    >>> enforcer.enforce_input_policies(user, {"param": "value"})
"""

from ._types import PolicyAction, PolicyDefinition, PolicyEnforcementError, PolicySet
from .enforcer import PolicyEnforcer

__all__ = [
    # Types
    "PolicyAction",
    "PolicyDefinition",
    "PolicySet",
    "PolicyEnforcementError",
    # Enforcer
    "PolicyEnforcer",
]
