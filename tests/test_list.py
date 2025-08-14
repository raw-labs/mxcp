import os
from pathlib import Path

import pytest

from mxcp.core.config.site_config import load_site_config
from mxcp.core.config.user_config import load_user_config
from mxcp.definitions.endpoints.loader import EndpointLoader


@pytest.fixture(scope="session", autouse=True)
def set_mxcp_config_env():
    os.environ["MXCP_CONFIG"] = str(Path(__file__).parent / "fixtures" / "list" / "mxcp-config.yml")


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
        site_config = load_site_config()
        return load_user_config(site_config)
    finally:
        os.chdir(original_dir)


def test_list_endpoints(test_repo_path, test_config):
    """Test listing all endpoints from root directory"""
    original_dir = os.getcwd()
    os.chdir(test_repo_path)
    try:
        # Load site config and create loader
        site_config = load_site_config()
        loader = EndpointLoader(site_config)
        endpoints = loader.discover_endpoints()

        # Convert to dict for easier lookup
        endpoint_dict = {
            str(path): data for path, data, error_msg in endpoints if error_msg is None
        }
        failed_endpoints = {str(path): error for path, _, error in endpoints if error is not None}

        # Verify no failed endpoints
        assert len(failed_endpoints) == 0, f"Found failed endpoints: {failed_endpoints}"

        # Verify we found all our test endpoints
        # Note: disabled tools are filtered out during discovery
        assert (
            len(endpoints) == 7
        )  # tool1, tool2, resource1, resource1_detail, resource1_list, prompt1, prompt2 (disabled_tool filtered out)

        # Verify tools directory endpoints
        tool1_path = test_repo_path / "tools" / "tool1.yml"
        assert str(tool1_path) in endpoint_dict
        tool1_data = endpoint_dict[str(tool1_path)]
        assert "tool" in tool1_data
        assert tool1_data["tool"]["name"] == "tool1"

        # Verify resources directory endpoints
        resource1_path = test_repo_path / "resources" / "resource1.yml"
        assert str(resource1_path) in endpoint_dict
        resource1_data = endpoint_dict[str(resource1_path)]
        assert "resource" in resource1_data
        assert resource1_data["resource"]["name"] == "resource1"

        # Verify prompts directory endpoints
        prompt1_path = test_repo_path / "prompts" / "prompt1.yml"
        assert str(prompt1_path) in endpoint_dict
        prompt1_data = endpoint_dict[str(prompt1_path)]
        assert "prompt" in prompt1_data
        assert prompt1_data["prompt"]["name"] == "prompt1"

        # Verify prompt1 has proper message structure
        messages = prompt1_data["prompt"]["messages"]
        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert messages[0]["type"] == "text"
        assert messages[1]["role"] == "user"
        assert messages[1]["type"] == "text"

        # Verify additional tools
        tool2_path = test_repo_path / "tools" / "tool2.yml"
        assert str(tool2_path) in endpoint_dict
        tool2_data = endpoint_dict[str(tool2_path)]
        assert "tool" in tool2_data
        assert tool2_data["tool"]["name"] == "tool2"
        assert "source" in tool2_data["tool"]
        assert "code" in tool2_data["tool"]["source"]

        # Verify additional prompts
        prompt2_path = test_repo_path / "prompts" / "prompt2.yml"
        assert str(prompt2_path) in endpoint_dict
        prompt2_data = endpoint_dict[str(prompt2_path)]
        assert "prompt" in prompt2_data
        assert prompt2_data["prompt"]["name"] == "prompt2"

        # Verify prompt2 has proper message structure
        messages = prompt2_data["prompt"]["messages"]
        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert messages[0]["type"] == "text"
        assert messages[0]["prompt"] == "You are a helpful assistant in a subfolder."
        assert messages[1]["role"] == "user"
        assert messages[1]["type"] == "text"
        assert messages[1]["prompt"] == "{{message}}"

        # Verify disabled endpoint is filtered out during discovery
        disabled_tool_path = test_repo_path / "tools" / "disabled_tool.yml"
        assert (
            str(disabled_tool_path) not in endpoint_dict
        ), "Disabled endpoint should be filtered out during discovery"
    finally:
        os.chdir(original_dir)


def test_list_endpoints_from_subfolder(test_repo_path, test_config):
    """Test listing endpoints from subfolder directory"""
    original_dir = os.getcwd()
    # Change to test repo directory (no more subfolder navigation)
    os.chdir(test_repo_path)
    try:
        # Load site config and create loader
        site_config = load_site_config()
        loader = EndpointLoader(site_config)
        endpoints = loader.discover_endpoints()

        # Convert to dict for easier lookup
        endpoint_dict = {
            str(path): data for path, data, error_msg in endpoints if error_msg is None
        }

        # Should find all endpoints in organized directories
        # Note: disabled tools are filtered out during discovery
        assert (
            len(endpoints) == 7
        )  # tool1, tool2, resource1, resource1_detail, resource1_list, prompt1, prompt2 (disabled_tool filtered out)

        # Verify tools directory endpoints are accessible
        tool1_path = test_repo_path / "tools" / "tool1.yml"
        assert str(tool1_path) in endpoint_dict
        tool1_data = endpoint_dict[str(tool1_path)]
        assert "tool" in tool1_data
        assert tool1_data["tool"]["name"] == "tool1"

        # Verify additional tools
        tool2_path = test_repo_path / "tools" / "tool2.yml"
        assert str(tool2_path) in endpoint_dict
        tool2_data = endpoint_dict[str(tool2_path)]
        assert "tool" in tool2_data
        assert tool2_data["tool"]["name"] == "tool2"
        assert "source" in tool2_data["tool"]
        assert "code" in tool2_data["tool"]["source"]

        # Verify additional prompts
        prompt2_path = test_repo_path / "prompts" / "prompt2.yml"
        assert str(prompt2_path) in endpoint_dict
        prompt2_data = endpoint_dict[str(prompt2_path)]
        assert "prompt" in prompt2_data
        assert prompt2_data["prompt"]["name"] == "prompt2"

        # Verify prompt2 has proper message structure
        messages = prompt2_data["prompt"]["messages"]
        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert messages[0]["type"] == "text"
        assert messages[0]["prompt"] == "You are a helpful assistant in a subfolder."
        assert messages[1]["role"] == "user"
        assert messages[1]["type"] == "text"
        assert messages[1]["prompt"] == "{{message}}"
    finally:
        os.chdir(original_dir)


def test_list_endpoints_skips_config_files(test_repo_path, test_config):
    """Test that config files are not included in endpoint list"""
    original_dir = os.getcwd()
    os.chdir(test_repo_path)
    try:
        # Load site config and create loader
        site_config = load_site_config()
        loader = EndpointLoader(site_config)
        endpoints = loader.discover_endpoints()

        # Convert to dict for easier lookup
        endpoint_dict = {
            str(path): data for path, data, error_msg in endpoints if error_msg is None
        }

        # Verify config files are not included
        site_config_path = test_repo_path / "mxcp-site.yml"
        user_config_path = Path(os.environ["MXCP_CONFIG"])

        assert str(site_config_path) not in endpoint_dict
        assert str(user_config_path) not in endpoint_dict
    finally:
        os.chdir(original_dir)
