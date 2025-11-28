import asyncio
import contextlib
import json
import os
from pathlib import Path
from unittest.mock import AsyncMock, patch

import aiohttp
import pytest

from mxcp.server.definitions.endpoints.models import (
    PromptDefinitionModel,
    ResourceDefinitionModel,
    ToolDefinitionModel,
)
from mxcp.server.interfaces.server.mcp import RAWMCP


@pytest.fixture(scope="session", autouse=True)
def set_mxcp_config_env():
    os.environ["MXCP_CONFIG"] = str(Path(__file__).parent / "fixtures" / "mcp" / "mxcp-config.yml")


@pytest.fixture(scope="module")
def mcp_repo_path():
    """Get path to test repository."""
    return Path(__file__).parent / "fixtures" / "mcp"


@pytest.fixture(autouse=True)
def change_to_mcp_repo(mcp_repo_path):
    original_dir = os.getcwd()
    os.chdir(mcp_repo_path)
    try:
        yield
    finally:
        os.chdir(original_dir)


@pytest.fixture(scope="module")
def mcp_server(mcp_repo_path):
    """Create a RAWMCP instance for testing."""
    original_dir = os.getcwd()
    os.chdir(mcp_repo_path)
    try:
        server = RAWMCP(
            site_config_path=mcp_repo_path,
            stateless_http=True,
            json_response=True,
            host="localhost",
            port=8000,
        )
        os.chdir(original_dir)
        yield server
        with contextlib.suppress(Exception):
            loop = asyncio.new_event_loop()
            try:
                loop.run_until_complete(server.shutdown())
            finally:
                loop.close()
        # Clean up - close the DuckDB session
        if hasattr(server, "db_session") and server.db_session:
            server.db_session.close()
    finally:
        os.chdir(original_dir)


@pytest.fixture
async def http_server(mcp_server):
    """Create a running HTTP server for testing."""
    transport = "streamable-http"
    server_task = asyncio.create_task(mcp_server.run(transport=transport))
    await asyncio.sleep(1)  # Give server time to start
    yield mcp_server
    server_task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await server_task


@pytest.fixture
def mock_endpoint():
    """Create a mock endpoint definition."""
    return {
        "name": "test_tool",
        "parameters": [
            {"name": "str_param", "type": "string"},
            {"name": "int_param", "type": "integer"},
            {"name": "bool_param", "type": "boolean"},
            {"name": "array_param", "type": "array"},
            {"name": "object_param", "type": "object"},
        ],
        "source": {"code": "SELECT 1"},
    }


def test_convert_param_type_string(mcp_server):
    """Test converting parameters to string type."""
    assert mcp_server._convert_param_type(123, "string") == "123"
    assert mcp_server._convert_param_type(True, "string") == "True"
    assert mcp_server._convert_param_type("test", "string") == "test"


def test_convert_param_type_integer(mcp_server):
    """Test converting parameters to integer type."""
    assert mcp_server._convert_param_type("123", "integer") == 123
    assert mcp_server._convert_param_type(123, "integer") == 123
    with pytest.raises(ValueError):
        mcp_server._convert_param_type("not_a_number", "integer")


def test_convert_param_type_boolean(mcp_server):
    """Test converting parameters to boolean type."""
    assert mcp_server._convert_param_type("true", "boolean") is True
    assert mcp_server._convert_param_type("false", "boolean") is False
    assert mcp_server._convert_param_type(True, "boolean") is True
    assert mcp_server._convert_param_type(False, "boolean") is False


def test_convert_param_type_array(mcp_server):
    """Test converting parameters to array type."""
    test_array = [1, 2, 3]
    assert mcp_server._convert_param_type(json.dumps(test_array), "array") == test_array
    assert mcp_server._convert_param_type(test_array, "array") == test_array
    with pytest.raises(ValueError):
        mcp_server._convert_param_type("invalid_json", "array")


def test_convert_param_type_object(mcp_server):
    """Test converting parameters to object type."""
    test_obj = {"key": "value"}
    assert mcp_server._convert_param_type(json.dumps(test_obj), "object") == test_obj
    assert mcp_server._convert_param_type(test_obj, "object") == test_obj
    with pytest.raises(ValueError):
        mcp_server._convert_param_type("invalid_json", "object")


def test_register_tool(mcp_server, mock_endpoint):
    """Test registering a tool endpoint."""
    tool_model = ToolDefinitionModel.model_validate(mock_endpoint)
    with patch.object(mcp_server.mcp, "tool", return_value=lambda f: f):
        mcp_server._register_tool(tool_model)


def test_register_resource(mcp_server):
    """Test registering a resource endpoint."""
    resource_def = {
        "uri": "resource://test/resource",
        "parameters": [{"name": "param1", "type": "string"}],
        "source": {"code": "select 1"},
    }
    resource_model = ResourceDefinitionModel.model_validate(resource_def)
    with patch.object(mcp_server.mcp, "resource", return_value=lambda f: f):
        mcp_server._register_resource(resource_model)


def test_register_prompt(mcp_server, mock_endpoint):
    """Test registering a prompt endpoint."""
    prompt_def = {
        "name": "test_prompt",
        "parameters": [{"name": "name", "type": "string"}],
        "messages": [
            {"role": "system", "type": "text", "prompt": "Say hi"},
            {"role": "user", "type": "text", "prompt": "{{name}}"},
        ],
    }
    prompt_model = PromptDefinitionModel.model_validate(prompt_def)
    with patch.object(mcp_server.mcp, "prompt", return_value=lambda f: f):
        mcp_server._register_prompt(prompt_model)


@pytest.mark.asyncio
async def test_run_http(mcp_server):
    """Test running the server with HTTP transport."""
    with patch.object(
        mcp_server,
        "_run_admin_api_and_transport",
        new_callable=AsyncMock,
    ) as mock_run:
        await mcp_server.run(transport="streamable-http")
        mock_run.assert_awaited_once_with("streamable-http")


@pytest.mark.asyncio
async def test_run_stdio(mcp_server):
    """Test running the server with stdio transport."""
    with patch.object(
        mcp_server,
        "_run_admin_api_and_transport",
        new_callable=AsyncMock,
    ) as mock_run:
        await mcp_server.run(transport="stdio")
        mock_run.assert_awaited_once_with("stdio")


@pytest.mark.asyncio
async def test_invalid_transport(mcp_server):
    """Test running with invalid transport."""
    with pytest.raises(ValueError, match="Unknown transport: invalid"):
        await mcp_server.run(transport="invalid")


def test_parameter_conversion(mcp_server):
    """Test parameter type conversion."""
    # Test string conversion
    assert mcp_server._convert_param_type("123", "string") == "123"

    # Test integer conversion
    assert mcp_server._convert_param_type("123", "integer") == 123

    # Test boolean conversion
    assert mcp_server._convert_param_type("true", "boolean") is True
    assert mcp_server._convert_param_type("false", "boolean") is False

    # Test array conversion
    assert mcp_server._convert_param_type('["a", "b"]', "array") == ["a", "b"]

    # Test object conversion
    assert mcp_server._convert_param_type('{"key": "value"}', "object") == {"key": "value"}

    # Test invalid conversions
    with pytest.raises(ValueError):
        mcp_server._convert_param_type("not_a_number", "integer")

    with pytest.raises(ValueError):
        mcp_server._convert_param_type("not_json", "array")


def test_endpoint_registration(mcp_server):
    """Test endpoint registration."""
    # Register endpoints
    mcp_server.register_endpoints()

    # Verify no endpoints were skipped
    assert len(mcp_server.skipped_endpoints) == 0


@pytest.mark.asyncio
async def test_server_transport(mcp_server):
    """Test server transport options."""
    # Test invalid transport
    with pytest.raises(ValueError, match="Unknown transport: invalid"):
        await mcp_server.run(transport="invalid")

    # Test HTTP transport
    with patch.object(
        mcp_server,
        "_run_admin_api_and_transport",
        new_callable=AsyncMock,
    ) as mock_run:
        await mcp_server.run(transport="streamable-http")
        mock_run.assert_awaited_once_with("streamable-http")


@pytest.mark.skip(
    reason="Incompatible with pytest-asyncio event loop; should be run in a subprocess or integration test harness. TODO: Refactor to subprocess-based integration test."
)
@pytest.mark.asyncio
async def test_server_lifecycle(http_server):
    """Test server startup and shutdown."""
    # Test server is running
    async with aiohttp.ClientSession() as session:
        async with session.get("http://localhost:8000/health") as response:
            assert response.status == 200
            data = await response.json()
            assert data["status"] == "ok"


@pytest.mark.skip(
    reason="Incompatible with pytest-asyncio event loop; should be run in a subprocess or integration test harness. TODO: Refactor to subprocess-based integration test."
)
@pytest.mark.asyncio
async def test_server_shutdown(http_server):
    """Test server shutdown."""
    # Verify server is running
    async with aiohttp.ClientSession() as session:
        async with session.get("http://localhost:8000/health") as response:
            assert response.status == 200
    # Server will be shut down by fixture cleanup
