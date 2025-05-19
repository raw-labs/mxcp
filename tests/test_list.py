import pytest
from pathlib import Path
from raw.endpoints.loader import EndpointLoader
import os

@pytest.fixture(scope="session", autouse=True)
def set_raw_config_env():
    os.environ["RAW_CONFIG"] = str(Path(__file__).parent / "fixtures" / "list" / "raw-config.yml")

@pytest.fixture
def test_repo_path():
    """Path to the test repository."""
    return Path(__file__).parent / "fixtures" / "list"

@pytest.fixture
def test_config(test_repo_path):
    """Load test configuration."""
    original_dir = os.getcwd()
    os.chdir(test_repo_path)
    try:
        from raw.config.user_config import load_user_config
        return load_user_config()
    finally:
        os.chdir(original_dir)

def test_list_endpoints(test_repo_path, test_config):
    """Test listing all endpoints"""
    original_dir = os.getcwd()
    os.chdir(test_repo_path)
    try:
        # Create loader and discover endpoints
        loader = EndpointLoader({})
        endpoints = loader.discover_endpoints()
        
        # Verify we found all our test endpoints
        assert len(endpoints) == 3  # tool1, resource1, prompt1
        
        # Convert to dict for easier lookup
        endpoint_dict = {str(path): data for path, data in endpoints}
        
        # Verify tool endpoint
        tool_path = test_repo_path / "endpoints" / "tool1.yml"
        assert str(tool_path) in endpoint_dict
        tool_data = endpoint_dict[str(tool_path)]
        assert "tool" in tool_data
        assert tool_data["tool"]["name"] == "tool1"
        
        # Verify resource endpoint
        resource_path = test_repo_path / "endpoints" / "resource1.yml"
        assert str(resource_path) in endpoint_dict
        resource_data = endpoint_dict[str(resource_path)]
        assert "resource" in resource_data
        assert resource_data["resource"]["name"] == "resource1"
        
        # Verify prompt endpoint
        prompt_path = test_repo_path / "endpoints" / "prompt1.yml"
        assert str(prompt_path) in endpoint_dict
        prompt_data = endpoint_dict[str(prompt_path)]
        assert "prompt" in prompt_data
        assert prompt_data["prompt"]["name"] == "prompt1"
        
        # Verify prompt has proper message structure
        messages = prompt_data["prompt"]["messages"]
        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert messages[0]["type"] == "text"
        assert messages[1]["role"] == "user"
        assert messages[1]["type"] == "text"
        
    finally:
        os.chdir(original_dir)

def test_list_endpoints_skips_config_files(test_repo_path, test_config):
    """Test that list skips raw-site.yml and raw-config.yml"""
    original_dir = os.getcwd()
    os.chdir(test_repo_path)
    try:
        # Create loader and discover endpoints
        loader = EndpointLoader({})
        endpoints = loader.discover_endpoints()
        
        # Convert to dict for easier lookup
        endpoint_dict = {str(path): data for path, data in endpoints}
        
        # Verify config files are not included
        site_config_path = test_repo_path / "raw-site.yml"
        user_config_path = Path(os.environ["RAW_CONFIG"])
        
        assert str(site_config_path) not in endpoint_dict
        assert str(user_config_path) not in endpoint_dict
        
    finally:
        os.chdir(original_dir) 