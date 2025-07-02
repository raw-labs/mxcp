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
    mxcp: 1
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
    mxcp: 1
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
    mxcp: 1
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

def test_file_url_interpolation(tmp_path):
    """Test file:// URL interpolation in user config."""
    # Create test files with secrets
    secrets_dir = tmp_path / "secrets"
    secrets_dir.mkdir()
    
    api_key_file = secrets_dir / "api_key.txt"
    api_key_file.write_text("super-secret-api-key-123")
    
    db_password_file = secrets_dir / "db_password.txt"
    db_password_file.write_text("database-password-456\n")  # With newline to test stripping
    
    # Create a test config file with file:// URLs
    config_path = tmp_path / "config.yml"
    config_content = f"""
    mxcp: 1
    projects:
      test_project:
        profiles:
          dev:
            secrets:
              - name: "api_credentials"
                type: "test"
                parameters:
                  api_key: "file://{api_key_file}"
                  api_url: "https://api.example.com"
              - name: "database"
                type: "postgresql"
                parameters:
                  host: "localhost"
                  password: "file://{db_password_file}"
    """
    config_path.write_text(config_content)
    
    # Set up environment variables
    os.environ["MXCP_CONFIG"] = str(config_path)
    
    # Create a minimal site config
    site_config = {
        "project": "test_project",
        "profile": "dev"
    }
    
    # Load and verify config
    config = load_user_config(site_config)
    api_params = config["projects"]["test_project"]["profiles"]["dev"]["secrets"][0]["parameters"]
    db_params = config["projects"]["test_project"]["profiles"]["dev"]["secrets"][1]["parameters"]
    
    assert api_params["api_key"] == "super-secret-api-key-123"
    assert api_params["api_url"] == "https://api.example.com"
    assert db_params["password"] == "database-password-456"  # Whitespace should be stripped
    
    # Clean up environment variables
    del os.environ["MXCP_CONFIG"]

def test_file_url_relative_path(tmp_path):
    """Test file:// URL with relative paths."""
    # Create a test file in current directory
    original_cwd = os.getcwd()
    os.chdir(tmp_path)
    
    try:
        # Create a secret file
        secret_file = Path("secret.txt")
        secret_file.write_text("relative-secret-value")
        
        # Create a test config file
        config_path = Path("config.yml")
        config_content = """
        mxcp: 1
        projects:
          test_project:
            profiles:
              dev:
                secrets:
                  - name: "test_secret"
                    type: "test"
                    parameters:
                      value: "file://secret.txt"
        """
        config_path.write_text(config_content)
        
        # Set up environment variables
        os.environ["MXCP_CONFIG"] = str(config_path)
        
        # Create a minimal site config
        site_config = {
            "project": "test_project",
            "profile": "dev"
        }
        
        # Load and verify config
        config = load_user_config(site_config)
        params = config["projects"]["test_project"]["profiles"]["dev"]["secrets"][0]["parameters"]
        assert params["value"] == "relative-secret-value"
        
    finally:
        # Clean up
        if "MXCP_CONFIG" in os.environ:
            del os.environ["MXCP_CONFIG"]
        os.chdir(original_cwd)

def test_file_url_errors(tmp_path):
    """Test error handling for file:// URLs."""
    # Test non-existent file
    config_path = tmp_path / "config.yml"
    config_content = """
    mxcp: 1
    projects:
      test_project:
        profiles:
          dev:
            secrets:
              - name: "test_secret"
                type: "test"
                parameters:
                  value: "file:///non/existent/file.txt"
    """
    config_path.write_text(config_content)
    
    os.environ["MXCP_CONFIG"] = str(config_path)
    
    site_config = {
        "project": "test_project",
        "profile": "dev"
    }
    
    # Should raise FileNotFoundError
    with pytest.raises(FileNotFoundError, match="File not found"):
        load_user_config(site_config)
    
    # Test directory instead of file
    dir_path = tmp_path / "testdir"
    dir_path.mkdir()
    
    config_content = f"""
    mxcp: 1
    projects:
      test_project:
        profiles:
          dev:
            secrets:
              - name: "test_secret"
                type: "test"
                parameters:
                  value: "file://{dir_path}"
    """
    config_path.write_text(config_content)
    
    # Should raise ValueError
    with pytest.raises(ValueError, match="Path is not a file"):
        load_user_config(site_config)
    
    # Clean up
    del os.environ["MXCP_CONFIG"]

def test_mixed_interpolation_with_files(tmp_path):
    """Test mixing env vars, vault URLs, and file URLs."""
    # Create a secret file
    secret_file = tmp_path / "jwt_secret.txt"
    secret_file.write_text("jwt-secret-key-789")
    
    # Create config with mixed interpolation
    config_path = tmp_path / "config.yml"
    config_content = f"""
    mxcp: 1
    projects:
      test_project:
        profiles:
          dev:
            secrets:
              - name: "api_config"
                type: "test"
                parameters:
                  api_url: "${{API_BASE_URL}}"
                  api_key: "file://{secret_file}"
                  api_timeout: "30"
    """
    config_path.write_text(config_content)
    
    # Set up environment
    os.environ["MXCP_CONFIG"] = str(config_path)
    os.environ["API_BASE_URL"] = "https://api.production.com"
    
    site_config = {
        "project": "test_project",
        "profile": "dev"
    }
    
    # Load and verify
    config = load_user_config(site_config)
    params = config["projects"]["test_project"]["profiles"]["dev"]["secrets"][0]["parameters"]
    
    assert params["api_url"] == "https://api.production.com"
    assert params["api_key"] == "jwt-secret-key-789"
    assert params["api_timeout"] == "30"
    
    # Clean up
    del os.environ["MXCP_CONFIG"]
    del os.environ["API_BASE_URL"] 