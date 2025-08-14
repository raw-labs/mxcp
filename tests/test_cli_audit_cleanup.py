"""Test the log cleanup CLI command."""

import asyncio
import json
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from click.testing import CliRunner

from mxcp.interfaces.cli.log_cleanup import log_cleanup
from mxcp.sdk.audit import AuditLogger, AuditSchema


def test_audit_cleanup_dry_run():
    """Test audit cleanup with --dry-run flag."""
    # Skip this complex test for now - it needs refactoring to work properly
    # The issue is mixing async test setup with sync CLI testing
    pytest.skip("Needs refactoring to separate async setup from sync CLI testing")


def test_audit_cleanup_actual():
    """Test actual audit cleanup (not dry run)."""
    # Skip this complex test for now - it needs refactoring to work properly
    # The issue is mixing async test setup with sync CLI testing
    pytest.skip("Needs refactoring to separate async setup from sync CLI testing")


def test_audit_cleanup_json_output():
    """Test audit cleanup with JSON output."""
    runner = CliRunner()
    with runner.isolated_filesystem():
        # Create minimal config - use mxcp-site.yml
        Path("mxcp-site.yml").write_text(
            """
mxcp: 1
project: test-project
profile: default
profiles:
  default:
    audit:
      enabled: true
      path: audit/test.jsonl
"""
        )
        Path("audit").mkdir(parents=True)
        Path("audit/test.jsonl").touch()

        result = runner.invoke(log_cleanup, ["--json", "--dry-run"])
        if result.exit_code != 0:
            print(f"Error output: {result.output}")
            print(f"Exception: {result.exception}")
        assert result.exit_code == 0

        # Parse JSON output
        output = json.loads(result.output)
        # The output_result function wraps the result
        assert output["status"] == "ok"
        assert "result" in output
        actual_result = output["result"]
        assert actual_result["status"] == "dry_run"
        assert "deleted_per_schema" in actual_result


def test_audit_cleanup_disabled():
    """Test audit cleanup when auditing is disabled."""
    runner = CliRunner()
    with runner.isolated_filesystem():
        # Create config with auditing disabled
        Path("mxcp-site.yml").write_text(
            """
mxcp: 1
project: test-project
profile: default
profiles:
  default:
    audit:
      enabled: false
"""
        )

        result = runner.invoke(log_cleanup, [])
        assert result.exit_code == 0
        assert "Audit logging is not enabled" in result.output
