import pytest
import subprocess
import json
import yaml
import tempfile
import sys
import os
from pathlib import Path
import shutil


def test_init_basic(tmp_path):
    """Test basic init without bootstrap."""
    # Simulate 'n' response to the config generation prompt
    result = subprocess.run(
        ["mxcp", "init", str(tmp_path)],
        capture_output=True,
        text=True,
        input="n\n"  # Say no to config generation
    )
    
    assert result.returncode == 0
    assert (tmp_path / "mxcp-site.yml").exists()
    assert not (tmp_path / "server_config.json").exists()  # Should not exist if we said no
    
    # Check mxcp-site.yml content
    with open(tmp_path / "mxcp-site.yml") as f:
        site_config = yaml.safe_load(f)
    
    assert site_config["mxcp"] == "1.0.0"
    assert site_config["project"] == tmp_path.name
    assert site_config["profile"] == "default"


def test_init_bootstrap(tmp_path):
    """Test init with bootstrap flag."""
    # Simulate 'y' response to the config generation prompt
    result = subprocess.run(
        ["mxcp", "init", str(tmp_path), "--bootstrap"],
        capture_output=True,
        text=True,
        input="y\n"  # Say yes to config generation
    )
    
    assert result.returncode == 0
    assert (tmp_path / "mxcp-site.yml").exists()
    assert (tmp_path / "server_config.json").exists()  # Should exist if we said yes
    assert (tmp_path / "endpoints" / "hello-world.yml").exists()
    assert (tmp_path / "endpoints" / "hello-world.sql").exists()
    
    # Check SQL file formatting
    with open(tmp_path / "endpoints" / "hello-world.sql") as f:
        sql_content = f.read()
    assert sql_content == "SELECT 'Hello, ' || $name || '!' as greeting\n"
    
    # Check YML file content
    with open(tmp_path / "endpoints" / "hello-world.yml") as f:
        yml_content = yaml.safe_load(f)
    
    assert yml_content["tool"]["name"] == "hello_world"
    assert yml_content["tool"]["parameters"][0]["examples"] == ["World", "Alice", "Bob"]
    
    # Check output includes next steps
    assert "✨ MXCP project initialized successfully!" in result.stdout
    assert "📁 Project Structure:" in result.stdout
    assert "🚀 Next Steps:" in result.stdout
    assert "mxcp run tool hello_world --param name=World" in result.stdout


def test_init_custom_project_name(tmp_path):
    """Test init with custom project name."""
    result = subprocess.run(
        ["mxcp", "init", str(tmp_path), "--project", "my-custom-project"],
        capture_output=True,
        text=True,
        input="n\n"  # Say no to config generation
    )
    
    assert result.returncode == 0
    
    with open(tmp_path / "mxcp-site.yml") as f:
        site_config = yaml.safe_load(f)
    
    assert site_config["project"] == "my-custom-project"


def test_init_with_config_generation(tmp_path):
    """Test init with Claude Desktop config generation."""
    result = subprocess.run(
        ["mxcp", "init", str(tmp_path), "--bootstrap"],
        capture_output=True,
        text=True,
        input="y\n"  # Say yes to config generation
    )
    
    assert result.returncode == 0
    assert (tmp_path / "server_config.json").exists()
    
    with open(tmp_path / "server_config.json") as f:
        config = json.load(f)
    
    # Basic structure check
    assert "mcpServers" in config
    assert tmp_path.name in config["mcpServers"]
    
    server_config = config["mcpServers"][tmp_path.name]
    assert "command" in server_config
    assert "args" in server_config
    
    # Check output shows the generated config
    assert "Generated configuration:" in result.stdout
    assert "mcpServers" in result.stdout


def test_init_without_config_generation(tmp_path):
    """Test init declining Claude Desktop config generation."""
    result = subprocess.run(
        ["mxcp", "init", str(tmp_path), "--bootstrap"],
        capture_output=True,
        text=True,
        input="n\n"  # Say no to config generation
    )
    
    assert result.returncode == 0
    assert not (tmp_path / "server_config.json").exists()
    
    # Check output mentions skipping config
    assert "Skipped Claude Desktop configuration generation" in result.stdout
    assert "Run 'mxcp init .' again to generate server_config.json" in result.stdout


def test_init_cannot_create_inside_existing_repo(tmp_path):
    """Test that init fails when trying to create inside existing repo."""
    # Create parent repo
    parent_dir = tmp_path / "parent"
    parent_dir.mkdir()
    
    subprocess.run(["mxcp", "init", str(parent_dir)], capture_output=True, input="n\n", text=True)
    
    # Try to create child repo
    child_dir = parent_dir / "child"
    child_dir.mkdir()
    
    result = subprocess.run(
        ["mxcp", "init", str(child_dir)],
        capture_output=True,
        text=True,
        input="n\n"  # Say no to config generation
    )
    
    assert result.returncode != 0
    assert "Cannot create a MXCP repository inside another one" in result.stderr


def test_init_server_config_content(tmp_path):
    """Test the content of generated server_config.json."""
    project_name = "test-project"
    project_dir = tmp_path / project_name
    project_dir.mkdir()
    
    result = subprocess.run(
        ["mxcp", "init", str(project_dir), "--bootstrap"],
        capture_output=True,
        text=True,
        input="y\n"  # Say yes to config generation
    )
    
    assert result.returncode == 0
    
    with open(project_dir / "server_config.json") as f:
        config = json.load(f)
    
    # Basic structure check
    assert "mcpServers" in config
    assert project_name in config["mcpServers"]
    
    server_config = config["mcpServers"][project_name]
    assert "command" in server_config
    assert "args" in server_config
    
    # Check that it includes proper transport
    args_str = " ".join(server_config.get("args", []))
    assert "--transport stdio" in args_str or all(arg in server_config["args"] for arg in ["--transport", "stdio"])
    
    # If we're in a virtualenv (common in testing), check venv-specific config
    if hasattr(sys, 'real_prefix') or (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix):
        # Should use bash command with activation
        if os.name != 'nt':  # Unix-like systems
            assert server_config["command"] == "bash"
            assert any("activate" in arg for arg in server_config["args"])
    else:
        # System-wide installation should use direct mxcp command
        assert server_config["command"] == "mxcp"
        assert "cwd" in server_config 