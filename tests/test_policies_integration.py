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


class TestPolicyIntegration:
    """Test policy enforcement integration with endpoints."""
    
    @pytest.mark.asyncio
    async def test_guest_access_denied(self, user_config, site_config):
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
                user_context=user_context
            )
        
        assert "Guests cannot access employee information" in str(excinfo.value)
    
    @pytest.mark.asyncio
    async def test_missing_permission_denied(self, user_config, site_config):
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
                user_context=user_context
            )
        
        assert "Missing 'employee.read' permission" in str(excinfo.value)
    
    @pytest.mark.asyncio
    async def test_user_viewing_others_profile_denied(self, user_config, site_config):
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
                user_context=user_context
            )
        
        assert "You can only view your own employee information" in str(excinfo.value)
    
    @pytest.mark.asyncio
    async def test_user_viewing_own_profile(self, user_config, site_config):
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
    async def test_hr_user_access(self, user_config, site_config):
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
            user_context=user_context
        )
        
        assert result2["id"] == "emp456"
        assert result2["name"] == "Jane Smith"
        assert result2["ssn"] == "987-65-4321"  # Real SSN
    
    @pytest.mark.asyncio
    async def test_admin_user_access(self, user_config, site_config):
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
            user_context=user_context
        )
        
        # Admin can see salary
        assert result["salary"] == 85000
        
        # Admin can see phone (has pii.view)
        assert result["phone"] == "555-1234"
        
        # But SSN is still masked (only HR can see unmasked SSN)
        assert result["ssn"] == "****"
    
    @pytest.mark.asyncio
    async def test_user_without_pii_permission(self, user_config, site_config):
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
            user_context=user_context
        )
        
        # HR without pii.view cannot see phone
        assert "phone" not in result
        
        # But can still see unmasked SSN (HR role)
        assert result["ssn"] == "123-45-6789"
    
    @pytest.mark.asyncio
    async def test_anonymous_user_denied(self, user_config, site_config):
        """Test that anonymous users (None context) are handled properly."""
        # Anonymous users have role="anonymous" and no permissions by default
        
        with pytest.raises(ValueError) as excinfo:
            await execute_endpoint(
                "tool", 
                "employee_info", 
                {"employee_id": "emp123"},
                user_config, 
                site_config,
                user_context=None
            )
        
        # Anonymous users should be denied due to missing permissions
        assert "Missing 'employee.read' permission" in str(excinfo.value)


class TestPolicyEnforcementEdgeCases:
    """Test edge cases in policy enforcement."""
    
    @pytest.mark.asyncio
    async def test_multiple_filter_policies(self, user_config, site_config):
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
    async def test_policy_with_complex_conditions(self, user_config, site_config):
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
            user_context=hr_context
        )
        
        assert result["id"] == "emp123"  # HR can view it 