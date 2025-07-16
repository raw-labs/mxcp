import pytest
import asyncio
from pathlib import Path
import os
from mxcp.endpoints.sdk_executor import execute_endpoint_with_engine
from mxcp.config.execution_engine import create_execution_engine
from mxcp.config.user_config import load_user_config
from mxcp.config.site_config import load_site_config

@pytest.fixture(scope="session", autouse=True)
def set_mxcp_config_env():
    os.environ["MXCP_CONFIG"] = str(Path(__file__).parent / "fixtures" / "secret-injection" / "mxcp-config.yml")

@pytest.fixture
def test_repo_path():
    """Path to the test repository."""
    return Path(__file__).parent / "fixtures" / "secret-injection"

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

@pytest.fixture
def test_profile():
    """Test profile name."""
    return "test_profile"

@pytest.fixture
def execution_engine(user_config, site_config, test_profile):
    """Create execution engine for secret injection tests."""
    engine = create_execution_engine(user_config, site_config, test_profile, readonly=True)
    yield engine
    engine.shutdown()

@pytest.mark.asyncio
async def test_secret_injection(execution_engine, site_config, test_repo_path):
    """Test that secrets are properly injected into DuckDB session"""
    # Change to test repo directory for relative path resolution
    original_dir = os.getcwd()
    os.chdir(test_repo_path)
    try:
        result = await execute_endpoint_with_engine(
            endpoint_type="tool",
            name="secret_test",
            params={},
            site_config=site_config,
            execution_engine=execution_engine
        )
        
        # With return type transformation, this should be a single dict
        assert isinstance(result, dict)
        assert "bearer_token=bearer_token" in result["secret_value"]
    finally:
        os.chdir(original_dir)

@pytest.mark.asyncio
async def test_http_headers_injection(execution_engine, site_config, test_repo_path):
    """Test that HTTP headers are properly injected as MAP type"""
    # Change to test repo directory for relative path resolution
    original_dir = os.getcwd()
    os.chdir(test_repo_path)
    try:
        result = await execute_endpoint_with_engine(
            endpoint_type="tool",
            name="http_headers_test",
            params={},
            site_config=site_config,
            execution_engine=execution_engine
        )
        
        # With return type transformation, this should be a single dict
        assert isinstance(result, dict)
        assert "Authorization=Bearer test_token" in result["secret_value"]
        assert "X-Custom-Header=custom_value" in result["secret_value"]
    finally:
        os.chdir(original_dir)
