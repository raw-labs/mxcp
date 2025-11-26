import os
from pathlib import Path

import pytest

from mxcp.server.core.config.site_config import load_site_config
from mxcp.server.core.config.user_config import load_user_config
from mxcp.server.services.tests.service import run_all_tests, run_tests


@pytest.fixture(scope="session", autouse=True)
def set_mxcp_config_env():
    os.environ["MXCP_CONFIG"] = str(
        Path(__file__).parent / "fixtures" / "tester" / "mxcp-config.yml"
    )


@pytest.fixture
def tester_repo_path():
    """Path to the tester test repository."""
    return Path(__file__).parent / "fixtures" / "tester"


@pytest.fixture
def site_config(tester_repo_path):
    """Load test site configuration."""
    original_dir = os.getcwd()
    os.chdir(tester_repo_path)
    try:
        return load_site_config()
    finally:
        os.chdir(original_dir)


@pytest.fixture
def user_config(tester_repo_path):
    """Load test user configuration."""
    original_dir = os.getcwd()
    os.chdir(tester_repo_path)
    try:
        site_config = load_site_config()
        return load_user_config(site_config)
    finally:
        os.chdir(original_dir)


@pytest.mark.asyncio
async def test_run_valid_tool(tester_repo_path, site_config, user_config):
    """Test running tests for a valid tool endpoint."""
    original_dir = os.getcwd()
    os.chdir(tester_repo_path)
    try:
        result = await run_tests("tool", "valid_tool", user_config, site_config, None)
        assert result.status == "ok"
    finally:
        os.chdir(original_dir)


@pytest.mark.asyncio
async def test_run_invalid_tool(tester_repo_path, site_config, user_config):
    """Test running tests for an invalid tool endpoint."""
    original_dir = os.getcwd()
    os.chdir(tester_repo_path)
    try:
        result = await run_tests("tool", "invalid_tool", user_config, site_config, None)
        assert result.status == "error"
        assert result.tests_run == 4
        assert any(test.status == "passed" for test in result.tests)
        # Check error causes for each error test
        error_msgs = [test.error for test in result.tests if test.status == "error"]
        assert any("Required parameter missing: count" in str(msg) for msg in error_msgs)
        assert any(
            "Error validating parameter 'count'" in str(msg)
            and "Expected integer, got str" in str(msg)
            for msg in error_msgs
        )
        assert any("Unknown parameter: extra" in str(msg) for msg in error_msgs)
    finally:
        os.chdir(original_dir)


@pytest.mark.asyncio
async def test_run_valid_resource(tester_repo_path, site_config, user_config):
    """Test running tests for a valid resource endpoint."""
    original_dir = os.getcwd()
    os.chdir(tester_repo_path)
    try:
        result = await run_tests(
            "resource", "data://valid.resource", user_config, site_config, None
        )
        assert result.status == "error"  # Overall status is error because of the failing test
        assert result.tests_run == 2
        assert any(
            test.status == "passed" for test in result.tests
        )  # valid filter test should pass
        assert any(test.status == "error" for test in result.tests)  # no filter test should error
        # Check error cause for the error test
        error_msgs = [test.error for test in result.tests if test.status == "error"]
        assert any("Required parameter missing: filter" in str(msg) for msg in error_msgs)
    finally:
        os.chdir(original_dir)


@pytest.mark.asyncio
async def test_run_valid_prompt(tester_repo_path, site_config, user_config):
    """Test running tests for a valid prompt endpoint."""
    original_dir = os.getcwd()
    os.chdir(tester_repo_path)
    try:
        result = await run_tests("prompt", "valid_prompt", user_config, site_config, None)
        # The tests should fail because the prompt returns a transformed string result
        # but the test expects the raw SQL result format
        assert result.status == "failed"
        assert result.tests_run == 2
        assert all(test.status == "failed" for test in result.tests)
    finally:
        os.chdir(original_dir)


@pytest.mark.asyncio
async def test_run_nonexistent_endpoint(tester_repo_path, site_config, user_config):
    """Test running tests for a non-existent endpoint."""
    original_dir = os.getcwd()
    os.chdir(tester_repo_path)
    try:
        result = await run_tests("tool", "nonexistent", user_config, site_config, None)
        assert result.status == "error"
        assert result.message is not None and "Endpoint not found" in result.message
    finally:
        os.chdir(original_dir)


@pytest.mark.asyncio
async def test_run_all_tests(tester_repo_path, site_config, user_config):
    """Test running all tests."""
    original_dir = os.getcwd()
    os.chdir(tester_repo_path)
    try:
        result = await run_all_tests(user_config, site_config, None)
        assert result.status == "error"
        assert result.tests_run > 0
        assert len(result.endpoints) > 0
        # Check that we have results for all endpoint types
        endpoint_types = {e.endpoint.split("/")[0] for e in result.endpoints}
        assert "tool" in endpoint_types
        assert "resource" in endpoint_types
        assert "prompt" in endpoint_types
        # Optionally, check that at least one error cause is present in endpoints
        error_causes = [
            test.error
            for ep in result.endpoints
            for test in (ep.test_results.tests or [])
            if test.status == "error"
        ]
        assert any(
            "Required parameter missing" in str(msg)
            or "messages" in str(msg)
            or "Unknown parameter" in str(msg)
            for msg in error_causes
        )
    finally:
        os.chdir(original_dir)


@pytest.mark.asyncio
async def test_run_missing_param_tool(tester_repo_path, site_config, user_config):
    """Test running tests for a tool endpoint missing a required parameter."""
    original_dir = os.getcwd()
    os.chdir(tester_repo_path)
    try:
        result = await run_tests("tool", "missing_param_tool", user_config, site_config, None)
        assert result.status == "error"
        assert "Required parameter missing: count" in str(result.tests[0].error)
    finally:
        os.chdir(original_dir)


@pytest.mark.asyncio
async def test_run_mismatched_result(tester_repo_path, site_config, user_config):
    """Test running tests for a tool endpoint with mismatched expected result."""
    original_dir = os.getcwd()
    os.chdir(tester_repo_path)
    try:
        result = await run_tests("tool", "mismatched_result", user_config, site_config, None)
        assert result.status == "failed"  # Overall status should be failed
    finally:
        os.chdir(original_dir)
