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
        
        result, action = enforcer.enforce_output_policies(user_context, output)
        assert "name" in result
        assert "email" in result
        assert "salary" not in result
        assert "ssn" not in result
        assert action == "filter_fields"
    
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
        
        result, action = enforcer.enforce_output_policies(user_context, output)
        assert len(result) == 2
        assert result[0]["name"] == "John Doe"
        assert result[0]["phone"] == "****"
        assert result[0]["address"] == "****"
        assert result[1]["name"] == "Jane Smith"
        assert result[1]["phone"] == "****"
        assert result[1]["address"] == "****"
        assert action == "mask_fields"
    
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
    
    def test_output_policy_filter_sensitive_fields(self):
        """Test filter_sensitive_fields policy action."""
        # Define a type with sensitive fields
        type_def = {
            "type": "object",
            "properties": {
                "username": {"type": "string"},
                "api_key": {"type": "string", "sensitive": True},
                "email": {"type": "string"}
            }
        }
        
        # Create policy set with filter_sensitive_fields
        policy_set = PolicySet(
            input_policies=[],
            output_policies=[
                PolicyDefinition(
                    condition="true",  # Always apply
                    action=PolicyAction.FILTER_SENSITIVE_FIELDS
                )
            ]
        )
        
        enforcer = PolicyEnforcer(policy_set)
        
        # Test data
        data = {
            "username": "john_doe",
            "api_key": "secret123",
            "email": "john@example.com"
        }
        
        # Apply policy
        result, action = enforcer.enforce_output_policies(
            user_context=None,
            output=data,
            endpoint_def={"return": type_def}
        )
        
        # Verify sensitive field was removed
        assert "username" in result
        assert "email" in result
        assert "api_key" not in result
        assert action == "filter_sensitive_fields"
    
    def test_filter_sensitive_fields_nested(self):
        """Test filtering sensitive fields from nested objects."""
        type_def = {
            "type": "object",
            "properties": {
                "user": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "credentials": {
                            "type": "object",
                            "sensitive": True,  # Entire object is sensitive
                            "properties": {
                                "password": {"type": "string"},
                                "token": {"type": "string"}
                            }
                        }
                    }
                },
                "metadata": {
                    "type": "object",
                    "properties": {
                        "created": {"type": "string"},
                        "secret": {"type": "string", "sensitive": True}
                    }
                }
            }
        }
        
        policy_set = PolicySet(
            input_policies=[],
            output_policies=[
                PolicyDefinition(
                    condition="true",
                    action=PolicyAction.FILTER_SENSITIVE_FIELDS
                )
            ]
        )
        
        enforcer = PolicyEnforcer(policy_set)
        
        data = {
            "user": {
                "name": "John",
                "credentials": {
                    "password": "pass123",
                    "token": "tok456"
                }
            },
            "metadata": {
                "created": "2024-01-01",
                "secret": "hidden"
            }
        }
        
        result, _ = enforcer.enforce_output_policies(
            user_context=None,
            output=data,
            endpoint_def={"return": type_def}
        )
        
        # Verify nested sensitive data was removed
        assert result["user"]["name"] == "John"
        assert "credentials" not in result["user"]
        assert result["metadata"]["created"] == "2024-01-01"
        assert "secret" not in result["metadata"]
    
    def test_filter_sensitive_fields_array(self):
        """Test filtering sensitive fields from arrays."""
        type_def = {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer"},
                    "token": {"type": "string", "sensitive": True},
                    "data": {"type": "string"}
                }
            }
        }
        
        policy_set = PolicySet(
            input_policies=[],
            output_policies=[
                PolicyDefinition(
                    condition="true",
                    action=PolicyAction.FILTER_SENSITIVE_FIELDS
                )
            ]
        )
        
        enforcer = PolicyEnforcer(policy_set)
        
        data = [
            {"id": 1, "token": "tok1", "data": "data1"},
            {"id": 2, "token": "tok2", "data": "data2"}
        ]
        
        result, _ = enforcer.enforce_output_policies(
            user_context=None,
            output=data,
            endpoint_def={"return": type_def}
        )
        
        # Verify sensitive fields removed from all array items
        assert len(result) == 2
        for item in result:
            assert "id" in item
            assert "data" in item
            assert "token" not in item
    
    def test_filter_sensitive_fields_conditional(self):
        """Test conditional application of filter_sensitive_fields."""
        type_def = {
            "type": "object",
            "properties": {
                "public_data": {"type": "string"},
                "admin_token": {"type": "string", "sensitive": True}
            }
        }
        
        # Only filter for non-admin users
        policy_set = PolicySet(
            input_policies=[],
            output_policies=[
                PolicyDefinition(
                    condition="user.role != 'admin'",
                    action=PolicyAction.FILTER_SENSITIVE_FIELDS
                )
            ]
        )
        
        enforcer = PolicyEnforcer(policy_set)
        
        data = {
            "public_data": "visible",
            "admin_token": "secret"
        }
        
        # Test with regular user
        regular_user = UserContext(
            user_id="1",
            username="user",
            email="user@example.com",
            provider="test",
            raw_profile={"role": "user"}
        )
        
        result, action = enforcer.enforce_output_policies(
            user_context=regular_user,
            output=data.copy(),
            endpoint_def={"return": type_def}
        )
        
        assert "public_data" in result
        assert "admin_token" not in result
        assert action == "filter_sensitive_fields"
        
        # Test with admin user
        admin_user = UserContext(
            user_id="2",
            username="admin",
            email="admin@example.com",
            provider="test",
            raw_profile={"role": "admin"}
        )
        
        result, action = enforcer.enforce_output_policies(
            user_context=admin_user,
            output=data.copy(),
            endpoint_def={"return": type_def}
        )
        
        # Admin should see everything
        assert "public_data" in result
        assert "admin_token" in result
        assert action is None


class TestPolicyConfigParsing:
    """Test parsing of filter_sensitive_fields from configuration."""
    
    def test_parse_filter_sensitive_fields_policy(self):
        """Test parsing filter_sensitive_fields action from config."""
        config = {
            "output": [
                {
                    "condition": "user.role != 'admin'",
                    "action": "filter_sensitive_fields",
                    "reason": "Non-admin users cannot see sensitive data"
                }
            ]
        }
        
        policy_set = parse_policies_from_config(config)
        
        assert len(policy_set.output_policies) == 1
        policy = policy_set.output_policies[0]
        assert policy.action == PolicyAction.FILTER_SENSITIVE_FIELDS
        assert policy.condition == "user.role != 'admin'"
        assert policy.reason == "Non-admin users cannot see sensitive data"
        assert policy.fields is None  # No fields needed for this action


class TestAuditLoggerSensitiveRedaction:
    """Test sensitive field redaction in audit logging."""
    
    def test_schema_based_redaction(self):
        """Test redaction based on endpoint schema."""
        import tempfile
        import time
        import json
        from pathlib import Path
        from mxcp.audit.logger import AuditLogger
        
        # Reset singleton instance
        AuditLogger._instance = None
        
        with tempfile.NamedTemporaryFile(suffix='.jsonl', delete=False) as f:
            log_path = Path(f.name)
        
        try:
            logger = AuditLogger(log_path, enabled=True)
            
            endpoint_def = {
                "parameters": [
                    {"name": "username", "type": "string"},
                    {"name": "password", "type": "string", "sensitive": True},
                    {"name": "query", "type": "string"}
                ]
            }
            
            logger.log_event(
                caller="cli",
                event_type="tool",
                name="test_tool",
                input_params={
                    "username": "john",
                    "password": "secret123",
                    "query": "SELECT * FROM users"
                },
                duration_ms=100,
                endpoint_def=endpoint_def
            )
            
            time.sleep(0.5)
            logger.shutdown()
            
            # Read and verify log
            with open(log_path, 'r') as f:
                log_entry = json.loads(f.readline())
                input_data = json.loads(log_entry['input_json'])
                
                assert input_data['username'] == "john"
                assert input_data['password'] == "[REDACTED]"
                assert input_data['query'] == "SELECT * FROM users"
                
        finally:
            log_path.unlink(missing_ok=True)
            AuditLogger._instance = None  # Clean up singleton
    
    def test_nested_schema_redaction(self):
        """Test redaction of nested sensitive fields."""
        import tempfile
        import time
        import json
        from pathlib import Path
        from mxcp.audit.logger import AuditLogger
        
        # Reset singleton instance
        AuditLogger._instance = None
        
        with tempfile.NamedTemporaryFile(suffix='.jsonl', delete=False) as f:
            log_path = Path(f.name)
        
        try:
            logger = AuditLogger(log_path, enabled=True)
            
            endpoint_def = {
                "parameters": [
                    {
                        "name": "config",
                        "type": "object",
                        "properties": {
                            "host": {"type": "string"},
                            "credentials": {
                                "type": "object",
                                "properties": {
                                    "username": {"type": "string"},
                                    "api_key": {"type": "string", "sensitive": True}
                                }
                            }
                        }
                    }
                ]
            }
            
            logger.log_event(
                caller="http",
                event_type="tool",
                name="connect",
                input_params={
                    "config": {
                        "host": "example.com",
                        "credentials": {
                            "username": "admin",
                            "api_key": "sk-12345"
                        }
                    }
                },
                duration_ms=50,
                endpoint_def=endpoint_def
            )
            
            time.sleep(0.5)  # Increased wait time
            logger.shutdown()
            
            with open(log_path, 'r') as f:
                content = f.read()
                assert content, "Log file is empty"
                log_entry = json.loads(content.strip())
                input_data = json.loads(log_entry['input_json'])
                
                assert input_data['config']['host'] == "example.com"
                assert input_data['config']['credentials']['username'] == "admin"
                assert input_data['config']['credentials']['api_key'] == "[REDACTED]"
                
        finally:
            log_path.unlink(missing_ok=True)
            AuditLogger._instance = None  # Clean up singleton
    
    def test_no_redaction_without_schema(self):
        """Test that no redaction happens without schema."""
        import tempfile
        import time
        import json
        from pathlib import Path
        from mxcp.audit.logger import AuditLogger
        
        # Reset singleton instance
        AuditLogger._instance = None
        
        with tempfile.NamedTemporaryFile(suffix='.jsonl', delete=False) as f:
            log_path = Path(f.name)
        
        try:
            logger = AuditLogger(log_path, enabled=True)
            
            # No endpoint_def provided
            logger.log_event(
                caller="stdio",
                event_type="resource",
                name="user_data",
                input_params={
                    "user_id": "123",
                    "api_key": "secret",
                    "password": "hidden",
                    "data": "public"
                },
                duration_ms=25
            )
            
            time.sleep(0.5)  # Increased wait time
            logger.shutdown()
            
            with open(log_path, 'r') as f:
                content = f.read()
                assert content, "Log file is empty"
                log_entry = json.loads(content.strip())
                input_data = json.loads(log_entry['input_json'])
                
                # Without schema, nothing should be redacted
                assert input_data['user_id'] == "123"
                assert input_data['api_key'] == "secret"
                assert input_data['password'] == "hidden"
                assert input_data['data'] == "public"
                
        finally:
            log_path.unlink(missing_ok=True)
            AuditLogger._instance = None  # Clean up singleton 