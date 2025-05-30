"""Tests for policy enforcement functionality."""
import pytest
from mxcp.auth.providers import UserContext
from mxcp.policies import (
    PolicyAction,
    PolicyDefinition,
    PolicySet,
    PolicyEnforcer,
    PolicyEnforcementError,
    parse_policies_from_config
)


class TestPolicyParsing:
    """Test policy configuration parsing."""
    
    def test_parse_empty_policies(self):
        """Test parsing empty policies configuration."""
        result = parse_policies_from_config(None)
        assert result is None
        
        result = parse_policies_from_config({})
        assert result is not None  # Empty dict should return empty PolicySet
        assert len(result.input_policies) == 0
        assert len(result.output_policies) == 0
    
    def test_parse_input_policies(self):
        """Test parsing input policies."""
        config = {
            "input": [
                {
                    "condition": "user.role == 'guest'",
                    "action": "deny",
                    "reason": "Guests not allowed"
                }
            ]
        }
        
        result = parse_policies_from_config(config)
        assert result is not None
        assert len(result.input_policies) == 1
        assert result.input_policies[0].condition == "user.role == 'guest'"
        assert result.input_policies[0].action == PolicyAction.DENY
        assert result.input_policies[0].reason == "Guests not allowed"
    
    def test_parse_output_policies(self):
        """Test parsing output policies with field filtering."""
        config = {
            "output": [
                {
                    "condition": "user.role != 'admin'",
                    "action": "filter_fields",
                    "fields": ["salary", "ssn"]
                },
                {
                    "condition": "true",
                    "action": "mask_fields",
                    "fields": ["phone"]
                }
            ]
        }
        
        result = parse_policies_from_config(config)
        assert result is not None
        assert len(result.output_policies) == 2
        
        # Check filter_fields policy
        assert result.output_policies[0].action == PolicyAction.FILTER_FIELDS
        assert result.output_policies[0].fields == ["salary", "ssn"]
        
        # Check mask_fields policy
        assert result.output_policies[1].action == PolicyAction.MASK_FIELDS
        assert result.output_policies[1].fields == ["phone"]


class TestPolicyEnforcement:
    """Test policy enforcement logic."""
    
    def test_input_policy_deny(self):
        """Test input policy that denies access."""
        policy_set = PolicySet(
            input_policies=[
                PolicyDefinition(
                    condition="user.role == 'guest'",
                    action=PolicyAction.DENY,
                    reason="Guests not allowed"
                )
            ],
            output_policies=[]
        )
        
        enforcer = PolicyEnforcer(policy_set)
        
        # Create a guest user context
        user_context = UserContext(
            provider="test",
            user_id="guest123",
            username="guest",
            raw_profile={"role": "guest"}
        )
        
        # Should raise PolicyEnforcementError
        with pytest.raises(PolicyEnforcementError) as excinfo:
            enforcer.enforce_input_policies(user_context, {})
        
        assert "Guests not allowed" in str(excinfo.value)
    
    def test_input_policy_allow(self):
        """Test input policy that allows access."""
        policy_set = PolicySet(
            input_policies=[
                PolicyDefinition(
                    condition="user.role == 'guest'",
                    action=PolicyAction.DENY,
                    reason="Guests not allowed"
                )
            ],
            output_policies=[]
        )
        
        enforcer = PolicyEnforcer(policy_set)
        
        # Create an admin user context
        user_context = UserContext(
            provider="test",
            user_id="admin123",
            username="admin",
            raw_profile={"role": "admin"}
        )
        
        # Should not raise any error
        enforcer.enforce_input_policies(user_context, {})
    
    def test_output_policy_filter_fields(self):
        """Test output policy that filters fields."""
        policy_set = PolicySet(
            input_policies=[],
            output_policies=[
                PolicyDefinition(
                    condition="user.role != 'admin'",
                    action=PolicyAction.FILTER_FIELDS,
                    fields=["salary", "ssn"]
                )
            ]
        )
        
        enforcer = PolicyEnforcer(policy_set)
        
        # Create a regular user context
        user_context = UserContext(
            provider="test",
            user_id="user123",
            username="user",
            raw_profile={"role": "user"}
        )
        
        # Test with single dict
        output = {
            "name": "John Doe",
            "email": "john@example.com",
            "salary": 100000,
            "ssn": "123-45-6789"
        }
        
        result = enforcer.enforce_output_policies(user_context, output)
        assert "name" in result
        assert "email" in result
        assert "salary" not in result
        assert "ssn" not in result
    
    def test_output_policy_mask_fields(self):
        """Test output policy that masks fields."""
        policy_set = PolicySet(
            input_policies=[],
            output_policies=[
                PolicyDefinition(
                    condition="!('pii.view' in user.permissions)",
                    action=PolicyAction.MASK_FIELDS,
                    fields=["phone", "address"]
                )
            ]
        )
        
        enforcer = PolicyEnforcer(policy_set)
        
        # Create a user without PII permission
        user_context = UserContext(
            provider="test",
            user_id="user123",
            username="user",
            raw_profile={"permissions": ["read", "write"]}
        )
        
        # Test with list of dicts
        output = [
            {
                "name": "John Doe",
                "phone": "555-1234",
                "address": "123 Main St"
            },
            {
                "name": "Jane Smith",
                "phone": "555-5678",
                "address": "456 Oak Ave"
            }
        ]
        
        result = enforcer.enforce_output_policies(user_context, output)
        assert len(result) == 2
        assert result[0]["name"] == "John Doe"
        assert result[0]["phone"] == "****"
        assert result[0]["address"] == "****"
        assert result[1]["name"] == "Jane Smith"
        assert result[1]["phone"] == "****"
        assert result[1]["address"] == "****"
    
    def test_permission_check_policy(self):
        """Test policy with permission checks."""
        policy_set = PolicySet(
            input_policies=[
                PolicyDefinition(
                    condition="!('resource.read' in user.permissions)",
                    action=PolicyAction.DENY,
                    reason="Missing resource.read permission"
                )
            ],
            output_policies=[]
        )
        
        enforcer = PolicyEnforcer(policy_set)
        
        # User without permission
        user_context = UserContext(
            provider="test",
            user_id="user123",
            username="user",
            raw_profile={"permissions": ["write"]}
        )
        
        with pytest.raises(PolicyEnforcementError) as excinfo:
            enforcer.enforce_input_policies(user_context, {})
        
        assert "Missing resource.read permission" in str(excinfo.value)
        
        # User with permission
        user_context = UserContext(
            provider="test",
            user_id="user456",
            username="user2",
            raw_profile={"permissions": ["resource.read", "write"]}
        )
        
        # Should not raise
        enforcer.enforce_input_policies(user_context, {})
    
    def test_parameter_based_policy(self):
        """Test policy that uses query parameters."""
        policy_set = PolicySet(
            input_policies=[
                PolicyDefinition(
                    condition="employee_id != user.user_id && user.role != 'admin'",
                    action=PolicyAction.DENY,
                    reason="Users can only view their own profile"
                )
            ],
            output_policies=[]
        )
        
        enforcer = PolicyEnforcer(policy_set)
        
        # Regular user trying to access another user's profile
        user_context = UserContext(
            provider="test",
            user_id="user123",
            username="user",
            raw_profile={"role": "user"}
        )
        
        params = {"employee_id": "user456"}
        
        with pytest.raises(PolicyEnforcementError) as excinfo:
            enforcer.enforce_input_policies(user_context, params)
        
        assert "Users can only view their own profile" in str(excinfo.value)
        
        # User accessing their own profile - should be allowed
        params = {"employee_id": "user123"}
        enforcer.enforce_input_policies(user_context, params)
        
        # Admin accessing any profile - should be allowed
        admin_context = UserContext(
            provider="test",
            user_id="admin123",
            username="admin",
            raw_profile={"role": "admin"}
        )
        params = {"employee_id": "user456"}
        enforcer.enforce_input_policies(admin_context, params)
    
    def test_anonymous_user_context(self):
        """Test policy enforcement with anonymous user context."""
        policy_set = PolicySet(
            input_policies=[
                PolicyDefinition(
                    condition="user.user_id == null",
                    action=PolicyAction.DENY,
                    reason="Authentication required"
                )
            ],
            output_policies=[]
        )
        
        enforcer = PolicyEnforcer(policy_set)
        
        # None user context should be treated as anonymous
        with pytest.raises(PolicyEnforcementError) as excinfo:
            enforcer.enforce_input_policies(None, {})
        
        assert "Authentication required" in str(excinfo.value) 