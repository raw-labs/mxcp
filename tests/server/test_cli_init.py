import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
import yaml
from click.testing import CliRunner

from mxcp.server.interfaces.cli.init import init
from mxcp.server.core.config.site_config import load_site_config


@pytest.fixture(scope="session", autouse=True)
def set_mxcp_config_env():
    """Set MXCP_CONFIG to use test fixture user config."""
    original_config = os.environ.get("MXCP_CONFIG")
    os.environ["MXCP_CONFIG"] = str(
        Path(__file__).parent / "fixtures" / "cli-init" / "mxcp-config.yml"
    )
    yield
    # Restore original config after tests
    if original_config is not None:
        os.environ["MXCP_CONFIG"] = original_config
    elif "MXCP_CONFIG" in os.environ:
        del os.environ["MXCP_CONFIG"]


def test_init_basic(tmp_path):
    """Test basic init without bootstrap."""
    # Simulate 'n' response to the config generation prompt
    result = subprocess.run(
        ["mxcp", "init", str(tmp_path)],
        capture_output=True,
        text=True,
        input="n\n",  # Say no to config generation
    )

    assert result.returncode == 0
    assert (tmp_path / "mxcp-site.yml").exists()
    assert not (tmp_path / "server_config.json").exists()  # Should not exist if we said no

    # Check mxcp-site.yml content
    with open(tmp_path / "mxcp-site.yml") as f:
        site_config = yaml.safe_load(f)

    assert site_config["mxcp"] == 1
    assert site_config["project"] == tmp_path.name
    assert site_config["profile"] == "default"


def test_init_bootstrap(tmp_path):
    """Test init with bootstrap flag."""
    # Simulate 'y' response to the config generation prompt
    result = subprocess.run(
        ["mxcp", "init", str(tmp_path), "--bootstrap"],
        capture_output=True,
        text=True,
        input="y\n",  # Say yes to config generation
    )

    assert result.returncode == 0
    assert (tmp_path / "mxcp-site.yml").exists()
    assert (tmp_path / "server_config.json").exists()  # Should exist if we said yes
    assert (tmp_path / "tools" / "hello-world.yml").exists()
    assert (tmp_path / "sql" / "hello-world.sql").exists()

    # Check SQL file formatting
    with open(tmp_path / "sql" / "hello-world.sql") as f:
        sql_content = f.read()
    assert sql_content == "SELECT 'Hello, ' || $name || '!' as greeting\n"

    # Check YML file content
    with open(tmp_path / "tools" / "hello-world.yml") as f:
        yml_content = yaml.safe_load(f)

    assert yml_content["tool"]["name"] == "hello_world"
    assert yml_content["tool"]["parameters"][0]["examples"] == ["World", "Alice", "Bob"]

    # Check output includes next steps
    assert "✨ MXCP project initialized successfully!" in result.stdout
    assert "📁 Project Structure:" in result.stdout
    assert "🚀 Next Steps:" in result.stdout
    assert "mxcp run tool hello_world --param name=World" in result.stdout


def test_init_bootstrap_complete_directory_structure(tmp_path):
    """Test that init --bootstrap creates the complete organized directory structure."""
    project_name = "test-organized-project"
    project_dir = tmp_path / project_name

    # Run mxcp init --bootstrap
    result = subprocess.run(
        ["mxcp", "init", str(project_dir), "--bootstrap", "--project", project_name],
        capture_output=True,
        text=True,
        input="n\n",  # Say no to config generation to focus on directory structure
    )

    assert result.returncode == 0

    # Verify all expected directories exist
    expected_directories = [
        "tools",
        "resources",
        "prompts",
        "evals",
        "python",
        "sql",
        "drift",
        "audit",
        "data",
    ]

    for directory in expected_directories:
        dir_path = project_dir / directory
        assert dir_path.exists(), f"Directory {directory} should exist"
        assert dir_path.is_dir(), f"{directory} should be a directory"

    # No .gitkeep files are created; directories can be empty

    # Verify bootstrap files are in correct locations
    assert (project_dir / "tools" / "hello-world.yml").exists()
    assert (project_dir / "sql" / "hello-world.sql").exists()

    # Verify hello-world.yml references SQL file correctly
    with open(project_dir / "tools" / "hello-world.yml") as f:
        yml_content = yaml.safe_load(f)

    assert yml_content["tool"]["source"]["file"] == "../sql/hello-world.sql"

    # Verify mxcp-site.yml has correct project name
    with open(project_dir / "mxcp-site.yml") as f:
        site_config = yaml.safe_load(f)

    assert site_config["mxcp"] == 1  # Integer version, not string
    assert site_config["project"] == project_name
    assert site_config["profile"] == "default"

    # Test that we can load site config and verify organized paths
    # This requires importing MXCP modules, so we need to add the src path
    import sys

    mxcp_src_path = Path(__file__).parent.parent / "src"
    if str(mxcp_src_path) not in sys.path:
        sys.path.insert(0, str(mxcp_src_path))

    # Change to project directory for config loading
    original_cwd = os.getcwd()
    try:
        os.chdir(project_dir)

        from mxcp.server.core.config.site_config import load_site_config

        loaded_config = load_site_config()

        # Verify organized paths are configured correctly
        paths = loaded_config["paths"]
        expected_paths = {
            "tools": "tools",
            "resources": "resources",
            "prompts": "prompts",
            "evals": "evals",
            "python": "python",
            "sql": "sql",
            "drift": "drift",
            "audit": "audit",
            "data": "data",
        }

        for path_key, expected_value in expected_paths.items():
            assert paths[path_key] == expected_value, f"Path {path_key} should be {expected_value}"

        # Verify profile paths point to organized directories
        profile_config = loaded_config["profiles"]["default"]

        # DuckDB should be in data directory
        expected_duckdb_path = str(project_dir / "data" / "db-default.duckdb")
        assert profile_config["duckdb"]["path"] == expected_duckdb_path

        # Drift should be in drift directory
        expected_drift_path = str(project_dir / "drift" / "drift-default.json")
        assert profile_config["drift"]["path"] == expected_drift_path

        # Audit should be in audit directory
        expected_audit_path = str(project_dir / "audit" / "logs-default.jsonl")
        assert profile_config["audit"]["path"] == expected_audit_path

    finally:
        os.chdir(original_cwd)

    # Verify output mentions all directories in help text
    assert "tools/" in result.stdout
    assert "resources/" in result.stdout
    assert "prompts/" in result.stdout
    assert "evals/" in result.stdout
    assert "python/" in result.stdout
    assert "sql/" in result.stdout
    assert "drift/" in result.stdout
    assert "audit/" in result.stdout
    assert "data/" in result.stdout


def test_init_bootstrap_with_duckdb_initialization(tmp_path):
    """Test that init --bootstrap with DuckDB initialization works (catches versioning issues)."""
    project_name = "test-db-init-project"
    project_dir = tmp_path / project_name

    # Set required environment variables to avoid auth errors
    env = os.environ.copy()
    env["GITHUB_CLIENT_ID"] = "dummy"
    env["GITHUB_CLIENT_SECRET"] = "dummy"

    # Run mxcp init --bootstrap with config generation (triggers DuckDB init)
    result = subprocess.run(
        ["mxcp", "init", str(project_dir), "--bootstrap", "--project", project_name],
        capture_output=True,
        text=True,
        input="y\n",  # Say yes to config generation to trigger DuckDB initialization
        env=env,
    )

    # Should succeed - if there's a versioning issue, this will fail
    assert (
        result.returncode == 0
    ), f"Init failed with output: {result.stdout}\nStderr: {result.stderr}"

    # Verify no version validation errors in output (but allow other warnings)
    assert "Invalid user config" not in result.stdout
    assert "not of type 'integer'" not in result.stdout
    assert "'1.0.0' is not of type 'integer'" not in result.stdout

    # Verify directories were created correctly
    assert (project_dir / "data").exists()
    assert (project_dir / "tools").exists()
    assert (project_dir / "sql").exists()

    # Verify files exist in correct locations
    assert (project_dir / "mxcp-site.yml").exists()
    assert (project_dir / "server_config.json").exists()
    assert (project_dir / "tools" / "hello-world.yml").exists()
    assert (project_dir / "sql" / "hello-world.sql").exists()

    # Verify the mxcp-site.yml has correct integer version
    with open(project_dir / "mxcp-site.yml") as f:
        site_config = yaml.safe_load(f)

    assert site_config["mxcp"] == 1  # Should be integer, not string
    assert site_config["project"] == project_name

    # Success message should be present
    assert "✨ MXCP project initialized successfully!" in result.stdout


def test_user_config_generation_uses_integer_version():
    """Test that user config generation uses integer version (catches versioning bugs)."""
    # Test user config generation directly using the test fixture
    import sys

    mxcp_src_path = Path(__file__).parent.parent / "src"
    if str(mxcp_src_path) not in sys.path:
        sys.path.insert(0, str(mxcp_src_path))

    from mxcp.server.core.config.user_config import _generate_default_config

    # Create a mock site config (as would be created by mxcp init)
    site_config = {"mxcp": 1, "project": "test-new-project", "profile": "default"}

    # Generate default user config (this is what happens when user config doesn't exist)
    user_config = _generate_default_config(site_config)

    # Verify the generated user config has integer version
    assert (
        user_config["mxcp"] == 1
    ), f"User config should have integer version 1, got {user_config['mxcp']} ({type(user_config['mxcp'])})"
    assert isinstance(
        user_config["mxcp"], int
    ), f"User config version should be int, got {type(user_config['mxcp'])}"

    # Verify structure is correct
    assert "projects" in user_config
    assert "test-new-project" in user_config["projects"]
    assert "profiles" in user_config["projects"]["test-new-project"]
    assert "default" in user_config["projects"]["test-new-project"]["profiles"]


def test_init_custom_project_name(tmp_path):
    """Test init with custom project name."""
    result = subprocess.run(
        ["mxcp", "init", str(tmp_path), "--project", "my-custom-project"],
        capture_output=True,
        text=True,
        input="n\n",  # Say no to config generation
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
        input="y\n",  # Say yes to config generation
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
        input="n\n",  # Say no to config generation
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
        input="n\n",  # Say no to config generation
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
        input="y\n",  # Say yes to config generation
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
    assert "--transport stdio" in args_str or all(
        arg in server_config["args"] for arg in ["--transport", "stdio"]
    )

    # If we're in a virtualenv (common in testing), check venv-specific config
    if hasattr(sys, "real_prefix") or (
        hasattr(sys, "base_prefix") and sys.base_prefix != sys.prefix
    ):
        # Should use bash command with activation
        if os.name != "nt":  # Unix-like systems
            assert server_config["command"] == "bash"
            assert any("activate" in arg for arg in server_config["args"])
    else:
        # System-wide installation should use direct mxcp command
        assert server_config["command"] == "mxcp"
        assert "cwd" in server_config


def test_init_bootstrap_complete_directory_structure():
    """Test that init --bootstrap creates the complete directory structure and files."""
    runner = CliRunner()

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        project_dir = tmpdir_path / "test-project"

        # Run init with bootstrap
        result = runner.invoke(
            init, [str(project_dir), "--bootstrap", "--project", "test-project"], input="n\n"
        )

        # Should succeed
        assert result.exit_code == 0, f"Init failed with output: {result.output}"

        # Check that all directories were created
        expected_dirs = [
            "tools",
            "resources",
            "prompts",
            "evals",
            "python",
            "sql",
            "drift",
            "audit",
            "data",
        ]
        for dirname in expected_dirs:
            dir_path = project_dir / dirname
            assert dir_path.exists(), f"Directory {dirname} was not created"
            assert dir_path.is_dir(), f"{dirname} is not a directory"

        # No .gitkeep files are created

        # Check bootstrap files were created correctly
        tool_file = project_dir / "tools" / "hello-world.yml"
        sql_file = project_dir / "sql" / "hello-world.sql"
        assert tool_file.exists(), "hello-world.yml not created in tools/"
        assert sql_file.exists(), "hello-world.sql not created in sql/"

        # Check tool file references SQL correctly
        with open(tool_file) as f:
            tool_config = yaml.safe_load(f)
        assert tool_config["tool"]["source"]["file"] == "../sql/hello-world.sql"

        # Check site config can be loaded (validates schema)
        site_config = load_site_config(project_dir)
        assert site_config["project"] == "test-project"
        assert site_config["profile"] == "default"

        # Check database file was created in correct location
        db_file = project_dir / "data" / "db-default.duckdb"
        assert db_file.exists(), "Database file not created in data/ directory"


def test_init_bootstrap_with_duckdb_initialization():
    """Test that init --bootstrap works with DuckDB initialization."""
    runner = CliRunner()

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        project_dir = tmpdir_path / "test-db-init"

        # Run init with bootstrap
        result = runner.invoke(
            init, [str(project_dir), "--bootstrap", "--project", "test-db-init"], input="n\n"
        )

        # Should succeed without version validation errors
        assert result.exit_code == 0, f"Init failed with output: {result.output}"
        assert "✓ Initialized DuckDB database" in result.output

        # Check that database file exists
        db_file = project_dir / "data" / "db-default.duckdb"
        assert db_file.exists(), "Database file was not created"


def test_user_config_generation_uses_integer_version():
    """Test that _generate_default_config uses integer version format, not string."""
    from mxcp.server.core.config.user_config import _generate_default_config

    # Create a mock site config
    site_config = {"mxcp": 1, "project": "test-project", "profile": "default"}

    config = _generate_default_config(site_config)

    # Version should be integer 1, not string "1.0.0"
    assert config["mxcp"] == 1, f"Expected integer 1, got {repr(config['mxcp'])}"
    assert isinstance(config["mxcp"], int), f"Expected int type, got {type(config['mxcp'])}"


def test_migration_exception_handling():
    """Test that migration exceptions are properly caught and displayed by other commands."""
    from mxcp.server.interfaces.cli.list import list_endpoints

    runner = CliRunner()

    # Use /tmp directly to avoid any parent directory detection issues
    with tempfile.TemporaryDirectory(dir="/tmp") as tmpdir:
        tmpdir_path = Path(tmpdir)
        project_dir = tmpdir_path / "test-migration"
        project_dir.mkdir()

        # Create a site config with old string-based versioning
        old_site_config = {
            "mxcp": "1.0.0",  # This should trigger migration
            "project": "test-migration",
            "profile": "default",
        }

        with open(project_dir / "mxcp-site.yml", "w") as f:
            yaml.dump(old_site_config, f)

        # Change working directory to the project directory
        original_cwd = os.getcwd()
        try:
            os.chdir(project_dir)

            # Run mxcp list - should fail with migration message
            result = runner.invoke(list_endpoints, [])

            # Should exit with error
            assert result.exit_code != 0, "List should have failed due to migration requirement"

            # Should show migration message
            assert (
                "🚨 MIGRATION REQUIRED" in result.output
            ), f"Migration message not shown. Output: {result.output}"

            # Should mention the new directory structure
            assert "NEW structure:" in result.output
            assert "tools/" in result.output
            assert "resources/" in result.output

        finally:
            os.chdir(original_cwd)
