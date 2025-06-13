import os
import pytest
import asyncio
from pathlib import Path
from mxcp.endpoints.tester import run_tests, run_all_tests
from mxcp.config.site_config import load_site_config
from mxcp.config.user_config import load_user_config

@pytest.fixture(scope="session", autouse=True)
def set_mxcp_config_env():
    os.environ["MXCP_CONFIG"] = str(Path(__file__).parent / "fixtures" / "secrets" / "mxcp-config.yml")

@pytest.fixture
def secrets_repo_path():
    """Path to the secrets test repository."""
    return Path(__file__).parent / "fixtures" / "secrets"

@pytest.fixture
def site_config(secrets_repo_path):
    """Load test site configuration."""
    original_dir = os.getcwd()
    os.chdir(secrets_repo_path)
    try:
        return load_site_config()
    finally:
        os.chdir(original_dir)

@pytest.fixture
def user_config(secrets_repo_path):
    """Load test user configuration."""
    original_dir = os.getcwd()
    os.chdir(secrets_repo_path)
    try:
        site_config = load_site_config()
        return load_user_config(site_config)
    finally:
        os.chdir(original_dir)

@pytest.mark.asyncio
async def test_run_secrets_tool(secrets_repo_path, site_config, user_config):
    """Test running tests for the secrets tool endpoint that returns complex DuckDB objects."""
    original_dir = os.getcwd()
    os.chdir(secrets_repo_path)
    try:
        result = await run_tests("tool", "list_secrets", user_config, site_config, None)
        # The test should fail due to serialization issues with complex DuckDB objects
        assert result["status"] == "error"
        assert result["tests_run"] == 1
        # Check that the error is related to serialization of complex objects
        error_msg = str(result["tests"][0]["error"])
        # The error could be about JSON serialization, object not serializable, etc.
        assert any(keyword in error_msg.lower() for keyword in [
            "json", "serial", "not serializable", "object", "array", "dump"
        ]), f"Expected serialization error, but got: {error_msg}"
    finally:
        os.chdir(original_dir)

@pytest.mark.asyncio
async def test_run_all_secrets_tests(secrets_repo_path, site_config, user_config):
    """Test running all tests in the secrets repository (equivalent to 'mxcp test' CLI)."""
    original_dir = os.getcwd()
    os.chdir(secrets_repo_path)
    try:
        result = await run_all_tests(user_config, site_config, None)
        # The overall test run should fail due to the secrets endpoint test failure
        assert result["status"] == "error"
        assert result["tests_run"] > 0
        assert len(result["endpoints"]) > 0
        
        # Find the secrets endpoint in the results
        secrets_endpoint = None
        for endpoint in result["endpoints"]:
            if "list_secrets" in endpoint["endpoint"]:
                secrets_endpoint = endpoint
                break
        
        assert secrets_endpoint is not None, "Could not find list_secrets endpoint in results"
        assert secrets_endpoint["test_results"]["status"] == "error"
        
        # Check that the error is related to serialization of complex DuckDB objects
        test_error = secrets_endpoint["test_results"]["tests"][0]["error"]
        error_msg = str(test_error)
        assert any(keyword in error_msg.lower() for keyword in [
            "json", "serial", "not serializable", "object", "array", "dump"
        ]), f"Expected serialization error, but got: {error_msg}"
        
    finally:
        os.chdir(original_dir) 