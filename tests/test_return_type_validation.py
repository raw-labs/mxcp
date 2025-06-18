import os
from contextlib import contextmanager
from pathlib import Path

import pytest

from mxcp.config.site_config import SiteConfig, load_site_config
from mxcp.config.user_config import UserConfig, load_user_config
from mxcp.endpoints.executor import EndpointExecutor, EndpointType
from mxcp.engine.duckdb_session import DuckDBSession

TEST_REPO_PATH = os.path.join(os.path.dirname(__file__), "fixtures", "return-type-validation")


@contextmanager
def change_working_dir(path):
    """Change working directory temporarily."""
    original_dir = os.getcwd()
    try:
        os.chdir(path)
        yield
    finally:
        os.chdir(original_dir)


@pytest.fixture(scope="session", autouse=True)
def set_mxcp_config_env():
    os.environ["MXCP_CONFIG"] = str(
        Path(__file__).parent / "fixtures" / "return-type-validation" / "mxcp-config.yml"
    )


@pytest.fixture
def test_repo_path():
    """Path to the test repository."""
    return Path(__file__).parent / "fixtures" / "return-type-validation"


@pytest.fixture
def site_config(test_repo_path):
    """Load site config for tests."""
    original_dir = os.getcwd()
    os.chdir(test_repo_path)
    try:
        return load_site_config()
    finally:
        os.chdir(original_dir)


@pytest.fixture
def user_config(test_repo_path):
    """Load user config for tests."""
    original_dir = os.getcwd()
    os.chdir(test_repo_path)
    try:
        site_config = load_site_config()
        return load_user_config(site_config)
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
def array_executor(test_repo_path, user_config, site_config, test_profile, test_session):
    """Create an executor for array endpoint tests."""
    original_dir = os.getcwd()
    os.chdir(test_repo_path)
    try:
        executor = EndpointExecutor(
            EndpointType.TOOL,
            "array_endpoint",
            user_config,
            site_config,
            test_session,
            test_profile,
        )
        yield executor
    finally:
        os.chdir(original_dir)


@pytest.fixture
def object_executor(test_repo_path, user_config, site_config, test_profile, test_session):
    """Create an executor for object endpoint tests."""
    original_dir = os.getcwd()
    os.chdir(test_repo_path)
    try:
        executor = EndpointExecutor(
            EndpointType.TOOL,
            "object_endpoint",
            user_config,
            site_config,
            test_session,
            test_profile,
        )
        yield executor
    finally:
        os.chdir(original_dir)


@pytest.fixture
def scalar_executor(test_repo_path, user_config, site_config, test_profile, test_session):
    """Create an executor for scalar endpoint tests."""
    original_dir = os.getcwd()
    os.chdir(test_repo_path)
    try:
        executor = EndpointExecutor(
            EndpointType.TOOL,
            "scalar_endpoint",
            user_config,
            site_config,
            test_session,
            test_profile,
        )
        yield executor
    finally:
        os.chdir(original_dir)


@pytest.fixture
def error_executor(test_repo_path, user_config, site_config, test_profile, test_session):
    """Create an executor for error endpoint tests."""
    original_dir = os.getcwd()
    os.chdir(test_repo_path)
    try:
        executor = EndpointExecutor(
            EndpointType.TOOL,
            "error_endpoint",
            user_config,
            site_config,
            test_session,
            test_profile,
        )
        yield executor
    finally:
        os.chdir(original_dir)


@pytest.fixture
def strict_executor(test_repo_path, user_config, site_config, test_profile, test_session):
    """Create an executor for strict endpoint tests."""
    original_dir = os.getcwd()
    os.chdir(test_repo_path)
    try:
        executor = EndpointExecutor(
            EndpointType.TOOL,
            "strict_endpoint",
            user_config,
            site_config,
            test_session,
            test_profile,
        )
        yield executor
    finally:
        os.chdir(original_dir)


@pytest.fixture
def strict_extra_executor(test_repo_path, user_config, site_config, test_profile, test_session):
    """Create an executor for strict endpoint with extra column tests."""
    original_dir = os.getcwd()
    os.chdir(test_repo_path)
    try:
        executor = EndpointExecutor(
            EndpointType.TOOL,
            "strict_endpoint_extra",
            user_config,
            site_config,
            test_session,
            test_profile,
        )
        yield executor
    finally:
        os.chdir(original_dir)


@pytest.fixture
def flexible_executor(test_repo_path, user_config, site_config, test_profile, test_session):
    """Create an executor for flexible endpoint tests."""
    original_dir = os.getcwd()
    os.chdir(test_repo_path)
    try:
        executor = EndpointExecutor(
            EndpointType.TOOL,
            "flexible_endpoint",
            user_config,
            site_config,
            test_session,
            test_profile,
        )
        yield executor
    finally:
        os.chdir(original_dir)


async def test_array_return_type(array_executor):
    """Test that array return type works with multiple rows."""
    array_executor._load_endpoint()
    expected = [
        {"name": "Alice", "age": 30},
        {"name": "Bob", "age": 25},
        {"name": "test", "age": 25},
    ]
    result = await array_executor.execute({"name": "test", "age": 25})
    assert result == expected


async def test_object_return_type(object_executor):
    """Test that object return type works with single row."""
    object_executor._load_endpoint()
    expected = {"name": "Alice", "age": 30}
    result = await object_executor.execute({"name": "test", "age": 25})
    assert result == expected


async def test_scalar_return_type(scalar_executor):
    """Test that scalar return type works with single row, single column."""
    scalar_executor._load_endpoint()
    expected = 42
    result = await scalar_executor.execute({"value": 42})
    assert result == expected


async def test_multiple_rows_error(error_executor):
    """Test that multiple rows error when return type is not array."""
    error_executor._load_endpoint()
    with pytest.raises(ValueError, match="SQL query returned multiple rows"):
        await error_executor.execute({"error_type": "multiple_rows"})


async def test_multiple_columns_error(error_executor):
    """Test that multiple columns error when return type is scalar."""
    error_executor._load_endpoint()
    with pytest.raises(ValueError, match="Unexpected property: extra"):
        await error_executor.execute({"error_type": "multiple_columns"})


async def test_no_rows_error(error_executor):
    """Test that no rows error when return type is not array."""
    error_executor._load_endpoint()
    with pytest.raises(ValueError, match="SQL query returned no rows"):
        await error_executor.execute({"error_type": "no_rows"})


async def test_strict_endpoint_success(strict_executor):
    """Test that strict endpoint succeeds when only allowed columns are present."""
    strict_executor._load_endpoint()
    result = await strict_executor.execute({})
    assert result == {"name": "Alice", "age": 30}


async def test_strict_endpoint_extra_failure(strict_extra_executor):
    """Test that strict endpoint fails when extra column is present."""
    strict_extra_executor._load_endpoint()
    with pytest.raises(ValueError, match="Unexpected property: extra"):
        await strict_extra_executor.execute({})


async def test_flexible_endpoint_success(flexible_executor):
    """Test that flexible endpoint succeeds when extra column is present."""
    flexible_executor._load_endpoint()
    result = await flexible_executor.execute({})
    assert result == {"name": "Alice", "age": 30, "extra": "extra"}
