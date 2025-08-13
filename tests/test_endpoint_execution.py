import asyncio
import os
from pathlib import Path

import duckdb
import pytest

from mxcp.executor.engine import create_execution_engine
from mxcp.config.site_config import load_site_config
from mxcp.config.user_config import load_user_config
from mxcp.definitions.endpoints.loader import EndpointLoader
from mxcp.services.endpoint_service import execute_endpoint_with_engine


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
def execution_engine(user_config, site_config, test_repo_path):
    """Create execution engine for tests."""
    return create_execution_engine(user_config, site_config, repo_root=test_repo_path)


def test_endpoint_loading(site_config, test_repo_path):
    """Test that endpoint definition is loaded correctly"""
    # Change to test repo directory for relative path resolution
    original_dir = os.getcwd()
    os.chdir(test_repo_path)
    try:
        loader = EndpointLoader(site_config)
        result = loader.load_endpoint("tool", "example")
        assert result is not None
        endpoint_file_path, endpoint_definition = result
        assert endpoint_definition is not None
        assert "tool" in endpoint_definition
        tool_def = endpoint_definition["tool"]
        assert tool_def["name"] == "example"
        assert "parameters" in tool_def
        assert "return" in tool_def
    finally:
        os.chdir(original_dir)


def test_parameter_validation(site_config, test_repo_path):
    """Test parameter validation against schema"""
    # Change to test repo directory for relative path resolution
    original_dir = os.getcwd()
    os.chdir(test_repo_path)
    try:
        # Test valid parameters - this will be validated internally by the execution engine
        valid_params = {
            "name": "test",
            "age": 25,
            "is_active": True,
            "tags": ["tag1", "tag2"],
            "preferences": {"notifications": True, "theme": "dark"},
        }

        # Load endpoint to check schema structure
        loader = EndpointLoader(site_config)
        result = loader.load_endpoint("tool", "example")
        assert result is not None
        endpoint_file_path, endpoint_definition = result
        assert endpoint_definition is not None
        assert "tool" in endpoint_definition
        tool_def = endpoint_definition["tool"]
        assert tool_def is not None

        # Verify the schema has the expected parameter definitions
        parameters = tool_def["parameters"]
        assert parameters is not None
        param_names = [p["name"] for p in parameters]
        assert "name" in param_names
        assert "age" in param_names
        assert "is_active" in param_names
        assert "tags" in param_names
        assert "preferences" in param_names

    finally:
        os.chdir(original_dir)


@pytest.mark.asyncio
async def test_sql_execution(execution_engine, user_config, site_config, test_repo_path):
    """Test SQL execution with parameter conversion"""
    # Change to test repo directory for relative path resolution
    original_dir = os.getcwd()
    os.chdir(test_repo_path)
    try:
        # Test execution with valid parameters
        params = {
            "name": "test",
            "age": 25,
            "is_active": True,
            "tags": ["tag1", "tag2"],
            "preferences": {"notifications": True, "theme": "dark"},
        }

        result = await execute_endpoint_with_engine(
            endpoint_type="tool",
            name="example",
            params=params,
            user_config=user_config,
            site_config=site_config,
            execution_engine=execution_engine,
        )

        # Verify result structure based on the endpoint's return type
        assert result is not None
        if isinstance(result, list):
            assert len(result) > 0
            # Check first row has expected columns
            row = result[0]
            assert "name" in row
            assert "age" in row
            assert "is_active" in row
        elif isinstance(result, dict):
            # Single object return
            assert "name" in result
            assert "age" in result
            assert "is_active" in result
        # Could also be scalar depending on the endpoint's return type

    finally:
        os.chdir(original_dir)
