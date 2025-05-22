import pytest
import asyncio
from pathlib import Path
import os
from raw.endpoints.executor import EndpointExecutor, EndpointType
from raw.config.user_config import load_user_config
from raw.config.site_config import load_site_config

@pytest.fixture(scope="session", autouse=True)
def set_raw_config_env():
    os.environ["RAW_CONFIG"] = str(Path(__file__).parent / "fixtures" / "secret-injection" / "raw-config.yml")

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
def executor(test_repo_path, user_config, site_config, test_profile):
    """Create an executor for secret injection tests."""
    # Change to test repo directory
    original_dir = os.getcwd()
    os.chdir(test_repo_path)
    try:
        executor = EndpointExecutor(EndpointType.TOOL, "secret_test", user_config, site_config, test_profile)
        yield executor
    finally:
        os.chdir(original_dir)

@pytest.fixture
def http_headers_executor(test_repo_path, user_config, site_config, test_profile):
    """Create an executor for HTTP headers injection tests."""
    # Change to test repo directory
    original_dir = os.getcwd()
    os.chdir(test_repo_path)
    try:
        executor = EndpointExecutor(EndpointType.TOOL, "http_headers_test", user_config, site_config, test_profile)
        yield executor
    finally:
        os.chdir(original_dir)

@pytest.mark.asyncio
async def test_secret_injection(executor):
    """Test that secrets are properly injected into DuckDB session"""
    executor._load_endpoint()
    result = await executor.execute({})
    assert isinstance(result, dict)
    assert "bearer_token=bearer_token" in result["secret_value"]

@pytest.mark.asyncio
async def test_http_headers_injection(http_headers_executor):
    """Test that HTTP headers are properly injected as MAP type"""
    http_headers_executor._load_endpoint()
    result = await http_headers_executor.execute({})
    assert isinstance(result, dict)
    assert "Authorization=Bearer test_token" in result["secret_value"]
    assert "X-Custom-Header=custom_value" in result["secret_value"]
