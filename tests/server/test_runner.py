import os
from pathlib import Path

import pytest

from mxcp.server.core.config.site_config import load_site_config
from mxcp.server.core.config.user_config import load_user_config
from mxcp.server.services.endpoints import execute_endpoint


@pytest.fixture(scope="session", autouse=True)
def set_mxcp_config_env():
    os.environ["MXCP_CONFIG"] = str(
        Path(__file__).parent / "fixtures" / "runner" / "mxcp-config.yml"
    )


@pytest.fixture
def test_repo_path():
    """Path to the test repository."""
    return Path(__file__).parent / "fixtures" / "runner"


@pytest.fixture
def test_user_config(test_repo_path):
    """Load test user configuration."""
    original_dir = os.getcwd()
    os.chdir(test_repo_path)
    try:
        site_config = load_site_config()
        return load_user_config(site_config)
    finally:
        os.chdir(original_dir)


@pytest.fixture
def test_site_config(test_repo_path):
    """Load test site configuration."""
    original_dir = os.getcwd()
    os.chdir(test_repo_path)
    try:
        return load_site_config()
    finally:
        os.chdir(original_dir)


@pytest.fixture
def test_profile():
    return "test_profile"


@pytest.mark.asyncio
async def test_simple_tool_success(
    test_repo_path, test_user_config, test_site_config, test_profile
):
    """Test successful tool execution"""
    original_dir = os.getcwd()
    os.chdir(test_repo_path)
    try:
        endpoint_type = "tool"
        name = "simple_tool"
        args = {"a": 1, "b": 2}
        result = await execute_endpoint(
            endpoint_type, name, args, test_user_config, test_site_config, test_profile
        )
        assert result == 3.0
    finally:
        os.chdir(original_dir)


@pytest.mark.asyncio
async def test_simple_tool_missing_arg(
    test_repo_path, test_user_config, test_site_config, test_profile
):
    """Test tool execution with missing required argument"""
    original_dir = os.getcwd()
    os.chdir(test_repo_path)
    try:
        endpoint_type = "tool"
        name = "simple_tool"
        args = {"a": 1}  # Missing 'b'
        with pytest.raises(ValueError) as exc_info:
            await execute_endpoint(
                endpoint_type, name, args, test_user_config, test_site_config, test_profile
            )
        assert "Required parameter missing: b" in str(exc_info.value)
    finally:
        os.chdir(original_dir)


@pytest.mark.asyncio
async def test_simple_tool_wrong_type(
    test_repo_path, test_user_config, test_site_config, test_profile
):
    """Test tool execution with wrong argument type"""
    original_dir = os.getcwd()
    os.chdir(test_repo_path)
    try:
        endpoint_type = "tool"
        name = "simple_tool"
        args = {"a": "not_a_number", "b": 2}
        with pytest.raises(ValueError) as exc_info:
            await execute_endpoint(
                endpoint_type, name, args, test_user_config, test_site_config, test_profile
            )
        assert "Expected number, got str" in str(exc_info.value)
    finally:
        os.chdir(original_dir)


@pytest.mark.asyncio
async def test_date_resource_success(
    test_repo_path, test_user_config, test_site_config, test_profile
):
    """Test successful resource execution"""
    original_dir = os.getcwd()
    os.chdir(test_repo_path)
    try:
        endpoint_type = "resource"
        name = "data://date.resource"
        args = {"date": "2024-03-20", "format": "iso"}
        result = await execute_endpoint(
            endpoint_type, name, args, test_user_config, test_site_config, test_profile
        )
        assert result == {"date": "2024-03-20", "format": "iso"}
    finally:
        os.chdir(original_dir)


@pytest.mark.asyncio
async def test_date_resource_invalid_date(
    test_repo_path, test_user_config, test_site_config, test_profile
):
    """Test resource execution with invalid date format"""
    original_dir = os.getcwd()
    os.chdir(test_repo_path)
    try:
        endpoint_type = "resource"
        name = "data://date.resource"
        args = {"date": "not-a-date", "format": "iso"}
        with pytest.raises(ValueError) as exc_info:
            await execute_endpoint(
                endpoint_type, name, args, test_user_config, test_site_config, test_profile
            )
        assert "time data 'not-a-date' does not match format" in str(exc_info.value)
    finally:
        os.chdir(original_dir)


@pytest.mark.asyncio
async def test_date_resource_invalid_format(
    test_repo_path, test_user_config, test_site_config, test_profile
):
    """Test resource execution with invalid format enum value"""
    original_dir = os.getcwd()
    os.chdir(test_repo_path)
    try:
        endpoint_type = "resource"
        name = "data://date.resource"
        args = {"date": "2024-03-20", "format": "invalid_format"}
        with pytest.raises(ValueError) as exc_info:
            await execute_endpoint(
                endpoint_type, name, args, test_user_config, test_site_config, test_profile
            )
        assert "Must be one of: ['iso', 'unix', 'human']" in str(exc_info.value)
    finally:
        os.chdir(original_dir)


@pytest.mark.asyncio
async def test_greeting_prompt_success(
    test_repo_path, test_user_config, test_site_config, test_profile
):
    """Test successful prompt execution"""
    original_dir = os.getcwd()
    os.chdir(test_repo_path)
    try:
        endpoint_type = "prompt"
        name = "greeting_prompt"
        args = {"name": "World", "time_of_day": "morning"}
        result = await execute_endpoint(
            endpoint_type, name, args, test_user_config, test_site_config, test_profile
        )
        assert len(result) == 2
        assert result[0]["role"] == "system"
        assert result[1]["role"] == "user"
        assert "Good morning, World!" in result[1]["prompt"]
    finally:
        os.chdir(original_dir)


@pytest.mark.asyncio
async def test_greeting_prompt_default_value(
    test_repo_path, test_user_config, test_site_config, test_profile
):
    """Test prompt execution with default value"""
    original_dir = os.getcwd()
    os.chdir(test_repo_path)
    try:
        endpoint_type = "prompt"
        name = "greeting_prompt"
        args = {"name": "Alice"}  # time_of_day should default to "morning"
        result = await execute_endpoint(
            endpoint_type, name, args, test_user_config, test_site_config, test_profile
        )
        assert len(result) == 2
        assert result[0]["role"] == "system"
        assert result[1]["role"] == "user"
        assert "Good morning, Alice!" in result[1]["prompt"]
    finally:
        os.chdir(original_dir)


@pytest.mark.asyncio
async def test_greeting_prompt_name_too_long(
    test_repo_path, test_user_config, test_site_config, test_profile
):
    """Test prompt execution with name exceeding maxLength"""
    original_dir = os.getcwd()
    os.chdir(test_repo_path)
    try:
        endpoint_type = "prompt"
        name = "greeting_prompt"
        args = {"name": "A" * 51, "time_of_day": "morning"}  # 51 chars > maxLength 50
        with pytest.raises(ValueError) as exc_info:
            await execute_endpoint(
                endpoint_type, name, args, test_user_config, test_site_config, test_profile
            )
        assert "String must be at most 50 characters long" in str(exc_info.value)
    finally:
        os.chdir(original_dir)


@pytest.mark.asyncio
async def test_nonexistent_endpoint(
    test_repo_path, test_user_config, test_site_config, test_profile
):
    """Test execution of a non-existent endpoint"""
    original_dir = os.getcwd()
    os.chdir(test_repo_path)
    try:
        endpoint_type = "tool"
        name = "nonexistent"
        args = {}
        with pytest.raises(FileNotFoundError) as exc_info:
            await execute_endpoint(
                endpoint_type, name, args, test_user_config, test_site_config, test_profile
            )
        assert "not found" in str(exc_info.value)
    finally:
        os.chdir(original_dir)


@pytest.mark.asyncio
async def test_invalid_endpoint_yaml(
    test_repo_path, test_user_config, test_site_config, test_profile
):
    """Test execution of an endpoint with invalid YAML"""
    original_dir = os.getcwd()
    os.chdir(test_repo_path)
    try:
        endpoint_type = "tool"
        name = "invalid"
        invalid_path = Path("tools/invalid.yml")
        with open(invalid_path, "w") as f:
            f.write("invalid: yaml: content: [")
        try:
            args = {}
            with pytest.raises(FileNotFoundError) as exc_info:
                await execute_endpoint(
                    endpoint_type, name, args, test_user_config, test_site_config, test_profile
                )
            assert "not found" in str(exc_info.value)
        finally:
            invalid_path.unlink(missing_ok=True)
    finally:
        os.chdir(original_dir)


@pytest.mark.asyncio
async def test_greeting_prompt_missing_required_param(
    test_repo_path, test_user_config, test_site_config, test_profile
):
    """Test prompt execution with missing required parameter"""
    original_dir = os.getcwd()
    os.chdir(test_repo_path)
    try:
        endpoint_type = "prompt"
        name = "greeting_prompt"
        args = {"time_of_day": "morning"}  # Missing required 'name' parameter
        with pytest.raises(ValueError) as exc_info:
            await execute_endpoint(
                endpoint_type, name, args, test_user_config, test_site_config, test_profile
            )
        assert "Required parameter missing: name" in str(exc_info.value)
    finally:
        os.chdir(original_dir)


@pytest.mark.asyncio
async def test_valid_prompt_success(
    test_repo_path, test_user_config, test_site_config, test_profile
):
    """Test successful prompt execution with valid prompt"""
    original_dir = os.getcwd()
    os.chdir(test_repo_path)
    try:
        endpoint_type = "prompt"
        name = "valid_prompt"
        args = {"topic": "quantum computing", "expertise_level": "intermediate"}
        result = await execute_endpoint(
            endpoint_type, name, args, test_user_config, test_site_config, test_profile
        )
        assert len(result) == 2  # System and user messages
        assert result[0]["role"] == "system"
        assert result[1]["role"] == "user"
        assert "quantum computing" in result[1]["prompt"]
        assert "intermediate" in result[1]["prompt"]
    finally:
        os.chdir(original_dir)


@pytest.mark.asyncio
async def test_valid_prompt_default_value(
    test_repo_path, test_user_config, test_site_config, test_profile
):
    """Test prompt execution with default value for valid prompt"""
    original_dir = os.getcwd()
    os.chdir(test_repo_path)
    try:
        endpoint_type = "prompt"
        name = "valid_prompt"
        args = {"topic": "machine learning"}  # expertise_level defaults to "beginner"
        result = await execute_endpoint(
            endpoint_type, name, args, test_user_config, test_site_config, test_profile
        )
        assert len(result) == 2
        assert result[0]["role"] == "system"
        assert result[1]["role"] == "user"
        assert "machine learning" in result[1]["prompt"]
        assert "beginner" in result[1]["prompt"]
    finally:
        os.chdir(original_dir)


@pytest.mark.asyncio
async def test_headers_tool_with_headers(
    test_repo_path, test_user_config, test_site_config, test_profile
):
    """Test headers tool execution with request headers provided"""
    original_dir = os.getcwd()
    os.chdir(test_repo_path)
    try:
        endpoint_type = "tool"
        name = "headers"
        args = {}
        request_headers = {
            "Authorization": "Bearer test-token",
            "Content-Type": "application/json",
            "X-Custom-Header": "custom-value",
        }
        result = await execute_endpoint(
            endpoint_type,
            name,
            args,
            test_user_config,
            test_site_config,
            test_profile,
            request_headers=request_headers,
        )
        # The headers tool should return the request headers
        assert result == request_headers
        assert result["Authorization"] == "Bearer test-token"
        assert result["Content-Type"] == "application/json"
        assert result["X-Custom-Header"] == "custom-value"
    finally:
        os.chdir(original_dir)


@pytest.mark.asyncio
async def test_headers_tool_without_headers(
    test_repo_path, test_user_config, test_site_config, test_profile
):
    """Test headers tool execution without request headers"""
    original_dir = os.getcwd()
    os.chdir(test_repo_path)
    try:
        endpoint_type = "tool"
        name = "headers"
        args = {}
        result = await execute_endpoint(
            endpoint_type, name, args, test_user_config, test_site_config, test_profile
        )
        # When no headers are provided, the result should be None
        assert result is None
    finally:
        os.chdir(original_dir)
