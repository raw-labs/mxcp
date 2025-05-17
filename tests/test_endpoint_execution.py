import pytest
from pathlib import Path
from raw.endpoints.executor import EndpointExecutor, EndpointType
import duckdb
import os

@pytest.fixture(scope="session", autouse=True)
def set_raw_config_env():
    os.environ["RAW_CONFIG"] = str(Path(__file__).parent / "fixtures" / "test-repo" / "raw-config.yaml")

@pytest.fixture
def test_repo_path():
    return Path(__file__).parent / "fixtures" / "test-repo"

@pytest.fixture
def executor(test_repo_path):
    # Change to test repo directory
    original_dir = os.getcwd()
    os.chdir(test_repo_path)
    try:
        executor = EndpointExecutor(EndpointType.TOOL, "example")
        yield executor
    finally:
        os.chdir(original_dir)

def test_endpoint_loading(executor):
    """Test that endpoint definition is loaded correctly"""
    executor._load_endpoint()
    assert executor.endpoint is not None
    assert executor.endpoint["tool"]["name"] == "example"
    assert "parameters" in executor.endpoint["tool"]
    assert "return" in executor.endpoint["tool"]

def test_parameter_validation(executor):
    """Test parameter validation against schema"""
    executor._load_endpoint()
    
    # Test valid parameters
    valid_params = {
        "name": "test",
        "age": 25,
        "is_active": True,
        "tags": ["tag1", "tag2"],
        "preferences": {
            "notifications": True,
            "theme": "dark"
        }
    }
    executor._validate_parameters(valid_params)
    
    # Test invalid parameters
    with pytest.raises(ValueError):
        executor._validate_parameters({"name": 123})  # Wrong type
    
    with pytest.raises(ValueError):
        executor._validate_parameters({"age": "not a number"})  # Wrong type
    
    with pytest.raises(ValueError):
        executor._validate_parameters({"tags": "not an array"})  # Wrong type

def test_sql_execution(executor):
    """Test SQL execution with parameter conversion"""
    executor._load_endpoint()
    
    # Create test table
    conn = duckdb.connect(":memory:")
    conn.execute("""
        CREATE TABLE users (
            name VARCHAR,
            age INTEGER,
            is_active BOOLEAN,
            tags VARCHAR[],
            preferences JSON
        )
    """)
    
    # Insert test data
    conn.execute("""
        INSERT INTO users VALUES (
            'test',
            25,
            true,
            ['tag1', 'tag2'],
            '{"notifications": true, "theme": "dark"}'
        )
    """)
    
    # Test execution
    params = {
        "name": "test",
        "age": 25,
        "is_active": True,
        "tags": ["tag1", "tag2"],
        "preferences": {
            "notifications": True,
            "theme": "dark"
        }
    }
    
    result = executor.execute(params)
    assert len(result) > 0
    assert result[0][0] == "test"  # name column
    assert result[0][1] == 25      # age column
    assert result[0][2] is True    # is_active column 