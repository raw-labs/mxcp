import pytest
import json
import os
from pathlib import Path
from click.testing import CliRunner
from mxcp.cli.run import run_endpoint


@pytest.fixture(scope="session", autouse=True)
def set_mxcp_config_env():
    os.environ["MXCP_CONFIG"] = str(
        Path(__file__).parent / "fixtures" / "cli-run" / "mxcp-config.yml"
    )


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def temp_json_file(tmp_path):
    data = {"nested": {"array": [1, 2, 3], "object": {"key": "value"}}}
    file_path = tmp_path / "test.json"
    with open(file_path, "w") as f:
        json.dump(data, f)
    return file_path


@pytest.fixture(autouse=True)
def chdir_to_fixtures():
    """Change to the fixtures directory for each test"""
    original_dir = os.getcwd()
    fixtures_dir = Path(__file__).parent / "fixtures" / "cli-run"
    os.chdir(fixtures_dir)
    yield
    os.chdir(original_dir)


def test_simple_parameters(runner):
    result = runner.invoke(run_endpoint, ["tool", "test_tool", "--param", "name=value"])
    print("CLI OUTPUT:\n", result.output)
    assert result.exit_code == 0


def test_json_file_parameter(runner, temp_json_file):
    result = runner.invoke(
        run_endpoint,
        [
            "tool",
            "test_tool",
            "--param",
            "name=test",
            "--param",
            f"data=@{temp_json_file.resolve()}",
        ],
    )
    assert result.exit_code == 0


def test_invalid_json_file(runner, tmp_path):
    invalid_file = tmp_path / "invalid.json"
    invalid_file.write_text("invalid json")

    result = runner.invoke(
        run_endpoint, ["tool", "test_tool", "--param", f"data=@{invalid_file.resolve()}"]
    )
    assert result.exit_code != 0
    assert "Invalid JSON" in result.output


def test_nonexistent_json_file(runner):
    result = runner.invoke(
        run_endpoint, ["tool", "test_tool", "--param", "data=@/nonexistent.json"]
    )
    assert result.exit_code != 0
    assert "JSON file not found" in result.output


def test_mixed_parameters(runner, temp_json_file):
    result = runner.invoke(
        run_endpoint,
        [
            "tool",
            "test_tool",
            "--param",
            "name=value",
            "--param",
            f"data=@{temp_json_file.resolve()}",
        ],
    )
    assert result.exit_code == 0


def test_invalid_parameter_format(runner):
    result = runner.invoke(run_endpoint, ["tool", "test_tool", "--param", "invalid"])
    assert result.exit_code != 0
    assert "Parameter must be in format" in result.output
