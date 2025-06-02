import os
import pytest
from pathlib import Path
from mxcp.config.user_config import load_user_config
from mxcp.config.types import SiteConfig

def test_env_var_interpolation(tmp_path):
    """Test environment variable interpolation in user config."""
    # Create a test config file
    config_path = tmp_path / "config.yml"
    config_content = """
    mxcp: "1.0.0"
    projects:
      test_project:
        profiles:
          dev:
            secrets:
              - name: "test_secret"
                type: "test"
                parameters:
                  simple: "${SIMPLE_VAR}"
                  nested: "prefix-${NESTED_VAR}-suffix"
                  mixed: "static-${MIXED_VAR}-${ANOTHER_VAR}"
    """
    config_path.write_text(config_content)
    
    # Set up environment variables
    os.environ["MXCP_CONFIG"] = str(config_path)
    os.environ["SIMPLE_VAR"] = "simple_value"
    os.environ["NESTED_VAR"] = "nested_value"
    os.environ["MIXED_VAR"] = "mixed_value"
    os.environ["ANOTHER_VAR"] = "another_value"
    
    # Create a minimal site config
    site_config = {
        "project": "test_project",
        "profile": "dev"
    }
    
    # Load and verify config
    config = load_user_config(site_config)
    assert config["projects"]["test_project"]["profiles"]["dev"]["secrets"][0]["parameters"]["simple"] == "simple_value"
    assert config["projects"]["test_project"]["profiles"]["dev"]["secrets"][0]["parameters"]["nested"] == "prefix-nested_value-suffix"
    assert config["projects"]["test_project"]["profiles"]["dev"]["secrets"][0]["parameters"]["mixed"] == "static-mixed_value-another_value"
    
    # Clean up environment variables
    del os.environ["MXCP_CONFIG"]
    del os.environ["SIMPLE_VAR"]
    del os.environ["NESTED_VAR"]
    del os.environ["MIXED_VAR"]
    del os.environ["ANOTHER_VAR"]

def test_missing_env_var(tmp_path):
    """Test error handling for missing environment variables."""
    # Create a test config file
    config_path = tmp_path / "config.yml"
    config_content = """
    mxcp: "1.0.0"
    projects:
      test_project:
        profiles:
          dev:
            secrets:
              - name: "test_secret"
                type: "test"
                parameters:
                  value: "${MISSING_VAR}"
    """
    config_path.write_text(config_content)
    
    # Set up environment variables
    os.environ["MXCP_CONFIG"] = str(config_path)
    
    # Create a minimal site config
    site_config = {
        "project": "test_project",
        "profile": "dev"
    }
    
    # Verify that loading fails with appropriate error
    with pytest.raises(ValueError, match="Environment variable MISSING_VAR is not set"):
        load_user_config(site_config)
    
    # Clean up environment variables
    del os.environ["MXCP_CONFIG"]

def test_env_var_in_nested_structures(tmp_path):
    """Test environment variable interpolation in nested structures (dicts only)."""
    # Create a test config file
    config_path = tmp_path / "config.yml"
    config_content = """
    mxcp: "1.0.0"
    projects:
      test_project:
        profiles:
          dev:
            secrets:
              - name: "test_secret"
                type: "test"
                parameters:
                  nested:
                    key1: "${NESTED_VAR1}"
                    key2: "${NESTED_VAR2}"
    """
    config_path.write_text(config_content)
    
    # Set up environment variables
    os.environ["MXCP_CONFIG"] = str(config_path)
    os.environ["NESTED_VAR1"] = "nested_value1"
    os.environ["NESTED_VAR2"] = "nested_value2"
    
    # Create a minimal site config
    site_config = {
        "project": "test_project",
        "profile": "dev"
    }
    
    # Load and verify config
    config = load_user_config(site_config)
    params = config["projects"]["test_project"]["profiles"]["dev"]["secrets"][0]["parameters"]
    assert params["nested"]["key1"] == "nested_value1"
    assert params["nested"]["key2"] == "nested_value2"
    
    # Clean up environment variables
    del os.environ["MXCP_CONFIG"]
    del os.environ["NESTED_VAR1"]
    del os.environ["NESTED_VAR2"] 