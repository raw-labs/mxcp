import pytest
from pathlib import Path
from raw.endpoints.executor import EndpointExecutor, EndpointType
from raw.config.user_config import load_user_config
from raw.config.site_config import load_site_config
import os

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
        return load_user_config()
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
def executor(test_repo_path, user_config, site_config):
    """Create an executor for secret injection tests."""
    # Change to test repo directory
    original_dir = os.getcwd()
    os.chdir(test_repo_path)
    try:
        executor = EndpointExecutor(EndpointType.TOOL, "secret_test", user_config, site_config)
        yield executor
    finally:
        os.chdir(original_dir)

@pytest.fixture
def http_headers_executor(test_repo_path, user_config, site_config):
    """Create an executor for HTTP headers injection tests."""
    # Change to test repo directory
    original_dir = os.getcwd()
    os.chdir(test_repo_path)
    try:
        executor = EndpointExecutor(EndpointType.TOOL, "http_headers_test", user_config, site_config)
        yield executor
    finally:
        os.chdir(original_dir)

def test_secret_injection(executor):
    """Test basic secret injection."""
    result = executor.execute({})
    assert result[0][0] == "name=http_auth_token;type=http;provider=config;serializable=true;scope;bearer_token=bearer_token"

def test_http_headers_injection(http_headers_executor):
    """Test HTTP headers injection."""
    result = http_headers_executor.execute({})
    assert result[0][0] == "name=http_headers_token;type=http;provider=config;serializable=true;scope;extra_http_headers={Authorization=Bearer test_token, X-Custom-Header=custom_value}"
