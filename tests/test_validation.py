import os
import pytest
from pathlib import Path
from raw.endpoints.schema import validate_endpoint, validate_all_endpoints
from raw.config.site_config import load_site_config
from raw.config.user_config import load_user_config

@pytest.fixture(scope="session", autouse=True)
def set_raw_config_env():
    os.environ["RAW_CONFIG"] = str(Path(__file__).parent / "fixtures" / "validation" / "raw-config.yml")

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

def test_validate_valid_endpoint(validation_repo_path, site_config, user_config, test_profile):
    """Test validation of a valid endpoint."""
    original_dir = os.getcwd()
    os.chdir(validation_repo_path)
    try:
        endpoint_path = "endpoints/valid_endpoint.yml"
        result = validate_endpoint(endpoint_path, user_config, site_config, test_profile)
        assert result["status"] == "ok"
        assert result["path"] == endpoint_path
    finally:
        os.chdir(original_dir)

@pytest.mark.skip(reason="Type checking temporarily disabled until DuckDB provides better parameter type inference")
def test_validate_invalid_type(validation_repo_path, site_config, user_config, test_profile):
    """Test validation of an endpoint with type mismatch."""
    original_dir = os.getcwd()
    os.chdir(validation_repo_path)
    try:
        endpoint_path = "endpoints/invalid_type.yml"
        result = validate_endpoint(endpoint_path, user_config, site_config, test_profile)
        assert result["status"] == "error"
        assert "type mismatches" in result["message"].lower()
        assert "user_id" in result["message"]
    finally:
        os.chdir(original_dir)

def test_validate_missing_param(validation_repo_path, site_config, user_config, test_profile):
    """Test validation of an endpoint with missing parameter."""
    original_dir = os.getcwd()
    os.chdir(validation_repo_path)
    try:
        endpoint_path = "endpoints/missing_param.yml"
        result = validate_endpoint(endpoint_path, user_config, site_config, test_profile)
        assert result["status"] == "error"
        assert "parameter mismatch" in result["message"].lower()
        assert "extra_param" in result["message"]
    finally:
        os.chdir(original_dir)

def test_validate_all_endpoints(validation_repo_path, site_config, user_config, test_profile):
    """Test validation of all endpoints in the repository."""
    original_dir = os.getcwd()
    os.chdir(validation_repo_path)
    try:
        result = validate_all_endpoints(user_config, site_config, test_profile)
        assert result["status"] == "ok"
        assert len(result["validated"]) == 3  # We have 3 test endpoints
        # Check that we have both valid and invalid results
        statuses = [r["status"] for r in result["validated"]]
        assert "ok" in statuses
        assert "error" in statuses
    finally:
        os.chdir(original_dir) 