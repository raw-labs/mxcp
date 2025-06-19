import asyncio
import os
from pathlib import Path

import pytest

from mxcp.config.site_config import load_site_config
from mxcp.config.user_config import load_user_config
from mxcp.endpoints.runner import run_endpoint
from mxcp.engine.duckdb_session import DuckDBSession


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


@pytest.fixture
def test_session(test_user_config, test_site_config, test_profile):
    """Create a test DuckDB session."""
    session = DuckDBSession(test_user_config, test_site_config, test_profile, readonly=True)
    yield session
    session.close()


@pytest.mark.asyncio
async def test_simple_tool_success(
    test_repo_path, test_user_config, test_site_config, test_profile, test_session
):
    """Test successful execution of a simple tool endpoint"""
    original_dir = os.getcwd()
    os.chdir(test_repo_path)
    try:
        endpoint_type = "tool"
        name = "simple_tool"
        args = {"a": 1, "b": 2}
        result = await run_endpoint(
            endpoint_type,
            name,
            args,
            test_user_config,
            test_site_config,
            test_session,
            test_profile,
        )
        assert result == 3
    finally:
        os.chdir(original_dir)


@pytest.mark.asyncio
async def test_simple_tool_missing_arg(
    test_repo_path, test_user_config, test_site_config, test_profile, test_session
):
    """Test tool execution with missing required argument"""
    original_dir = os.getcwd()
    os.chdir(test_repo_path)
    try:
        endpoint_type = "tool"
        name = "simple_tool"
        args = {"a": 1}  # Missing 'b'
        with pytest.raises(RuntimeError) as exc_info:
            await run_endpoint(
                endpoint_type,
                name,
                args,
                test_user_config,
                test_site_config,
                test_session,
                test_profile,
            )
        assert "Required parameter missing" in str(exc_info.value)
    finally:
        os.chdir(original_dir)


@pytest.mark.asyncio
async def test_simple_tool_wrong_type(
    test_repo_path, test_user_config, test_site_config, test_profile, test_session
):
    """Test tool execution with wrong argument type"""
    original_dir = os.getcwd()
    os.chdir(test_repo_path)
    try:
        endpoint_type = "tool"
        name = "simple_tool"
        args = {"a": "not_a_number", "b": 2}
        with pytest.raises(RuntimeError) as exc_info:
            await run_endpoint(
                endpoint_type,
                name,
                args,
                test_user_config,
                test_site_config,
                test_session,
                test_profile,
            )
        assert "Error converting parameter" in str(exc_info.value)
    finally:
        os.chdir(original_dir)


@pytest.mark.asyncio
async def test_date_resource_success(
    test_repo_path, test_user_config, test_site_config, test_profile, test_session
):
    """Test successful execution of a date resource endpoint"""
    original_dir = os.getcwd()
    os.chdir(test_repo_path)
    try:
        endpoint_type = "resource"
        name = "data://date.resource"
        args = {"date": "2024-03-20", "format": "human"}
        result = await run_endpoint(
            endpoint_type,
            name,
            args,
            test_user_config,
            test_site_config,
            test_session,
            test_profile,
        )
        assert result["date"] == "March 20, 2024"
        assert result["format"] == "human"
    finally:
        os.chdir(original_dir)


@pytest.mark.asyncio
async def test_date_resource_invalid_date(
    test_repo_path, test_user_config, test_site_config, test_profile, test_session
):
    """Test resource execution with invalid date format"""
    original_dir = os.getcwd()
    os.chdir(test_repo_path)
    try:
        endpoint_type = "resource"
        name = "data://date.resource"
        args = {"date": "not-a-date", "format": "iso"}
        with pytest.raises(RuntimeError) as exc_info:
            await run_endpoint(
                endpoint_type,
                name,
                args,
                test_user_config,
                test_site_config,
                test_session,
                test_profile,
            )
        assert "Error converting parameter" in str(exc_info.value)
    finally:
        os.chdir(original_dir)


@pytest.mark.asyncio
async def test_date_resource_invalid_format(
    test_repo_path, test_user_config, test_site_config, test_profile, test_session
):
    """Test resource execution with invalid format enum value"""
    original_dir = os.getcwd()
    os.chdir(test_repo_path)
    try:
        endpoint_type = "resource"
        name = "data://date.resource"
        args = {"date": "2024-03-20", "format": "invalid_format"}
        with pytest.raises(RuntimeError) as exc_info:
            await run_endpoint(
                endpoint_type,
                name,
                args,
                test_user_config,
                test_site_config,
                test_session,
                test_profile,
            )
        assert "Invalid value for format" in str(exc_info.value)
    finally:
        os.chdir(original_dir)


@pytest.mark.asyncio
async def test_greeting_prompt_success(
    test_repo_path, test_user_config, test_site_config, test_profile, test_session
):
    """Test successful execution of a greeting prompt endpoint"""
    original_dir = os.getcwd()
    os.chdir(test_repo_path)
    try:
        endpoint_type = "prompt"
        name = "greeting_prompt"
        args = {"name": "Alice", "time_of_day": "afternoon"}
        result = await run_endpoint(
            endpoint_type,
            name,
            args,
            test_user_config,
            test_site_config,
            test_session,
            test_profile,
        )
        assert len(result) == 2  # Two messages
        # Verify system message
        assert result[0]["role"] == "system"
        assert result[0]["type"] == "text"
        assert result[0]["prompt"] == "You are a friendly greeter."
        # Verify user message
        assert result[1]["role"] == "user"
        assert result[1]["type"] == "text"
        assert "Good afternoon, Alice!" in result[1]["prompt"]
        assert "wonderful afternoon" in result[1]["prompt"]
    finally:
        os.chdir(original_dir)


@pytest.mark.asyncio
async def test_greeting_prompt_default_value(
    test_repo_path, test_user_config, test_site_config, test_profile, test_session
):
    """Test prompt execution with default time_of_day value"""
    original_dir = os.getcwd()
    os.chdir(test_repo_path)
    try:
        endpoint_type = "prompt"
        name = "greeting_prompt"
        args = {"name": "Bob"}  # time_of_day defaults to "morning"
        result = await run_endpoint(
            endpoint_type,
            name,
            args,
            test_user_config,
            test_site_config,
            test_session,
            test_profile,
        )
        assert len(result) == 2  # Two messages
        assert "Good morning, Bob!" in result[1]["prompt"]
    finally:
        os.chdir(original_dir)


@pytest.mark.asyncio
async def test_greeting_prompt_name_too_long(
    test_repo_path, test_user_config, test_site_config, test_profile, test_session
):
    """Test prompt execution with name exceeding maxLength"""
    original_dir = os.getcwd()
    os.chdir(test_repo_path)
    try:
        endpoint_type = "prompt"
        name = "greeting_prompt"
        args = {"name": "A" * 51, "time_of_day": "morning"}  # 51 chars > maxLength 50
        with pytest.raises(RuntimeError) as exc_info:
            await run_endpoint(
                endpoint_type,
                name,
                args,
                test_user_config,
                test_site_config,
                test_session,
                test_profile,
            )
        assert "String must be at most 50 characters long" in str(exc_info.value)
    finally:
        os.chdir(original_dir)


@pytest.mark.asyncio
async def test_nonexistent_endpoint(
    test_repo_path, test_user_config, test_site_config, test_profile, test_session
):
    """Test execution of a non-existent endpoint"""
    original_dir = os.getcwd()
    os.chdir(test_repo_path)
    try:
        endpoint_type = "tool"
        name = "nonexistent"
        args = {}
        with pytest.raises(RuntimeError) as exc_info:
            await run_endpoint(
                endpoint_type,
                name,
                args,
                test_user_config,
                test_site_config,
                test_session,
                test_profile,
            )
        assert "not found" in str(exc_info.value)
    finally:
        os.chdir(original_dir)


@pytest.mark.asyncio
async def test_invalid_endpoint_yaml(
    test_repo_path, test_user_config, test_site_config, test_profile, test_session
):
    """Test execution of an endpoint with invalid YAML"""
    original_dir = os.getcwd()
    os.chdir(test_repo_path)
    try:
        endpoint_type = "tool"
        name = "invalid"
        invalid_path = Path("endpoints/invalid.yml")
        with open(invalid_path, "w") as f:
            f.write("invalid: yaml: content: [")
        try:
            args = {}
            with pytest.raises(RuntimeError) as exc_info:
                await run_endpoint(
                    endpoint_type,
                    name,
                    args,
                    test_user_config,
                    test_site_config,
                    test_session,
                    test_profile,
                )
            assert "Error running endpoint" in str(exc_info.value)
        finally:
            invalid_path.unlink()
    finally:
        os.chdir(original_dir)


@pytest.mark.asyncio
async def test_greeting_prompt_missing_required_param(
    test_repo_path, test_user_config, test_site_config, test_profile, test_session
):
    """Test prompt execution with missing required parameter"""
    original_dir = os.getcwd()
    os.chdir(test_repo_path)
    try:
        endpoint_type = "prompt"
        name = "greeting_prompt"
        args = {"time_of_day": "morning"}  # Missing required 'name' parameter
        with pytest.raises(RuntimeError) as exc_info:
            await run_endpoint(
                endpoint_type,
                name,
                args,
                test_user_config,
                test_site_config,
                test_session,
                test_profile,
            )
        assert "Required parameter missing" in str(exc_info.value)
    finally:
        os.chdir(original_dir)


@pytest.mark.asyncio
async def test_valid_prompt_success(
    test_repo_path, test_user_config, test_site_config, test_profile, test_session
):
    """Test successful execution of a valid prompt endpoint"""
    original_dir = os.getcwd()
    os.chdir(test_repo_path)
    try:
        endpoint_type = "prompt"
        name = "valid_prompt"
        args = {"topic": "quantum computing", "expertise_level": "intermediate"}
        result = await run_endpoint(
            endpoint_type,
            name,
            args,
            test_user_config,
            test_site_config,
            test_session,
            test_profile,
        )
        assert len(result) == 2  # Two messages
        # Verify system message
        assert result[0]["role"] == "system"
        assert result[0]["type"] == "text"
        assert (
            result[0]["prompt"]
            == "You are a knowledgeable teacher who adapts explanations to the audience's expertise level."
        )
        # Verify user message
        assert result[1]["role"] == "user"
        assert result[1]["type"] == "text"
        assert "quantum computing" in result[1]["prompt"]
        assert "intermediate" in result[1]["prompt"]
    finally:
        os.chdir(original_dir)


@pytest.mark.asyncio
async def test_valid_prompt_default_value(
    test_repo_path, test_user_config, test_site_config, test_profile, test_session
):
    """Test prompt execution with default expertise_level value"""
    original_dir = os.getcwd()
    os.chdir(test_repo_path)
    try:
        endpoint_type = "prompt"
        name = "valid_prompt"
        args = {"topic": "machine learning"}  # expertise_level defaults to "beginner"
        result = await run_endpoint(
            endpoint_type,
            name,
            args,
            test_user_config,
            test_site_config,
            test_session,
            test_profile,
        )
        assert len(result) == 2  # Two messages
        assert "machine learning" in result[1]["prompt"]
        assert "beginner" in result[1]["prompt"]
    finally:
        os.chdir(original_dir)
