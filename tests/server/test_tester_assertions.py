import asyncio
import os
from pathlib import Path

import pytest

from mxcp.server.core.config.site_config import load_site_config
from mxcp.server.core.config.user_config import load_user_config
from mxcp.server.services.tests import run_tests
from mxcp.sdk.auth import UserContext


@pytest.fixture(scope="session", autouse=True)
def set_mxcp_config_env():
    """Set environment variable to point to test fixture config"""
    os.environ["MXCP_CONFIG"] = str(
        Path(__file__).parent / "fixtures" / "tester" / "mxcp-config.yml"
    )
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


@pytest.mark.asyncio
async def test_result_contains_assertions(user_config, site_config):
    """Test result_contains assertion with various data types including primitives."""
    results = await run_tests(
        "prompt", "test_result_contains_primitives", user_config, site_config, "test"
    )

    # All tests should pass
    assert results["status"] == "ok"
    assert results["tests_run"] == 6

    # Check individual test results
    tests = results["tests"]
    test_names = {test["name"]: test for test in tests}

    # Verify all tests passed
    assert test_names["String array contains banana"]["status"] == "passed"
    assert test_names["Number array contains 3"]["status"] == "passed"
    assert test_names["Mixed array contains true"]["status"] == "passed"
    assert test_names["Mixed array contains null"]["status"] == "passed"
    assert test_names["Dict contains name John"]["status"] == "passed"
    assert test_names["Dict array contains Bob"]["status"] == "passed"


@pytest.mark.asyncio
async def test_result_contains_error_messages(user_config, site_config):
    """Test that result_contains assertion produces correct error messages."""
    results = await run_tests(
        "prompt", "test_result_contains_failures_prompt", user_config, site_config, "test"
    )

    # All tests should fail (they're designed to)
    assert results["status"] == "failed"
    assert results["tests_run"] == 7

    # Check individual test results and error messages
    tests = results["tests"]
    test_names = {test["name"]: test for test in tests}

    # Test 1: Array missing primitive
    assert test_names["Array missing primitive value"]["status"] == "failed"
    assert (
        "Array does not contain expected value: grape"
        in test_names["Array missing primitive value"]["error"]
    )

    # Test 2: Dict missing field
    assert test_names["Dict missing field"]["status"] == "failed"
    assert "Expected field 'email' not found in result" in test_names["Dict missing field"]["error"]

    # Test 3: Dict field wrong value
    assert test_names["Dict field wrong value"]["status"] == "failed"
    assert "Field 'age' has value 25, expected 30" in test_names["Dict field wrong value"]["error"]

    # Test 4: Array of dicts no match
    assert test_names["Array of dicts no match"]["status"] == "failed"
    assert (
        "No item in array contains the expected fields"
        in test_names["Array of dicts no match"]["error"]
    )

    # Test 5: Wrong result type
    assert test_names["String result with dict pattern"]["status"] == "failed"
    assert (
        "result_contains assertion requires dict or array result"
        in test_names["String result with dict pattern"]["error"]
    )

    # Test 6: Empty array
    assert test_names["Empty array check"]["status"] == "failed"
    assert (
        "Array does not contain expected value: anything"
        in test_names["Empty array check"]["error"]
    )

    # Test 7: Number array missing value
    assert test_names["Number array missing value"]["status"] == "failed"
    assert (
        "Array does not contain expected value: 10"
        in test_names["Number array missing value"]["error"]
    )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
