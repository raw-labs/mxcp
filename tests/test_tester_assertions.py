import pytest
import asyncio
import os
from pathlib import Path
from mxcp.endpoints.tester import run_tests
from mxcp.config.user_config import load_user_config
from mxcp.config.site_config import load_site_config
from mxcp.auth.providers import UserContext


@pytest.fixture(scope="session", autouse=True)
def set_mxcp_config_env():
    """Set environment variable to point to test fixture config"""
    os.environ["MXCP_CONFIG"] = str(Path(__file__).parent / "fixtures" / "tester" / "mxcp-config.yml")
    yield
    if "MXCP_CONFIG" in os.environ:
        del os.environ["MXCP_CONFIG"]


@pytest.fixture
def test_repo_path():
    """Return path to the test tester fixture"""
    return Path(__file__).parent / "fixtures" / "tester"


@pytest.fixture
def user_config(test_repo_path):
    """Load test user configuration"""
    original_dir = os.getcwd()
    os.chdir(test_repo_path)
    try:
        site_config = load_site_config()
        return load_user_config(site_config)
    finally:
        os.chdir(original_dir)


@pytest.fixture
def site_config(test_repo_path):
    """Load test site configuration"""
    original_dir = os.getcwd()
    os.chdir(test_repo_path)
    try:
        return load_site_config()
    finally:
        os.chdir(original_dir)


@pytest.fixture(autouse=True)
def chdir_to_fixtures(test_repo_path):
    """Change to the fixtures directory for each test"""
    original_dir = os.getcwd()
    os.chdir(test_repo_path)
    yield
    os.chdir(original_dir)


@pytest.mark.asyncio
async def test_policy_assertions(user_config, site_config):
    """Test assertions work correctly with policy-filtered results."""
    results = await run_tests("tool", "test_policy_assertions", user_config, site_config, "test")
    
    # All tests should pass
    assert results["status"] == "ok"
    assert results["tests_run"] == 3
    
    # Check individual test results
    tests = results["tests"]
    test_names = {test["name"]: test for test in tests}
    
    # All policy-based tests should pass
    assert test_names["Admin sees all fields"]["status"] == "passed"
    assert test_names["Regular user has filtered fields"]["status"] == "passed"  
    assert test_names["HR sees SSN but needs permission for phone"]["status"] == "passed"


@pytest.mark.asyncio
async def test_assertion_failure_messages(user_config, site_config):
    """Test that assertion failures produce helpful error messages."""
    # Create a test that will fail to check error messages
    # This would require modifying test fixtures to include failing tests
    # For now, we'll just verify the successful cases work
    pass


@pytest.mark.asyncio
async def test_object_assertions(user_config, site_config):
    """Test object assertion types work correctly."""
    results = await run_tests("tool", "test_object_assertions", user_config, site_config, "test")
    
    # All tests should pass
    assert results["status"] == "ok"
    assert results["tests_run"] == 4
    
    # Check individual test results
    tests = results["tests"]
    test_names = {test["name"]: test for test in tests}
    
    # Verify each test passed
    assert test_names["Exact object match"]["status"] == "passed"
    assert test_names["Partial object match"]["status"] == "passed"
    assert test_names["Field exclusion check"]["status"] == "passed"
    assert test_names["Combined assertions"]["status"] == "passed"


@pytest.mark.asyncio
async def test_array_assertions(user_config, site_config):
    """Test array assertion types work correctly."""
    results = await run_tests("tool", "test_array_assertions", user_config, site_config, "test")
    
    # All tests should pass
    assert results["status"] == "ok"
    assert results["tests_run"] == 5
    
    # Check individual test results
    tests = results["tests"]
    test_names = {test["name"]: test for test in tests}
    
    # Verify each test passed
    assert test_names["Array contains specific item"]["status"] == "passed"
    assert test_names["Array contains partial match"]["status"] == "passed"
    assert test_names["Array contains all specified items"]["status"] == "passed"
    assert test_names["Array length check"]["status"] == "passed"
    assert test_names["Filtered array length check"]["status"] == "passed"


@pytest.mark.asyncio
async def test_string_assertions(user_config, site_config):
    """Test string assertion types work correctly."""
    results = await run_tests("tool", "test_string_assertions", user_config, site_config, "test")
    
    # All tests should pass
    assert results["status"] == "ok"
    assert results["tests_run"] == 3
    
    # Check individual test results
    tests = results["tests"]
    test_names = {test["name"]: test for test in tests}
    
    # Verify each test passed
    assert test_names["String contains text"]["status"] == "passed"
    assert test_names["String contains status"]["status"] == "passed"
    assert test_names["Exact string match"]["status"] == "passed"


if __name__ == "__main__":
    pytest.main([__file__, "-v"]) 