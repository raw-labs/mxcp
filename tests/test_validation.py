import os
import pytest
from pathlib import Path
from mxcp.endpoints.validate import validate_endpoint, validate_all_endpoints
from mxcp.config.site_config import load_site_config
from mxcp.config.user_config import load_user_config
from mxcp.config.execution_engine import create_execution_engine

@pytest.fixture(scope="session", autouse=True)
def set_mxcp_config_env():
    os.environ["MXCP_CONFIG"] = str(Path(__file__).parent / "fixtures" / "validation" / "mxcp-config.yml")

@pytest.fixture
def validation_repo_path():
    """Path to the validation test repository."""
    return Path(__file__).parent / "fixtures" / "validation"

@pytest.fixture
def site_config(validation_repo_path):
    """Load test site configuration."""
    original_dir = os.getcwd()
    os.chdir(validation_repo_path)
    try:
        return load_site_config()
    finally:
        os.chdir(original_dir)

@pytest.fixture
def user_config(validation_repo_path):
    """Load test user configuration."""
    original_dir = os.getcwd()
    os.chdir(validation_repo_path)
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
def test_execution_engine(user_config, site_config, test_profile):
    """Create a test ExecutionEngine."""
    execution_engine = create_execution_engine(user_config, site_config, test_profile, readonly=True)
    yield execution_engine
    execution_engine.shutdown()

def test_validate_valid_endpoint(validation_repo_path, site_config, test_execution_engine):
    """Test validation of a valid endpoint."""
    original_dir = os.getcwd()
    os.chdir(validation_repo_path)
    try:
        endpoint_path = "tools/valid_endpoint.yml"
        result = validate_endpoint(endpoint_path, site_config, test_execution_engine)
        assert result["status"] == "ok"
        assert result["path"] == endpoint_path
    finally:
        os.chdir(original_dir)

def test_validate_valid_prompt(validation_repo_path, site_config, test_execution_engine):
    """Test validation of a valid prompt endpoint."""
    original_dir = os.getcwd()
    os.chdir(validation_repo_path)
    try:
        endpoint_path = "prompts/valid_prompt.yml"
        result = validate_endpoint(endpoint_path, site_config, test_execution_engine)
        assert result["status"] == "ok"
        assert result["path"] == endpoint_path
    finally:
        os.chdir(original_dir)

def test_validate_invalid_prompt(validation_repo_path, site_config, test_execution_engine):
    """Test validation of a prompt endpoint with undefined template variables."""
    original_dir = os.getcwd()
    os.chdir(validation_repo_path)
    try:
        endpoint_path = "prompts/invalid_prompt.yml"
        result = validate_endpoint(endpoint_path, site_config, test_execution_engine)
        assert result["status"] == "error"
        assert "undefined template variables" in result["message"].lower()
        # Check that all undefined variables are mentioned
        assert "expertise_level" in result["message"]
        assert "complexity" in result["message"]
        assert "extra_info" in result["message"]
    finally:
        os.chdir(original_dir)

@pytest.mark.skip(reason="Type checking temporarily disabled until DuckDB provides better parameter type inference")
def test_validate_invalid_type(validation_repo_path, site_config, test_execution_engine):
    """Test validation of an endpoint with type mismatch."""
    original_dir = os.getcwd()
    os.chdir(validation_repo_path)
    try:
        endpoint_path = "endpoints/invalid_type.yml"
        result = validate_endpoint(endpoint_path, site_config, test_execution_engine)
        assert result["status"] == "error"
        assert "type mismatches" in result["message"].lower()
        assert "user_id" in result["message"]
    finally:
        os.chdir(original_dir)

def test_validate_invalid_parameter_name(validation_repo_path, site_config, test_execution_engine):
    """Test validation of an endpoint with an invalid parameter name."""
    original_dir = os.getcwd()
    os.chdir(validation_repo_path)
    try:
        endpoint_path = "tools/invalid_parameter_name.yml"
        result = validate_endpoint(endpoint_path, site_config, test_execution_engine)
        assert result["status"] == "error"
        assert "'user/id' does not match" in result["message"].lower()
    finally:
        os.chdir(original_dir)

def test_validate_missing_param(validation_repo_path, site_config, test_execution_engine):
    """Test validation of an endpoint with missing parameter."""
    original_dir = os.getcwd()
    os.chdir(validation_repo_path)
    try:
        endpoint_path = "tools/missing_param.yml"
        result = validate_endpoint(endpoint_path, site_config, test_execution_engine)
        assert result["status"] == "error"
        assert "parameter mismatch" in result["message"].lower()
        assert "extra_param" in result["message"]
    finally:
        os.chdir(original_dir)

def test_validate_all_endpoints(validation_repo_path, site_config, test_execution_engine):
    """Test validation of all endpoints in the repository."""
    original_dir = os.getcwd()
    os.chdir(validation_repo_path)
    try:
        result = validate_all_endpoints(site_config, test_execution_engine)
        # We expect at least one error due to intentionally invalid endpoints
        assert result["status"] == "error"
        # Check that we have both valid and invalid results
        statuses = [r["status"] for r in result["validated"]]
        assert "ok" in statuses
        assert "error" in statuses
    finally:
        os.chdir(original_dir)

def test_validate_complex_jinja_prompt_valid(validation_repo_path, site_config, test_execution_engine):
    """Test validation of a prompt endpoint with valid complex Jinja2 features."""
    original_dir = os.getcwd()
    os.chdir(validation_repo_path)
    try:
        endpoint_path = "prompts/complex_jinja_prompt.yml"
        result = validate_endpoint(endpoint_path, site_config, test_execution_engine)
        assert result["status"] == "ok"
        assert result["path"] == endpoint_path
    finally:
        os.chdir(original_dir)

def test_validate_complex_jinja_prompt_invalid(validation_repo_path, site_config, test_execution_engine):
    """Test validation of a prompt endpoint with invalid complex Jinja2 features."""
    original_dir = os.getcwd()
    os.chdir(validation_repo_path)
    try:
        endpoint_path = "prompts/invalid_complex_jinja_prompt.yml"
        result = validate_endpoint(endpoint_path, site_config, test_execution_engine)
        assert result["status"] == "error"
        assert "undefined template variables" in result["message"].lower()
        # Check that all undefined variables are mentioned
        assert "user_type" in result["message"]
        assert "username" in result["message"]
        assert "items" in result["message"]
        assert "item" in result["message"]
    finally:
        os.chdir(original_dir) 