import pytest
from pathlib import Path
import yaml
import os
from mxcp.evals.loader import discover_eval_files, load_eval_suite
from mxcp.evals.runner import get_model_config
from mxcp.config.user_config import UserConfig


def test_discover_eval_files(tmp_path):
    """Test discovering eval files"""
    # Create mxcp-site.yml to make it a valid repo
    site_config = tmp_path / "mxcp-site.yml"
    site_config.write_text("mxcp: '1.0.0'\nname: test")
    
    # Create test eval files
    eval_file1 = tmp_path / "test-evals.yml"
    eval_file1.write_text("""
mxcp: "1.0.0"
suite: test_suite
description: "Test suite"
tests:
  - name: test1
    prompt: "Test prompt"
""")
    
    eval_file2 = tmp_path / "another.evals.yml"
    eval_file2.write_text("""
mxcp: "1.0.0"
suite: another_suite
tests:
  - name: test2
    prompt: "Another test"
""")
    
    # Create non-eval file that should be ignored
    non_eval = tmp_path / "endpoint.yml"
    non_eval.write_text("mxcp: '1.0.0'\ntool:\n  name: test")
    
    # Change to tmp_path directory to discover files
    import os
    original_cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        eval_files = discover_eval_files()
    finally:
        os.chdir(original_cwd)
    
    assert len(eval_files) == 2
    # eval_files returns tuples of (path, content, error)
    file_names = [path.name for path, _, _ in eval_files]
    assert "test-evals.yml" in file_names
    assert "another.evals.yml" in file_names
    assert "endpoint.yml" not in file_names


def test_load_eval_suite():
    """Test loading an eval suite"""
    content = """
mxcp: "1.0.0"
suite: test_suite
description: "Test suite description"
model: gpt-3.5-turbo
tests:
  - name: test_with_assertions
    description: "Test with all assertion types"
    prompt: "Test prompt"
    user_context:
      role: admin
    assertions:
      must_call:
        - tool: my_tool
          args:
            param: value
      must_not_call:
        - dangerous_tool
      answer_contains:
        - "success"
      answer_not_contains:
        - "error"
"""
    
    # Parse YAML
    suite = yaml.safe_load(content)
    
    # Validate structure
    assert suite["suite"] == "test_suite"
    assert suite["description"] == "Test suite description"
    assert suite["model"] == "gpt-3.5-turbo"
    assert len(suite["tests"]) == 1
    
    test = suite["tests"][0]
    assert test["name"] == "test_with_assertions"
    assert test["prompt"] == "Test prompt"
    assert test["user_context"]["role"] == "admin"
    
    assertions = test["assertions"]
    assert len(assertions["must_call"]) == 1
    assert assertions["must_call"][0]["tool"] == "my_tool"
    assert assertions["must_not_call"] == ["dangerous_tool"]
    assert assertions["answer_contains"] == ["success"]
    assert assertions["answer_not_contains"] == ["error"]


def test_get_model_config():
    """Test getting model configuration"""
    user_config: UserConfig = {
        "mxcp": "1.0.0",
        "models": {
            "default": "claude-3-haiku",
            "models": {
                "claude-3-haiku": {
                    "type": "claude",
                    "api_key": "$\{ANTHROPIC_API_KEY\}",
                    "timeout": 30
                },
                "gpt-4": {
                    "type": "openai",
                    "api_key": "test-key",
                    "base_url": "https://api.openai.com/v1"
                }
            }
        }
    }
    
    # Test getting specific model
    config = get_model_config(user_config, "claude-3-haiku")
    assert config is not None
    assert config["type"] == "claude"
    assert config["api_key"] == "$\{ANTHROPIC_API_KEY\}"
    
    # Test getting default model
    config = get_model_config(user_config, None)
    assert config is not None
    assert config["type"] == "claude"
    
    # Test non-existent model
    config = get_model_config(user_config, "non-existent")
    assert config is None


def test_eval_file_validation(tmp_path):
    """Test eval file validation"""
    # Create mxcp-site.yml to make it a valid repo
    site_config = tmp_path / "mxcp-site.yml"
    site_config.write_text("mxcp: '1.0.0'\nname: test")
    
    # Valid eval file
    valid_file = tmp_path / "valid-evals.yml"
    valid_file.write_text("""
mxcp: "1.0.0"
suite: valid_suite
tests:
  - name: test1
    prompt: "Test"
    assertions:
      answer_contains:
        - "test"
""")
    
    # Invalid eval file (missing required fields)
    invalid_file = tmp_path / "invalid-evals.yml"
    invalid_file.write_text("""
mxcp: "1.0.0"
# Missing suite name
tests:
  - name: test1
    prompt: "Test"
""")
    
    # Load valid file should succeed
    import os
    original_cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        result = load_eval_suite("valid_suite")
        assert result is not None
        assert result[1]["suite"] == "valid_suite"
        
        # Load invalid file should fail  
        result = load_eval_suite("invalid_suite")
        # Since suite name is missing, it should not be found
        assert result is None
    finally:
        os.chdir(original_cwd) 