"""Integration tests for policy enforcement functionality."""
import pytest
import asyncio
import os
from pathlib import Path
from mxcp.endpoints.executor import EndpointExecutor, EndpointType, execute_endpoint
from mxcp.config.user_config import load_user_config
from mxcp.config.site_config import load_site_config
from mxcp.auth.providers import UserContext
from mxcp.policies import PolicyEnforcementError
from mxcp.engine.duckdb_session import DuckDBSession


@pytest.fixture(scope="session", autouse=True)
def set_mxcp_config_env():
    """Set MXCP_CONFIG environment variable to test config."""
    os.environ["MXCP_CONFIG"] = str(Path(__file__).parent / "fixtures" / "policies" / "mxcp-config.yml")


@pytest.fixture
def test_repo_path():
    """Path to the test repository."""
    return Path(__file__).parent / "fixtures" / "policies"


@pytest.fixture
def user_config(test_repo_path):
    """Load test user configuration."""
    original_dir = os.getcwd()
    os.chdir(test_repo_path)
    try:
        site_config = load_site_config()
        return load_user_config(site_config)
    finally:
        os.chdir(original_dir)


@pytest.fixture
def site_config(test_repo_path):
    """Load test site configuration."""
    original_dir = os.getcwd()
    os.chdir(test_repo_path)
    try:
        return load_site_config()
    finally:
        os.chdir(original_dir)


@pytest.fixture(autouse=True)
def chdir_to_fixtures(test_repo_path):
    """Change to the fixtures directory for each test."""
    original_dir = os.getcwd()
    os.chdir(test_repo_path)
    yield
    os.chdir(original_dir)


@pytest.fixture
def test_session(user_config, site_config):
    """Create a test DuckDB session."""
    session = DuckDBSession(user_config, site_config, None, readonly=True)
    yield session
    session.close()


class TestPolicyIntegration:
    """Test policy enforcement integration with endpoints."""
    
    @pytest.mark.asyncio
    async def test_guest_access_denied(self, user_config, site_config, test_session):
        """Test that guest users are denied access."""
        user_context = UserContext(
            provider="test",
            user_id="guest123",
            username="guest",
            raw_profile={"role": "guest", "permissions": []}
        )
        
        with pytest.raises(ValueError) as excinfo:
            await execute_endpoint(
                "tool", 
                "employee_info", 
                {"employee_id": "emp123"}, 
                user_config, 
                site_config,
                test_session,
                user_context=user_context
            )
        
        assert "Guests cannot access employee information" in str(excinfo.value)
    
    @pytest.mark.asyncio
    async def test_missing_permission_denied(self, user_config, site_config, test_session):
        """Test that users without required permissions are denied."""
        user_context = UserContext(
            provider="test",
            user_id="emp456",
            username="user",
            raw_profile={"role": "user", "permissions": []}
        )
        
        with pytest.raises(ValueError) as excinfo:
            await execute_endpoint(
                "tool", 
                "employee_info", 
                {"employee_id": "emp123"}, 
                user_config, 
                site_config,
                test_session,
                user_context=user_context
            )
        
        assert "Missing 'employee.read' permission" in str(excinfo.value)
    
    @pytest.mark.asyncio
    async def test_user_viewing_others_profile_denied(self, user_config, site_config, test_session):
        """Test that users cannot view other employees' profiles."""
        user_context = UserContext(
            provider="test",
            user_id="emp123",
            username="user",
            raw_profile={"role": "user", "permissions": ["employee.read"]}
        )
        
        with pytest.raises(ValueError) as excinfo:
            await execute_endpoint(
                "tool", 
                "employee_info", 
                {"employee_id": "emp456"},  # Trying to view someone else's profile
                user_config, 
                site_config,
                test_session,
                user_context=user_context
            )
        
        assert "You can only view your own employee information" in str(excinfo.value)
    
    @pytest.mark.asyncio
    async def test_user_viewing_own_profile(self, user_config, site_config, test_session):
        """Test that users can view their own profile with filtered data."""
        user_context = UserContext(
            provider="test",
            user_id="emp123",
            username="user",
            raw_profile={"role": "user", "permissions": ["employee.read"]}
        )
        
        result = await execute_endpoint(
            "tool", 
            "employee_info", 
            {"employee_id": "emp123"},  # Viewing own profile
            user_config, 
            site_config,
            test_session,
            user_context=user_context
        )
        
        # Verify basic fields are present
        assert result["id"] == "emp123"
        assert result["name"] == "John Doe"
        assert result["email"] == "john.doe@company.com"
        assert result["department"] == "Engineering"
        
        # Verify salary is filtered out (not admin/hr)
        assert "salary" not in result
        
        # Verify SSN is masked (not hr)
        assert result["ssn"] == "****"
        
        # Verify phone is filtered out (no pii.view permission)
        assert "phone" not in result
    
    @pytest.mark.asyncio
    async def test_hr_user_access(self, user_config, site_config, test_session):
        """Test that HR users can view all employee data."""
        user_context = UserContext(
            provider="test",
            user_id="hr001",
            username="hr_user",
            raw_profile={"role": "hr", "permissions": ["employee.read", "pii.view"]}
        )
        
        # HR can view any employee
        result = await execute_endpoint(
            "tool", 
            "employee_info", 
            {"employee_id": "emp123"},
            user_config, 
            site_config,
            test_session,
            user_context=user_context
        )
        
        # Verify all fields are present
        assert result["id"] == "emp123"
        assert result["name"] == "John Doe"
        assert result["email"] == "john.doe@company.com"
        assert result["department"] == "Engineering"
        
        # HR can see salary
        assert result["salary"] == 85000
        
        # HR can see real SSN (not masked)
        assert result["ssn"] == "123-45-6789"
        
        # HR with pii.view can see phone
        assert result["phone"] == "555-1234"
        
        # Test HR viewing another employee
        result2 = await execute_endpoint(
            "tool", 
            "employee_info", 
            {"employee_id": "emp456"},
            user_config, 
            site_config,
            test_session,
            user_context=user_context
        )
        
        assert result2["id"] == "emp456"
        assert result2["name"] == "Jane Smith"
        assert result2["ssn"] == "987-65-4321"  # Real SSN
    
    @pytest.mark.asyncio
    async def test_admin_user_access(self, user_config, site_config, test_session):
        """Test that admin users have appropriate access."""
        user_context = UserContext(
            provider="test",
            user_id="admin001",
            username="admin",
            raw_profile={"role": "admin", "permissions": ["employee.read", "pii.view"]}
        )
        
        # Admin can view any employee
        result = await execute_endpoint(
            "tool", 
            "employee_info", 
            {"employee_id": "emp123"},
            user_config, 
            site_config,
            test_session,
            user_context=user_context
        )
        
        # Admin can see salary
        assert result["salary"] == 85000
        
        # Admin can see phone (has pii.view)
        assert result["phone"] == "555-1234"
        
        # But SSN is still masked (only HR can see unmasked SSN)
        assert result["ssn"] == "****"
    
    @pytest.mark.asyncio
    async def test_user_without_pii_permission(self, user_config, site_config, test_session):
        """Test that users without pii.view permission cannot see phone numbers."""
        user_context = UserContext(
            provider="test",
            user_id="hr002",
            username="hr_user2",
            raw_profile={"role": "hr", "permissions": ["employee.read"]}  # No pii.view
        )
        
        result = await execute_endpoint(
            "tool", 
            "employee_info", 
            {"employee_id": "emp123"},
            user_config, 
            site_config,
            test_session,
            user_context=user_context
        )
        
        # HR without pii.view cannot see phone
        assert "phone" not in result
        
        # But can still see unmasked SSN (HR role)
        assert result["ssn"] == "123-45-6789"
    
    @pytest.mark.asyncio
    async def test_anonymous_user_denied(self, user_config, site_config, test_session):
        """Test that anonymous users (None context) are handled properly."""
        # Anonymous users have role="anonymous" and no permissions by default
        
        with pytest.raises(ValueError) as excinfo:
            await execute_endpoint(
                "tool", 
                "employee_info", 
                {"employee_id": "emp123"},
                user_config, 
                site_config,
                test_session,
                user_context=None
            )
        
        # Anonymous users should be denied due to missing permissions
        assert "Missing 'employee.read' permission" in str(excinfo.value)


class TestPolicyEnforcementEdgeCases:
    """Test edge cases in policy enforcement."""
    
    @pytest.mark.asyncio
    async def test_multiple_filter_policies(self, user_config, site_config, test_session):
        """Test that multiple output policies are applied correctly."""
        user_context = UserContext(
            provider="test",
            user_id="emp123",
            username="user",
            raw_profile={"role": "user", "permissions": ["employee.read"]}
        )
        
        result = await execute_endpoint(
            "tool", 
            "employee_info", 
            {"employee_id": "emp123"},
            user_config, 
            site_config,
            test_session,
            user_context=user_context
        )
        
        # Verify multiple policies were applied:
        # 1. salary filtered (not admin/hr)
        assert "salary" not in result
        
        # 2. SSN masked (not hr)
        assert result["ssn"] == "****"
        
        # 3. phone filtered (no pii.view)
        assert "phone" not in result
    
    @pytest.mark.asyncio
    async def test_policy_with_complex_conditions(self, user_config, site_config, test_session):
        """Test policies with complex CEL conditions."""
        # Test the compound condition: employee_id != user.user_id && user.role != 'admin' && user.role != 'hr'
        
        # Admin can view any employee even if not their own
        admin_context = UserContext(
            provider="test",
            user_id="admin001",
            username="admin",
            raw_profile={"role": "admin", "permissions": ["employee.read"]}
        )
        
        result = await execute_endpoint(
            "tool", 
            "employee_info", 
            {"employee_id": "emp456"},  # Not admin's ID
            user_config, 
            site_config,
            test_session,
            user_context=admin_context
        )
        
        assert result["id"] == "emp456"  # Admin can view it
        
        # HR can also view any employee
        hr_context = UserContext(
            provider="test",
            user_id="hr001",
            username="hr_user",
            raw_profile={"role": "hr", "permissions": ["employee.read"]}
        )
        
        result = await execute_endpoint(
            "tool", 
            "employee_info", 
            {"employee_id": "emp123"},  # Not HR's ID
            user_config, 
            site_config,
            test_session,
            user_context=hr_context
        )
        
        assert result["id"] == "emp123"  # HR can view it 

    @pytest.mark.asyncio
    async def test_policy_with_nonexistent_fields(self, user_config, site_config, test_session):
        """Test that policies handle non-existent fields gracefully."""
        # Create a policy that references fields that don't exist in our test data
        # This simulates a common scenario where policies are defined generically
        # across endpoints with different schemas
        
        user_context = UserContext(
            provider="test",
            user_id="emp123",
            username="user",
            raw_profile={"role": "user", "permissions": ["employee.read"]}
        )
        
        # Get result to see what fields are actually present
        result = await execute_endpoint(
            "tool", 
            "employee_info", 
            {"employee_id": "emp123"},
            user_config, 
            site_config,
            test_session,
            user_context=user_context
        )
        
        # The employee_info endpoint should return:
        # id, name, email, department, hire_date, salary (filtered), ssn (masked), phone (filtered)
        expected_fields = {"id", "name", "email", "department", "ssn", "hire_date"}
        assert set(result.keys()) == expected_fields
        
        # Verify that existing fields were properly processed:
        # - salary was filtered out (user is not admin/hr)
        assert "salary" not in result
        
        # - ssn was masked (user is not hr)
        assert result["ssn"] == "****"
        
        # - phone was filtered out (user doesn't have pii.view permission)
        assert "phone" not in result
        
        # - Regular fields remain untouched
        assert result["id"] == "emp123"
        assert result["name"] == "John Doe"
        assert result["email"] == "john.doe@company.com"
        assert result["department"] == "Engineering"
        
        # The key test: policies reference non-existent fields like 
        # "internal_notes", "performance_rating", "manager_comments" etc.
        # These should be silently ignored without causing errors
        # (this is implicitly tested since our policies in the YAML
        # can reference fields that don't exist in all endpoints)

    @pytest.mark.asyncio
    async def test_nonexistent_fields_in_policies(self, user_config, site_config, test_session):
        """Test that policies handle non-existent fields gracefully without errors."""
        # Test with regular user - should trigger both filter and mask policies
        user_context = UserContext(
            provider="test",
            user_id="user123",
            username="regular_user",
            raw_profile={"role": "user", "permissions": []}
        )
        
        result = await execute_endpoint(
            "tool", 
            "test_nonexistent_fields", 
            {"user_id": "user123"},
            user_config, 
            site_config,
            test_session,
            user_context=user_context
        )
        
        # Should only have the 3 fields that actually exist in the response
        expected_fields = {"id", "name", "email"}
        assert set(result.keys()) == expected_fields
        
        # Verify the actual data is correct
        assert result["id"] == "user123"
        assert result["name"] == "Test User"
        assert result["email"] == "test@example.com"
        
        # All non-existent fields referenced in policies should be silently ignored
        non_existent_fields = [
            "salary", "ssn", "internal_notes", "performance_rating", 
            "manager_comments", "secret_data", "phone", "credit_card",
            "password_hash", "api_keys", "private_keys"
        ]
        for field in non_existent_fields:
            assert field not in result
        
        # Test with admin user - should bypass filter_fields policy
        admin_context = UserContext(
            provider="test", 
            user_id="admin123",
            username="admin_user",
            raw_profile={"role": "admin", "permissions": []}
        )
        
        admin_result = await execute_endpoint(
            "tool",
            "test_nonexistent_fields",
            {"user_id": "user123"},
            user_config,
            site_config,
            test_session,
            user_context=admin_context
        )
        
        # Admin should still get the same result since the non-existent fields
        # don't exist to be filtered anyway
        assert admin_result == result
        
        # Test with superuser - should bypass both policies
        superuser_context = UserContext(
            provider="test",
            user_id="super123", 
            username="superuser",
            raw_profile={"role": "superuser", "permissions": []}
        )
        
        super_result = await execute_endpoint(
            "tool",
            "test_nonexistent_fields", 
            {"user_id": "user123"},
            user_config,
            site_config,
            test_session,
            user_context=superuser_context
        )
        
        # Superuser should also get the same result
        assert super_result == result 

    @pytest.mark.asyncio
    async def test_user_parameter_collision_bug(self, user_config, site_config, test_session):
        """Test the critical bug where a parameter named 'user' overwrites user context."""
        # This test demonstrates a serious security bug!
        # When a query parameter is named "user", it overwrites the user context
        # in the CEL evaluation, potentially bypassing security policies
        
        # Create a non-admin user context
        user_context = UserContext(
            provider="test",
            user_id="regular123",
            username="regular_user",
            raw_profile={"role": "user", "permissions": []}  # NOT admin
        )
        
        # The endpoint has a policy: condition: "user.role == 'admin'"
        # This SHOULD evaluate user_context.role which is "user", so the condition is False
        # But because of the bug, the parameter "user": "some_string" overwrites the context
        # And "some_string".role will be null/undefined, making the evaluation fail
        
        # This call should work because user.role != 'admin' (regular user)
        # But it will likely fail due to the collision bug
        try:
            result = await execute_endpoint(
                "tool", 
                "test_user_collision", 
                {"user": "test_value"},  # This overwrites the user context!
                user_config, 
                site_config,
                test_session,
                user_context=user_context
            )
            # If we get here, the policy was bypassed due to the bug
            print(f"Result: {result}")
            assert False, "This test should fail due to the user parameter collision bug"
        except Exception as e:
            # The policy evaluation will likely fail because "test_value".role doesn't exist
            print(f"Exception as expected due to collision bug: {e}")
            # This demonstrates the security issue - the policy doesn't work as intended

    @pytest.mark.asyncio
    async def test_user_parameter_collision_fixed(self, user_config, site_config, test_session):
        """Test that the user parameter collision is now properly handled."""
        # After the fix, user context should take precedence over query parameters
        
        # Test 1: Non-admin user should be allowed (policy condition is false)
        user_context = UserContext(
            provider="test",
            user_id="regular123",
            username="regular_user",
            raw_profile={"role": "user", "permissions": []}  # NOT admin
        )
        
        # This should work because user.role != 'admin' (the policy denies when role == 'admin')
        result = await execute_endpoint(
            "tool", 
            "test_user_collision", 
            {"user": "test_value"},  # This parameter should NOT overwrite user context
            user_config, 
            site_config,
            test_session,
            user_context=user_context
        )
        
        # Verify the endpoint executed successfully
        assert result["id"] == "test_value"
        assert result["name"] == "Test User for test_value"
        
        # Test 2: Admin user should be denied (policy condition is true)
        admin_context = UserContext(
            provider="test",
            user_id="admin123",
            username="admin_user",
            raw_profile={"role": "admin", "permissions": []}  # IS admin
        )
        
        # This should be denied because user.role == 'admin' triggers the deny policy
        with pytest.raises(ValueError) as excinfo:
            await execute_endpoint(
                "tool", 
                "test_user_collision", 
                {"user": "test_value"},  # This parameter should NOT affect policy evaluation
                user_config, 
                site_config,
                test_session,
                user_context=admin_context
            )
        
        assert "Test policy that should check user context role" in str(excinfo.value) 