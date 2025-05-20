import pytest
from pathlib import Path
from raw.endpoints.runner import run_endpoint
from raw.config.user_config import load_user_config
from raw.config.site_config import load_site_config
import os

@pytest.fixture(scope="session", autouse=True)
def set_raw_config_env():
    os.environ["RAW_CONFIG"] = str(Path(__file__).parent / "fixtures" / "runner" / "raw-config.yml")

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
        return load_user_config()
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

def test_simple_tool_success(test_repo_path, test_user_config, test_site_config, test_profile):
    """Test successful execution of a simple tool endpoint"""
    original_dir = os.getcwd()
    os.chdir(test_repo_path)
    try:
        endpoint_type = "tool"
        name = "simple_tool"
        args = {"a": 1, "b": 2}
        result = run_endpoint(endpoint_type, name, args, test_user_config, test_site_config, test_profile)
        assert len(result) == 1
        assert result[0][0] == 3
    finally:
        os.chdir(original_dir)

def test_simple_tool_missing_arg(test_repo_path, test_user_config, test_site_config, test_profile):
    """Test tool execution with missing required argument"""
    original_dir = os.getcwd()
    os.chdir(test_repo_path)
    try:
        endpoint_type = "tool"
        name = "simple_tool"
        args = {"a": 1}  # Missing 'b'
        with pytest.raises(RuntimeError) as exc_info:
            run_endpoint(endpoint_type, name, args, test_user_config, test_site_config, test_profile)
        assert "Required parameter missing" in str(exc_info.value)
    finally:
        os.chdir(original_dir)

def test_simple_tool_wrong_type(test_repo_path, test_user_config, test_site_config, test_profile):
    """Test tool execution with wrong argument type"""
    original_dir = os.getcwd()
    os.chdir(test_repo_path)
    try:
        endpoint_type = "tool"
        name = "simple_tool"
        args = {"a": "not_a_number", "b": 2}
        with pytest.raises(RuntimeError) as exc_info:
            run_endpoint(endpoint_type, name, args, test_user_config, test_site_config, test_profile)
        assert "Error converting parameter" in str(exc_info.value)
    finally:
        os.chdir(original_dir)

def test_date_resource_success(test_repo_path, test_user_config, test_site_config, test_profile):
    """Test successful execution of a date resource endpoint"""
    original_dir = os.getcwd()
    os.chdir(test_repo_path)
    try:
        endpoint_type = "resource"
        name = "date_resource"
        args = {"date": "2024-03-20", "format": "human"}
        result = run_endpoint(endpoint_type, name, args, test_user_config, test_site_config, test_profile)
        assert len(result) == 1
        assert result[0][0] == "March 20, 2024"
        assert result[0][1] == "human"
    finally:
        os.chdir(original_dir)

def test_date_resource_invalid_date(test_repo_path, test_user_config, test_site_config, test_profile):
    """Test resource execution with invalid date format"""
    original_dir = os.getcwd()
    os.chdir(test_repo_path)
    try:
        endpoint_type = "resource"
        name = "date_resource"
        args = {"date": "not-a-date", "format": "iso"}
        with pytest.raises(RuntimeError) as exc_info:
            run_endpoint(endpoint_type, name, args, test_user_config, test_site_config, test_profile)
        assert "Error converting parameter" in str(exc_info.value)
    finally:
        os.chdir(original_dir)

def test_date_resource_invalid_format(test_repo_path, test_user_config, test_site_config, test_profile):
    """Test resource execution with invalid format enum value"""
    original_dir = os.getcwd()
    os.chdir(test_repo_path)
    try:
        endpoint_type = "resource"
        name = "date_resource"
        args = {"date": "2024-03-20", "format": "invalid_format"}
        with pytest.raises(RuntimeError) as exc_info:
            run_endpoint(endpoint_type, name, args, test_user_config, test_site_config, test_profile)
        assert "Invalid value for format" in str(exc_info.value)
    finally:
        os.chdir(original_dir)

def test_greeting_prompt_success(test_repo_path, test_user_config, test_site_config, test_profile):
    """Test successful execution of a greeting prompt endpoint"""
    original_dir = os.getcwd()
    os.chdir(test_repo_path)
    try:
        endpoint_type = "prompt"
        name = "greeting_prompt"
        args = {"name": "Alice", "time_of_day": "afternoon"}
        result = run_endpoint(endpoint_type, name, args, test_user_config, test_site_config, test_profile)
        assert len(result) == 1
        messages = result[0][0]  # Access first tuple element
        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert messages[0]["type"] == "text"
        assert messages[0]["prompt"] == "You are a friendly greeter."
        assert messages[1]["role"] == "user"
        assert messages[1]["type"] == "text"
        assert "Good afternoon, Alice!" in messages[1]["prompt"]
        assert "wonderful afternoon" in messages[1]["prompt"]
    finally:
        os.chdir(original_dir)

def test_greeting_prompt_default_value(test_repo_path, test_user_config, test_site_config, test_profile):
    """Test prompt execution with default time_of_day value"""
    original_dir = os.getcwd()
    os.chdir(test_repo_path)
    try:
        endpoint_type = "prompt"
        name = "greeting_prompt"
        args = {"name": "Bob"}  # time_of_day defaults to "morning"
        result = run_endpoint(endpoint_type, name, args, test_user_config, test_site_config, test_profile)
        assert len(result) == 1
        messages = result[0][0]  # Access first tuple element
        assert len(messages) == 2
        assert "Good morning, Bob!" in messages[1]["prompt"]
    finally:
        os.chdir(original_dir)

def test_greeting_prompt_name_too_long(test_repo_path, test_user_config, test_site_config, test_profile):
    """Test prompt execution with name exceeding maxLength"""
    original_dir = os.getcwd()
    os.chdir(test_repo_path)
    try:
        endpoint_type = "prompt"
        name = "greeting_prompt"
        args = {"name": "A" * 51, "time_of_day": "morning"}  # 51 chars > maxLength 50
        with pytest.raises(RuntimeError) as exc_info:
            run_endpoint(endpoint_type, name, args, test_user_config, test_site_config, test_profile)
        assert "String name is too long" in str(exc_info.value)
    finally:
        os.chdir(original_dir)

def test_nonexistent_endpoint(test_repo_path, test_user_config, test_site_config, test_profile):
    """Test execution of a non-existent endpoint"""
    original_dir = os.getcwd()
    os.chdir(test_repo_path)
    try:
        endpoint_type = "tool"
        name = "nonexistent"
        args = {}
        with pytest.raises(RuntimeError) as exc_info:
            run_endpoint(endpoint_type, name, args, test_user_config, test_site_config, test_profile)
        assert "not found" in str(exc_info.value)
    finally:
        os.chdir(original_dir)

def test_invalid_endpoint_yaml(test_repo_path, test_user_config, test_site_config, test_profile):
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
                run_endpoint(endpoint_type, name, args, test_user_config, test_site_config, test_profile)
            assert "Error running endpoint" in str(exc_info.value)
        finally:
            invalid_path.unlink()
    finally:
        os.chdir(original_dir)

def test_greeting_prompt_missing_required_param(test_repo_path, test_user_config, test_site_config, test_profile):
    """Test prompt execution with missing required parameter"""
    original_dir = os.getcwd()
    os.chdir(test_repo_path)
    try:
        endpoint_type = "prompt"
        name = "greeting_prompt"
        args = {"time_of_day": "morning"}  # Missing required 'name' parameter
        with pytest.raises(RuntimeError) as exc_info:
            run_endpoint(endpoint_type, name, args, test_user_config, test_site_config, test_profile)
        assert "Required parameter missing" in str(exc_info.value)
    finally:
        os.chdir(original_dir)

def test_valid_prompt_success(test_repo_path, test_user_config, test_site_config, test_profile):
    """Test successful execution of a valid prompt endpoint"""
    original_dir = os.getcwd()
    os.chdir(test_repo_path)
    try:
        endpoint_type = "prompt"
        name = "valid_prompt"
        args = {"topic": "quantum computing", "expertise_level": "intermediate"}
        result = run_endpoint(endpoint_type, name, args, test_user_config, test_site_config, test_profile)
        assert len(result) == 1
        messages = result[0][0]  # Access first tuple element
        assert len(messages) == 2
        # Verify system message
        assert messages[0]["role"] == "system"
        assert messages[0]["type"] == "text"
        assert messages[0]["prompt"] == "You are a knowledgeable teacher who adapts explanations to the audience's expertise level."
        # Verify user message
        assert messages[1]["role"] == "user"
        assert messages[1]["type"] == "text"
        assert "quantum computing" in messages[1]["prompt"]
        assert "intermediate" in messages[1]["prompt"]
    finally:
        os.chdir(original_dir)

def test_valid_prompt_default_value(test_repo_path, test_user_config, test_site_config, test_profile):
    """Test prompt execution with default expertise_level value"""
    original_dir = os.getcwd()
    os.chdir(test_repo_path)
    try:
        endpoint_type = "prompt"
        name = "valid_prompt"
        args = {"topic": "machine learning"}  # expertise_level defaults to "beginner"
        result = run_endpoint(endpoint_type, name, args, test_user_config, test_site_config, test_profile)
        assert len(result) == 1
        messages = result[0][0]  # Access first tuple element
        assert len(messages) == 2
        assert "machine learning" in messages[1]["prompt"]
        assert "beginner" in messages[1]["prompt"]
    finally:
        os.chdir(original_dir) 