import json
import subprocess
from pathlib import Path

import pytest


def test_lint_command_runs():
    """Test that the lint command runs without error."""
    result = subprocess.run(["mxcp", "lint", "--help"], capture_output=True, text=True)

    assert result.returncode == 0
    assert "Check endpoints for missing but recommended metadata" in result.stdout


def test_lint_with_json_output(tmp_path):
    """Test lint command with JSON output."""
    # Create a minimal mxcp-site.yml
    site_config = tmp_path / "mxcp-site.yml"
    site_config.write_text(
        """
mxcp: 1
project: test-lint
profile: default
"""
    )

    # Create tools directory following new organized structure
    tools_dir = tmp_path / "tools"
    tools_dir.mkdir()

    # Create a minimal endpoint without tests or examples (should trigger lint warnings)
    endpoint_file = tools_dir / "test.yml"
    endpoint_file.write_text(
        """
mxcp: 1
tool:
  name: test_tool
  description: "A test tool"
  parameters:
    - name: param1
      type: string
      description: "A parameter"
  return:
    type: string
  source:
    code: "SELECT $param1 as result"
"""
    )

    # Run lint command
    result = subprocess.run(
        ["mxcp", "lint", "--json-output"], cwd=tmp_path, capture_output=True, text=True
    )

    assert result.returncode == 0

    # Parse JSON output
    output = json.loads(result.stdout)
    assert output["status"] == "ok"
    assert isinstance(output["result"], list)

    # Should have warnings for missing tests and examples
    issues = output["result"]
    assert len(issues) > 0

    # Check for expected warnings
    severities = [issue["severity"] for issue in issues]
    assert "warning" in severities

    # Check for missing tests warning
    messages = [issue["message"] for issue in issues]
    assert any("no tests defined" in msg for msg in messages)
    assert any("missing examples" in msg for msg in messages)
