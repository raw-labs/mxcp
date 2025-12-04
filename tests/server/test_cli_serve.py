"""Tests for the mxcp serve CLI command."""

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from mxcp.server.interfaces.cli.serve import serve


@pytest.fixture
def serve_error_repo():
    """Get path to the serve-errors test repository."""
    return Path(__file__).parent / "fixtures" / "serve-errors"


@pytest.fixture
def valid_repo():
    """Get path to a valid test repository (mcp fixture)."""
    return Path(__file__).parent / "fixtures" / "mcp"


@pytest.fixture
def runner():
    """Create a Click test runner."""
    return CliRunner()


class TestServeStrictValidation:
    """Tests for serve command strict validation behavior."""

    def test_serve_fails_with_invalid_endpoint(self, runner, serve_error_repo):
        """Test that serve fails by default when there are invalid endpoints."""
        original_dir = os.getcwd()
        os.environ["MXCP_CONFIG"] = str(serve_error_repo / "mxcp-config.yml")
        os.chdir(serve_error_repo)
        try:
            # Mock the server run so it doesn't actually start
            with patch(
                "mxcp.server.interfaces.cli.serve.run_async_cli",
                side_effect=KeyboardInterrupt,
            ):
                result = runner.invoke(serve, [])
            # Should fail (non-zero exit code due to Abort)
            assert result.exit_code != 0
            # Should show error message
            assert (
                "Server startup failed" in result.output
                or "endpoint(s) with errors" in result.output
            )
        finally:
            os.chdir(original_dir)

    def test_serve_fails_with_json_output(self, runner, serve_error_repo):
        """Test that serve outputs JSON error when --json-output is used."""
        original_dir = os.getcwd()
        os.environ["MXCP_CONFIG"] = str(serve_error_repo / "mxcp-config.yml")
        os.chdir(serve_error_repo)
        try:
            with patch(
                "mxcp.server.interfaces.cli.serve.run_async_cli",
                side_effect=KeyboardInterrupt,
            ):
                result = runner.invoke(serve, ["--json-output"])
            # Should fail (non-zero exit code due to Abort)
            assert result.exit_code != 0
            # Extract JSON from output (may have warning lines before/after)
            output = result.output
            # Find the JSON object in the output
            json_start = output.find("{")
            json_end = output.rfind("}") + 1
            if json_start >= 0 and json_end > json_start:
                json_str = output[json_start:json_end]
                try:
                    error_data = json.loads(json_str)
                    assert error_data["status"] == "error"
                    assert "failed_endpoints" in error_data
                    assert len(error_data["failed_endpoints"]) > 0
                except json.JSONDecodeError:
                    pytest.fail(f"Expected valid JSON in output, got: {result.output}")
            else:
                pytest.fail(f"Expected JSON output, got: {result.output}")
        finally:
            os.chdir(original_dir)

    def test_serve_shows_error_path_and_message(self, runner, serve_error_repo):
        """Test that error output includes endpoint path and error message."""
        original_dir = os.getcwd()
        os.environ["MXCP_CONFIG"] = str(serve_error_repo / "mxcp-config.yml")
        os.chdir(serve_error_repo)
        try:
            with patch(
                "mxcp.server.interfaces.cli.serve.run_async_cli",
                side_effect=KeyboardInterrupt,
            ):
                result = runner.invoke(serve, [])
            assert result.exit_code != 0
            # Should show the invalid tool path
            assert "invalid_tool" in result.output
            # Should show helpful tip about --ignore-errors
            assert "--ignore-errors" in result.output
        finally:
            os.chdir(original_dir)


class TestServeIgnoreErrors:
    """Tests for serve command --ignore-errors flag."""

    def test_serve_continues_with_ignore_errors(self, runner, serve_error_repo):
        """Test that serve continues when --ignore-errors is set."""
        original_dir = os.getcwd()
        os.environ["MXCP_CONFIG"] = str(serve_error_repo / "mxcp-config.yml")
        os.chdir(serve_error_repo)
        try:
            # Mock the server run to avoid actually starting
            with patch(
                "mxcp.server.interfaces.cli.serve.run_async_cli",
                side_effect=KeyboardInterrupt,
            ):
                result = runner.invoke(serve, ["--ignore-errors"])
            # The serve command won't show the "Server startup failed" error message
            # because --ignore-errors is set
            assert "Server startup failed" not in result.output
            assert "endpoint(s) with errors" not in result.output
        finally:
            os.chdir(original_dir)


class TestServeWithValidRepo:
    """Tests for serve command with a valid repository."""

    def test_serve_no_validation_errors_with_valid_repo(self, runner, valid_repo):
        """Test that serve doesn't show validation errors when all endpoints are valid."""
        original_dir = os.getcwd()
        os.environ["MXCP_CONFIG"] = str(valid_repo / "mxcp-config.yml")
        os.chdir(valid_repo)
        try:
            # Mock the server run to avoid actually starting
            with patch(
                "mxcp.server.interfaces.cli.serve.run_async_cli",
                side_effect=KeyboardInterrupt,
            ):
                result = runner.invoke(serve, [])
            # Should not show startup failed message
            assert "Server startup failed" not in result.output
            assert "endpoint(s) with errors" not in result.output
        finally:
            os.chdir(original_dir)
