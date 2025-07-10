import pytest
from click.testing import CliRunner
from pathlib import Path
import tempfile
import yaml
import os
from mxcp.cli.dev import dev, load_lifecycle_config, run_command, check_required_env, run_command_list
from unittest.mock import patch, MagicMock
import subprocess

@pytest.fixture
def runner():
    return CliRunner()

@pytest.fixture
def temp_project():
    """Create a temporary project directory with mxcp-site.yml"""
    with tempfile.TemporaryDirectory() as tmpdir:
        project_dir = Path(tmpdir)
        
        # Create a sample mxcp-site.yml with lifecycle configuration
        site_config = {
            "mxcp": 1,
            "project": "test-project",
            "profile": "default",
            "lifecycle": {
                "setup": {
                    "description": "Initialize test project",
                    "commands": [
                        {"command": "echo 'Installing dependencies'", "name": "Install deps"},
                        {"command": "echo 'Setting up database'", "name": "Setup DB"},
                        {
                            "command": "echo 'Loading seed data'",
                            "name": "Load seeds",
                            "condition": "if_not_exists:seeds/.loaded"
                        }
                    ]
                },
                "test": {
                    "light": {
                        "description": "Run quick validation tests",
                        "commands": [
                            "echo 'Running light tests'"
                        ]
                    },
                    "full": {
                        "description": "Run comprehensive test suite",
                        "commands": [
                            "echo 'Running unit tests'",
                            "echo 'Running integration tests'"
                        ]
                    },
                    "unit": {
                        "description": "Run unit tests only",
                        "commands": [
                            {"command": "echo 'Running unit tests'", "name": "Unit tests"}
                        ]
                    }
                },
                "deploy": {
                    "description": "Deploy the service",
                    "targets": {
                        "local": {
                            "description": "Deploy locally",
                            "commands": [
                                "echo 'Building project'",
                                "echo 'Deploying locally'"
                            ]
                        },
                        "cloud": {
                            "description": "Deploy to cloud",
                            "commands": [
                                "echo 'Deploying to cloud'"
                            ],
                            "environment": {
                                "required": ["AWS_REGION", "AWS_ACCOUNT_ID"]
                            }
                        }
                    }
                },
                "custom": {
                    "generate-data": {
                        "description": "Generate synthetic test data",
                        "commands": [
                            "echo 'Generating test data'"
                        ]
                    },
                    "coverage": {
                        "description": "Calculate test coverage",
                        "commands": [
                            "echo 'Calculating coverage'",
                            "echo 'Coverage: 85%'"
                        ]
                    }
                }
            }
        }
        
        with open(project_dir / "mxcp-site.yml", "w") as f:
            yaml.dump(site_config, f)
        
        # Create mxcp-config.yml for completeness
        user_config = {
            "mxcp": 1,
            "analytics": {"enabled": False},
            "projects": {
                "test-project": {
                    "profiles": {
                        "default": {}
                    }
                }
            }
        }
        
        config_dir = project_dir / ".mxcp"
        config_dir.mkdir()
        with open(config_dir / "config.yml", "w") as f:
            yaml.dump(user_config, f)
        
        # Create seeds directory for testing conditions
        seeds_dir = project_dir / "seeds"
        seeds_dir.mkdir()
        
        yield project_dir

def test_dev_list_no_lifecycle(runner, temp_project):
    """Test list command when no lifecycle config exists"""
    # Remove lifecycle from config
    config_path = temp_project / "mxcp-site.yml"
    with open(config_path) as f:
        config = yaml.safe_load(f)
    del config["lifecycle"]
    with open(config_path, "w") as f:
        yaml.dump(config, f)
    
    with runner.isolated_filesystem():
        os.chdir(temp_project)
        result = runner.invoke(dev, ["list"])
        assert result.exit_code == 0
        assert "No lifecycle configuration found" in result.output
        assert "Add a 'lifecycle' section" in result.output

def test_dev_list_with_lifecycle(runner, temp_project):
    """Test list command with lifecycle configuration"""
    with runner.isolated_filesystem():
        os.chdir(temp_project)
        result = runner.invoke(dev, ["list"])
        assert result.exit_code == 0
        assert "Available Lifecycle Commands" in result.output
        assert "Setup:" in result.output
        assert "Test Levels:" in result.output
        assert "Deployment Targets:" in result.output
        assert "Custom Commands:" in result.output

def test_dev_setup_dry_run(runner, temp_project):
    """Test setup command with dry-run flag"""
    with runner.isolated_filesystem():
        os.chdir(temp_project)
        result = runner.invoke(dev, ["setup", "--dry-run"])
        assert result.exit_code == 0
        assert "[DRY RUN] Would execute:" in result.output
        assert "echo 'Installing dependencies'" in result.output
        assert "echo 'Setting up database'" in result.output

@patch('subprocess.run')
def test_dev_setup_execution(mock_run, runner, temp_project):
    """Test setup command execution"""
    mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
    
    with runner.isolated_filesystem():
        os.chdir(temp_project)
        result = runner.invoke(dev, ["setup"])
        assert result.exit_code == 0
        assert "✅ Setup completed successfully!" in result.output
        assert mock_run.call_count == 3  # Three commands in setup

def test_dev_setup_with_condition(runner, temp_project):
    """Test setup command with condition that skips execution"""
    # Create the .loaded file to trigger the condition
    (temp_project / "seeds" / ".loaded").touch()
    
    with runner.isolated_filesystem():
        os.chdir(temp_project)
        result = runner.invoke(dev, ["setup", "--dry-run"])
        assert result.exit_code == 0
        assert "Skipped (condition:" in result.output

def test_dev_test_light(runner, temp_project):
    """Test running light tests"""
    with runner.isolated_filesystem():
        os.chdir(temp_project)
        result = runner.invoke(dev, ["test", "--level", "light", "--dry-run"])
        assert result.exit_code == 0
        assert "Run quick validation tests" in result.output
        assert "[DRY RUN] Would execute: echo 'Running light tests'" in result.output

def test_dev_test_full(runner, temp_project):
    """Test running full tests"""
    with runner.isolated_filesystem():
        os.chdir(temp_project)
        result = runner.invoke(dev, ["test", "--level", "full", "--dry-run"])
        assert result.exit_code == 0
        assert "Run comprehensive test suite" in result.output
        assert "echo 'Running unit tests'" in result.output
        assert "echo 'Running integration tests'" in result.output

def test_dev_test_invalid_level(runner, temp_project):
    """Test with non-existent test level"""
    # Remove a test level to test fallback behavior
    config_path = temp_project / "mxcp-site.yml"
    with open(config_path) as f:
        config = yaml.safe_load(f)
    
    # Remove all test levels except light
    config["lifecycle"]["test"] = {
        "light": config["lifecycle"]["test"]["light"]
    }
    
    with open(config_path, "w") as f:
        yaml.dump(config, f)
    
    with runner.isolated_filesystem():
        os.chdir(temp_project)
        result = runner.invoke(dev, ["test", "--level", "full", "--dry-run"])
        assert result.exit_code == 0
        assert "Warning: Test level 'full' not found" in result.output

def test_dev_deploy_local(runner, temp_project):
    """Test deploying to local target"""
    with runner.isolated_filesystem():
        os.chdir(temp_project)
        result = runner.invoke(dev, ["deploy", "--target", "local", "--dry-run"])
        assert result.exit_code == 0
        assert "Deploy locally" in result.output
        assert "echo 'Building project'" in result.output
        assert "echo 'Deploying locally'" in result.output

def test_dev_deploy_cloud_missing_env(runner, temp_project):
    """Test deploying to cloud without required environment variables"""
    with runner.isolated_filesystem():
        os.chdir(temp_project)
        # Make sure env vars are not set
        env = os.environ.copy()
        env.pop("AWS_REGION", None)
        env.pop("AWS_ACCOUNT_ID", None)
        
        result = runner.invoke(dev, ["deploy", "--target", "cloud"], env=env)
        assert result.exit_code == 1
        assert "Missing required environment variables" in result.output

def test_dev_deploy_cloud_with_env(runner, temp_project):
    """Test deploying to cloud with required environment variables"""
    with runner.isolated_filesystem():
        os.chdir(temp_project)
        env = os.environ.copy()
        env["AWS_REGION"] = "us-east-1"
        env["AWS_ACCOUNT_ID"] = "123456789"
        
        result = runner.invoke(dev, ["deploy", "--target", "cloud", "--dry-run"], env=env)
        assert result.exit_code == 0
        assert "Deploy to cloud" in result.output

def test_dev_deploy_invalid_target(runner, temp_project):
    """Test deploying to non-existent target"""
    with runner.isolated_filesystem():
        os.chdir(temp_project)
        result = runner.invoke(dev, ["deploy", "--target", "invalid"])
        assert result.exit_code == 1
        assert "Unknown deployment target 'invalid'" in result.output
        assert "Available targets:" in result.output
        assert "local" in result.output
        assert "cloud" in result.output

def test_dev_run_custom_command(runner, temp_project):
    """Test running custom command"""
    with runner.isolated_filesystem():
        os.chdir(temp_project)
        result = runner.invoke(dev, ["run", "generate-data", "--dry-run"])
        assert result.exit_code == 0
        assert "Generate synthetic test data" in result.output
        assert "echo 'Generating test data'" in result.output

def test_dev_run_invalid_command(runner, temp_project):
    """Test running non-existent custom command"""
    with runner.isolated_filesystem():
        os.chdir(temp_project)
        result = runner.invoke(dev, ["run", "invalid"])
        assert result.exit_code == 1
        assert "Unknown custom command 'invalid'" in result.output
        assert "Available commands:" in result.output
        assert "generate-data" in result.output
        assert "coverage" in result.output

@patch('subprocess.run')
def test_dev_command_failure(mock_run, runner, temp_project):
    """Test command execution failure"""
    mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="Error occurred")
    
    with runner.isolated_filesystem():
        os.chdir(temp_project)
        result = runner.invoke(dev, ["setup"])
        assert result.exit_code == 1
        assert "Command failed with exit code 1" in result.output

def test_dev_verbose_mode(runner, temp_project):
    """Test verbose mode output"""
    with runner.isolated_filesystem():
        os.chdir(temp_project)
        result = runner.invoke(dev, ["setup", "--dry-run", "--verbose"])
        assert result.exit_code == 0
        # In dry-run mode, verbose doesn't change output much
        assert "[DRY RUN] Would execute:" in result.output

def test_load_lifecycle_config():
    """Test loading lifecycle configuration"""
    site_config = {
        "lifecycle": {
            "setup": {"commands": ["test"]}
        }
    }
    
    result = load_lifecycle_config(site_config)
    assert result == site_config["lifecycle"]
    
    # Test with missing lifecycle
    with pytest.raises(Exception) as exc_info:
        load_lifecycle_config({})
    assert "No lifecycle configuration found" in str(exc_info.value)

def test_check_required_env():
    """Test environment variable checking"""
    # Set one variable
    os.environ["TEST_VAR1"] = "value1"
    
    # Should pass with set variable
    check_required_env(["TEST_VAR1"])
    
    # Should fail with missing variable
    with pytest.raises(Exception) as exc_info:
        check_required_env(["TEST_VAR1", "TEST_VAR2"])
    assert "Missing required environment variables: TEST_VAR2" in str(exc_info.value)
    
    # Clean up
    del os.environ["TEST_VAR1"]

def test_run_command_cross_platform():
    """Test command execution cross-platform compatibility"""
    # Test dry run
    result = run_command("echo test", dry_run=True)
    assert result.returncode == 0
    
    # Test actual execution (simple echo should work everywhere)
    result = run_command("echo test")
    assert result.returncode == 0

def test_run_command_list_with_conditions():
    """Test running command list with various conditions"""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        
        commands = [
            "echo 'First command'",
            {
                "command": "echo 'Second command'",
                "name": "Custom name"
            },
            {
                "command": "echo 'Should be skipped'",
                "name": "Conditional command",
                "condition": "if_not_exists:test.txt"
            }
        ]
        
        # Create the file to trigger the condition
        (tmpdir_path / "test.txt").touch()
        
        # This should work without errors in dry-run mode
        run_command_list(commands, "Test commands", dry_run=True, cwd=tmpdir_path)

def test_no_lifecycle_config_error(runner, temp_project):
    """Test error when lifecycle config is missing for specific commands"""
    # Remove lifecycle config
    config_path = temp_project / "mxcp-site.yml"
    with open(config_path) as f:
        config = yaml.safe_load(f)
    del config["lifecycle"]
    with open(config_path, "w") as f:
        yaml.dump(config, f)
    
    with runner.isolated_filesystem():
        os.chdir(temp_project)
        
        # All commands should fail with no lifecycle config
        for cmd in ["setup", "test", "deploy --target local", "run test"]:
            result = runner.invoke(dev, cmd.split())
            assert result.exit_code == 1
            assert "No lifecycle configuration found" in result.output 