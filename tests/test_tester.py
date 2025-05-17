import os
import pytest
from pathlib import Path
from raw.endpoints.tester import run_tests, run_all_tests
from raw.config.site_config import load_site_config
from raw.config.user_config import load_user_config

@pytest.fixture(scope="session", autouse=True)
def set_raw_config_env():
    os.environ["RAW_CONFIG"] = str(Path(__file__).parent / "fixtures" / "tester" / "raw-config.yml")

@pytest.fixture
def tester_repo_path():
    """Path to the tester test repository."""
    return Path(__file__).parent / "fixtures" / "tester"

@pytest.fixture
def site_config(tester_repo_path):
    """Load test site configuration."""
    original_dir = os.getcwd()
    os.chdir(tester_repo_path)
    try:
        return load_site_config()
    finally:
        os.chdir(original_dir)

@pytest.fixture
def user_config(tester_repo_path):
    """Load test user configuration."""
    original_dir = os.getcwd()
    os.chdir(tester_repo_path)
    try:
        return load_user_config()
    finally:
        os.chdir(original_dir)

def test_run_valid_tool(tester_repo_path, site_config, user_config):
    """Test running tests for a valid tool endpoint."""
    original_dir = os.getcwd()
    os.chdir(tester_repo_path)
    try:
        result = run_tests("tool/valid_tool", site_config, user_config, None)
        assert result["status"] == "ok"
        assert result["tests_run"] == 2
        assert len(result["tests"]) == 2
        assert all(t["status"] == "passed" for t in result["tests"])
    finally:
        os.chdir(original_dir)

def test_run_invalid_tool(tester_repo_path, site_config, user_config):
    """Test running tests for an invalid tool endpoint."""
    original_dir = os.getcwd()
    os.chdir(tester_repo_path)
    try:
        result = run_tests("tool/invalid_tool", site_config, user_config, None)
        assert result["status"] == "failed"
        assert result["tests_run"] == 3
        assert len(result["tests"]) == 3
        # Check that we have both passed and failed tests
        statuses = [t["status"] for t in result["tests"]]
        assert "passed" in statuses
        assert "failed" in statuses
    finally:
        os.chdir(original_dir)

def test_run_valid_resource(tester_repo_path, site_config, user_config):
    """Test running tests for a valid resource endpoint."""
    original_dir = os.getcwd()
    os.chdir(tester_repo_path)
    try:
        result = run_tests("resource/valid_resource", site_config, user_config, None)
        assert result["status"] == "ok"
        assert result["tests_run"] == 2
        assert len(result["tests"]) == 2
        assert all(t["status"] == "passed" for t in result["tests"])
    finally:
        os.chdir(original_dir)

def test_run_valid_prompt(tester_repo_path, site_config, user_config):
    """Test running tests for a valid prompt endpoint."""
    original_dir = os.getcwd()
    os.chdir(tester_repo_path)
    try:
        result = run_tests("prompt/valid_prompt", site_config, user_config, None)
        assert result["status"] == "ok"
        assert result["tests_run"] == 2
        assert len(result["tests"]) == 2
        assert all(t["status"] == "passed" for t in result["tests"])
    finally:
        os.chdir(original_dir)

def test_run_nonexistent_endpoint(tester_repo_path, site_config, user_config):
    """Test running tests for a nonexistent endpoint."""
    original_dir = os.getcwd()
    os.chdir(tester_repo_path)
    try:
        result = run_tests("tool/nonexistent", site_config, user_config, None)
        assert result["status"] == "error"
        assert "Endpoint not found" in result["message"]
    finally:
        os.chdir(original_dir)

def test_run_all_tests(tester_repo_path, site_config, user_config):
    """Test running all tests."""
    original_dir = os.getcwd()
    os.chdir(tester_repo_path)
    try:
        result = run_all_tests(site_config, user_config, None)
        assert result["status"] == "failed"  # Because invalid_tool has failing tests
        assert result["tests_run"] > 0
        assert len(result["endpoints"]) > 0
        
        # Check that we have results for all endpoint types
        endpoint_types = {e["endpoint"].split("/")[0] for e in result["endpoints"]}
        assert "tool" in endpoint_types
        assert "resource" in endpoint_types
        assert "prompt" in endpoint_types
    finally:
        os.chdir(original_dir) 