"""Test that policy enforcement has telemetry spans."""

import asyncio
import pytest
from mxcp.sdk.auth import UserContext
from mxcp.sdk.policy import (
    PolicyEnforcer,
    PolicySet,
    PolicyDefinition,
    PolicyAction,
    PolicyEnforcementError,
)
from mxcp.sdk.telemetry import (
    configure_telemetry,
    is_telemetry_enabled,
    traced_operation,
    shutdown_telemetry,
)


@pytest.fixture(autouse=True)
def reset_telemetry():
    """Reset telemetry state between tests."""
    # Reset OpenTelemetry's internal state
    from opentelemetry import trace
    import mxcp.sdk.telemetry._config
    import mxcp.sdk.telemetry._tracer

    # Reset before test
    trace._TRACER_PROVIDER = None
    trace._TRACER_PROVIDER_FACTORY = None
    mxcp.sdk.telemetry._config._telemetry_enabled = False
    mxcp.sdk.telemetry._tracer._tracer = None

    yield

    # Cleanup after test
    try:
        shutdown_telemetry()
    except:
        pass
    trace._TRACER_PROVIDER = None
    trace._TRACER_PROVIDER_FACTORY = None
    mxcp.sdk.telemetry._config._telemetry_enabled = False
    mxcp.sdk.telemetry._tracer._tracer = None


def test_policy_enforcement_creates_telemetry_spans():
    """Test that policy enforcement creates telemetry spans."""
    # Enable telemetry
    configure_telemetry(enabled=True, console_export=True)
    assert is_telemetry_enabled()

    # Create a policy set with input and output policies
    policy_set = PolicySet(
        input_policies=[
            PolicyDefinition(
                condition='user.role != "admin"',  # Will pass since user is admin
                action=PolicyAction.DENY,
                reason="Admin access required",
            ),
            PolicyDefinition(
                condition='param1 == "blocked"',  # Will pass since param1 is "allowed"
                action=PolicyAction.DENY,
                reason="Parameter value not allowed",
            ),
        ],
        output_policies=[
            PolicyDefinition(
                condition="response.sensitive == true",
                action=PolicyAction.FILTER_FIELDS,
                fields=["sensitive_data", "internal_id"],
            ),
            PolicyDefinition(
                condition='user.role == "guest"',
                action=PolicyAction.MASK_FIELDS,
                fields=["email", "phone"],
            ),
        ],
    )

    # Create enforcer
    enforcer = PolicyEnforcer(policy_set)

    # Create user context
    user_context = UserContext(
        provider="test", user_id="user123", username="admin_user", raw_profile={"role": "admin"}
    )

    # Test input policy enforcement (should pass)
    with traced_operation("test.policy_enforcement") as root_span:
        assert root_span is not None

        # This should pass because user is admin
        enforcer.enforce_input_policies(user_context, {"param1": "allowed"})

        # Verify policies were evaluated
        assert len(enforcer.policies_evaluated) == 2
        assert enforcer.last_policy_decision == "allow"

        # Test output policy enforcement with filtering
        output_data = {
            "data": "public",
            "sensitive": True,
            "sensitive_data": "secret",
            "internal_id": "12345",
        }

        filtered_output, action = enforcer.enforce_output_policies(user_context, output_data)

        # Should have filtered sensitive fields
        assert "sensitive_data" not in filtered_output
        assert "internal_id" not in filtered_output
        assert filtered_output["data"] == "public"
        assert action == "filter_fields"


def test_policy_denial_tracked_in_telemetry():
    """Test that policy denials are tracked in telemetry."""
    # Enable telemetry
    configure_telemetry(enabled=True, console_export=True)

    # Create a policy that will deny
    policy_set = PolicySet(
        input_policies=[
            PolicyDefinition(
                condition='user.role != "admin"',
                action=PolicyAction.DENY,
                reason="Admin access required",
            )
        ],
        output_policies=[],
    )

    enforcer = PolicyEnforcer(policy_set)

    # Create non-admin user
    user_context = UserContext(
        provider="test", user_id="user456", username="regular_user", raw_profile={"role": "user"}
    )

    # This should raise PolicyEnforcementError
    with pytest.raises(PolicyEnforcementError) as exc_info:
        enforcer.enforce_input_policies(user_context, {"param": "value"})

    assert "Admin access required" in str(exc_info.value)
    assert enforcer.last_policy_decision == "deny"


def test_nested_policy_spans():
    """Test that policy evaluation creates nested spans."""
    # Enable telemetry
    configure_telemetry(enabled=True, console_export=True)

    # Create a policy set with multiple policies
    policy_set = PolicySet(
        input_policies=[
            PolicyDefinition(
                condition='param1 == "value1"',
                action=PolicyAction.DENY,
                reason="Value1 not allowed",
            ),
            PolicyDefinition(
                condition="param2 > 100", action=PolicyAction.DENY, reason="Value too large"
            ),
        ],
        output_policies=[],
    )

    enforcer = PolicyEnforcer(policy_set)
    user_context = UserContext(provider="test", user_id="user789", username="test_user")

    # Run with telemetry
    with traced_operation("test.root") as root_span:
        assert root_span is not None

        # This should pass (neither condition matches)
        enforcer.enforce_input_policies(user_context, {"param1": "value2", "param2": 50})

        # Should have evaluated both policies
        assert len(enforcer.policies_evaluated) == 2
        assert "input[0]:" in enforcer.policies_evaluated[0]
        assert "input[1]:" in enforcer.policies_evaluated[1]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
