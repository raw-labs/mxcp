import os
from contextlib import contextmanager
from pathlib import Path

import pytest

from mxcp.server.core.config.site_config import load_site_config
from mxcp.server.core.config.user_config import load_user_config
from mxcp.server.executor.engine import create_runtime_environment

from .helpers import execute_endpoint_with_engine

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
def execution_engine(user_config, site_config, test_repo_path):
    """Create execution engine for tests."""
    runtime_env = create_runtime_environment(user_config, site_config, repo_root=test_repo_path)
    yield runtime_env.execution_engine
    runtime_env.shutdown()


async def test_array_return_type(execution_engine, user_config, site_config, test_repo_path):
    """Test that array return type works with multiple rows."""
    with change_working_dir(test_repo_path):
        expected = [
            {"name": "Alice", "age": 30},
            {"name": "Bob", "age": 25},
            {"name": "test", "age": 25},
        ]
        result = await execute_endpoint_with_engine(
            endpoint_type="tool",
            name="array_endpoint",
            params={"name": "test", "age": 25},
            user_config=user_config,
            site_config=site_config,
            execution_engine=execution_engine,
        )
        assert result == expected


async def test_object_return_type(execution_engine, user_config, site_config, test_repo_path):
    """Test that object return type works with single row."""
    with change_working_dir(test_repo_path):
        expected = {"name": "Alice", "age": 30}
        result = await execute_endpoint_with_engine(
            endpoint_type="tool",
            name="object_endpoint",
            params={"name": "test", "age": 25},
            user_config=user_config,
            site_config=site_config,
            execution_engine=execution_engine,
        )
        assert result == expected


async def test_scalar_return_type(execution_engine, user_config, site_config, test_repo_path):
    """Test that scalar return type works with single row, single column."""
    with change_working_dir(test_repo_path):
        expected = 42
        result = await execute_endpoint_with_engine(
            endpoint_type="tool",
            name="scalar_endpoint",
            params={"value": 42},
            user_config=user_config,
            site_config=site_config,
            execution_engine=execution_engine,
        )
        assert result == expected


async def test_multiple_rows_error(execution_engine, user_config, site_config, test_repo_path):
    """Test that multiple rows error when return type is not array."""
    with change_working_dir(test_repo_path):
        with pytest.raises(ValueError, match="Expected single result for return type"):
            await execute_endpoint_with_engine(
                endpoint_type="tool",
                name="error_endpoint",
                params={"error_type": "multiple_rows"},
                user_config=user_config,
                site_config=site_config,
                execution_engine=execution_engine,
            )


async def test_multiple_columns_error(execution_engine, user_config, site_config, test_repo_path):
    """Test that multiple columns error when return type is scalar."""
    with change_working_dir(test_repo_path):
        with pytest.raises(ValueError, match="Unexpected property: extra"):
            await execute_endpoint_with_engine(
                endpoint_type="tool",
                name="error_endpoint",
                params={"error_type": "multiple_columns"},
                user_config=user_config,
                site_config=site_config,
                execution_engine=execution_engine,
            )


async def test_no_rows_error(execution_engine, user_config, site_config, test_repo_path):
    """Test that no rows error when return type is not array."""
    with change_working_dir(test_repo_path):
        with pytest.raises(ValueError, match="No results returned"):
            await execute_endpoint_with_engine(
                endpoint_type="tool",
                name="error_endpoint",
                params={"error_type": "no_rows"},
                user_config=user_config,
                site_config=site_config,
                execution_engine=execution_engine,
            )


async def test_strict_endpoint_success(execution_engine, user_config, site_config, test_repo_path):
    """Test that strict endpoint succeeds when only allowed columns are present."""
    with change_working_dir(test_repo_path):
        result = await execute_endpoint_with_engine(
            endpoint_type="tool",
            name="strict_endpoint",
            params={},
            user_config=user_config,
            site_config=site_config,
            execution_engine=execution_engine,
        )
        assert result == {"name": "Alice", "age": 30}


async def test_strict_endpoint_extra_failure(
    execution_engine, user_config, site_config, test_repo_path
):
    """Test that strict endpoint fails when extra column is present."""
    with change_working_dir(test_repo_path):
        with pytest.raises(ValueError, match="Unexpected property: extra"):
            await execute_endpoint_with_engine(
                endpoint_type="tool",
                name="strict_endpoint_extra",
                params={},
                user_config=user_config,
                site_config=site_config,
                execution_engine=execution_engine,
            )


async def test_flexible_endpoint_success(
    execution_engine, user_config, site_config, test_repo_path
):
    """Test that flexible endpoint succeeds when extra column is present."""
    with change_working_dir(test_repo_path):
        result = await execute_endpoint_with_engine(
            endpoint_type="tool",
            name="flexible_endpoint",
            params={},
            user_config=user_config,
            site_config=site_config,
            execution_engine=execution_engine,
        )
        assert result == {"name": "Alice", "age": 30, "extra": "extra"}
