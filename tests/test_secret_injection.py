import pytest
from pathlib import Path
from raw.endpoints.executor import EndpointExecutor, EndpointType
import os

@pytest.fixture(scope="session", autouse=True)
def set_raw_config_env():
    os.environ["RAW_CONFIG"] = str(Path(__file__).parent / "fixtures" / "secret-injection" / "raw-config.yml")

@pytest.fixture
def test_repo_path():
    return Path(__file__).parent / "fixtures" / "secret-injection"

@pytest.fixture
def executor(test_repo_path):
    # Change to test repo directory
    original_dir = os.getcwd()
    os.chdir(test_repo_path)
    try:
        executor = EndpointExecutor(EndpointType.TOOL, "secret_test")
        yield executor
    finally:
        os.chdir(original_dir)

def test_secret_injection(executor):
    result = executor.execute({})
    print(result)
    assert result[0][0] == "name=http_auth_token;type=http;provider=config;serializable=true;scope;bearer_token=bearer_token" 