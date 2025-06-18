import pytest
import asyncio
from pathlib import Path
from mxcp.endpoints.executor import EndpointExecutor, EndpointType
from mxcp.config.user_config import load_user_config
from mxcp.config.site_config import load_site_config
from mxcp.engine.duckdb_session import DuckDBSession
import duckdb
import os


@pytest.fixture(scope="session", autouse=True)
def set_mxcp_config_env():
    os.environ["MXCP_CONFIG"] = str(
        Path(__file__).parent / "fixtures" / "endpoint-execution" / "mxcp-config.yml"
    )


@pytest.fixture
def test_repo_path():
    """Path to the test repository."""
    return Path(__file__).parent / "fixtures" / "endpoint-execution"


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
def test_session(user_config, site_config, test_profile):
    """Create a test DuckDB session."""
    session = DuckDBSession(user_config, site_config, test_profile, readonly=True)
    yield session
    session.close()


@pytest.fixture
def executor(test_repo_path, user_config, site_config, test_profile, test_session):
    """Create an executor for endpoint execution tests."""
    # Change to test repo directory
    original_dir = os.getcwd()
    os.chdir(test_repo_path)
    try:
        executor = EndpointExecutor(
            EndpointType.TOOL, "example", user_config, site_config, test_session, test_profile
        )
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
        "preferences": {"notifications": True, "theme": "dark"},
    }
    executor._validate_parameters(valid_params)

    # Test invalid parameters
    with pytest.raises(ValueError):
        executor._validate_parameters({"name": 123})  # Wrong type

    with pytest.raises(ValueError):
        executor._validate_parameters({"age": "not a number"})  # Wrong type

    with pytest.raises(ValueError):
        executor._validate_parameters({"tags": "not an array"})  # Wrong type


@pytest.mark.asyncio
async def test_sql_execution(executor):
    """Test SQL execution with parameter conversion"""
    executor._load_endpoint()

    # Create test table
    conn = duckdb.connect(":memory:")
    conn.execute(
        """
        CREATE TABLE users (
            name VARCHAR,
            age INTEGER,
            is_active BOOLEAN,
            tags VARCHAR[],
            preferences JSON
        )
    """
    )

    # Insert test data
    conn.execute(
        """
        INSERT INTO users VALUES (
            'test',
            25,
            true,
            ['tag1', 'tag2'],
            '{"notifications": true, "theme": "dark"}'
        )
    """
    )

    # Test execution
    params = {
        "name": "test",
        "age": 25,
        "is_active": True,
        "tags": ["tag1", "tag2"],
        "preferences": {"notifications": True, "theme": "dark"},
    }

    result = await executor.execute(params)
    assert len(result) > 0
    assert result[0]["name"] == "test"  # name column
    assert result[0]["age"] == 25  # age column
    assert result[0]["is_active"] is True  # is_active column
