"""Policy enforcement for MXCP endpoints.

This module provides MXCP-specific policy configuration parsing
that converts YAML/JSON configuration into SDK policy types.
"""

from typing import Any

from mxcp.sdk.policy import PolicyAction, PolicyDefinition, PolicySet

__all__ = ["parse_policies_from_config"]


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
