import pytest
from pathlib import Path
from raw.endpoints.executor import EndpointExecutor, EndpointType
from raw.config.user_config import load_user_config
from raw.config.site_config import load_site_config
import os
import yaml

@pytest.fixture(scope="session", autouse=True)
def set_raw_config_env():
    os.environ["RAW_CONFIG"] = str(Path(__file__).parent / "fixtures" / "return-type-validation" / "raw-config.yml")

@pytest.fixture
def test_repo_path():
    """Path to the test repository."""
    return Path(__file__).parent / "fixtures" / "return-type-validation"

@pytest.fixture
def site_config(test_repo_path):
    """Load site config for tests."""
    return load_site_config(test_repo_path)

@pytest.fixture
def user_config(site_config):
    """Load user config for tests."""
    return load_user_config(site_config)

@pytest.fixture
def test_profile():
    """Test profile name."""
    return "test_profile"

@pytest.fixture
def endpoint_file(test_repo_path):
    """Path to the endpoint file."""
    return test_repo_path / "endpoints" / "example.yml"

def modify_return_type(endpoint_file: Path, return_type: str, properties: dict = None):
    """Modify the return type in the endpoint file."""
    with open(endpoint_file) as f:
        endpoint = yaml.safe_load(f)
    
    if return_type == "array":
        endpoint["tool"]["return"] = {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "age": {"type": "integer"}
                }
            }
        }
    elif return_type == "object":
        endpoint["tool"]["return"] = {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "age": {"type": "integer"}
            }
        }
    else:  # scalar type
        endpoint["tool"]["return"] = {
            "type": return_type
        }
    
    with open(endpoint_file, "w") as f:
        yaml.dump(endpoint, f)

@pytest.fixture
def executor(test_repo_path, user_config, site_config, test_profile, endpoint_file):
    """Create an executor for endpoint execution tests."""
    # Change to test repo directory
    original_dir = os.getcwd()
    os.chdir(test_repo_path)
    try:
        executor = EndpointExecutor(EndpointType.TOOL, "example", user_config, site_config, test_profile)
        yield executor
    finally:
        os.chdir(original_dir)

async def test_array_return_type(executor, endpoint_file):
    """Test that array return type works with multiple rows."""
    modify_return_type(endpoint_file, "array")
    executor._load_endpoint()
    output = [
        {"name": "Alice", "age": 30},
        {"name": "Bob", "age": 25}
    ]
    result = await executor.execute({"name": "test", "age": 25})
    assert result == output

async def test_object_return_type(executor, endpoint_file):
    """Test that object return type works with single row."""
    modify_return_type(endpoint_file, "object")
    executor._load_endpoint()
    output = {"name": "Alice", "age": 30}
    result = await executor.execute({"name": "Alice", "age": 30})
    assert result == output

async def test_scalar_return_type(executor, endpoint_file):
    """Test that scalar return type works with single row, single column."""
    modify_return_type(endpoint_file, "number")
    executor._load_endpoint()
    output = 42
    result = await executor.execute({"name": "test", "age": 42})
    assert result == output

async def test_multiple_rows_error(executor, endpoint_file):
    """Test that multiple rows error when return type is not array."""
    modify_return_type(endpoint_file, "object")
    executor._load_endpoint()
    with pytest.raises(ValueError, match="SQL query returned multiple rows"):
        await executor.execute({"name": "test", "age": 25})

async def test_multiple_columns_error(executor, endpoint_file):
    """Test that multiple columns error when return type is scalar."""
    modify_return_type(endpoint_file, "number")
    executor._load_endpoint()
    with pytest.raises(ValueError, match="SQL query returned multiple columns"):
        await executor.execute({"name": "test", "age": 25})

async def test_no_rows_error(executor, endpoint_file):
    """Test that no rows error when return type is not array."""
    modify_return_type(endpoint_file, "object")
    executor._load_endpoint()
    with pytest.raises(ValueError, match="SQL query returned no rows"):
        await executor.execute({"name": "test", "age": 25}) 