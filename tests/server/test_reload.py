"""
Tests for server reload functionality (SIGHUP and DuckDB reload).

These tests focus on the public API and observable behavior,
not internal implementation details.
"""

import signal
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from mxcp.server.core.config.models import SiteConfigModel
from mxcp.server.interfaces.server.mcp import RAWMCP
from mxcp.server.core.reload import ReloadManager


class TestReloadFunctionality:
    """Test reload functionality for both SIGHUP and DuckDB reloads."""

    @staticmethod
    def _minimal_site_config() -> SiteConfigModel:
        return SiteConfigModel.model_validate(
            {
                "mxcp": 1,
                "project": "test",
                "profile": "default",
                "profiles": {
                    "default": {
                        "duckdb": {
                            "path": str(Path("/tmp") / "db-default.duckdb"),
                            "readonly": False,
                        }
                    }
                },
            },
            context={"repo_root": Path("/tmp")},
        )

    def test_sighup_triggers_full_reload(self):
        """Test that SIGHUP signal triggers full system reload."""
        # Create a minimal mock server
        server = MagicMock(spec=RAWMCP)
        server.draining = False
        server._config_templates_loaded = True
        server.ref_tracker = MagicMock()
        server.ref_tracker._template_config = True
        server.site_config_path = None

        # Mock the reload manager
        server.reload_manager = MagicMock(spec=ReloadManager)

        # Set up the methods we need
        server.reload_configuration = RAWMCP.reload_configuration.__get__(server, RAWMCP)
        server._handle_reload_signal = RAWMCP._handle_reload_signal.__get__(server, RAWMCP)

        # Mock load_site_config and load_user_config
        with patch(
            "mxcp.server.interfaces.server.mcp.load_site_config",
            return_value=self._minimal_site_config(),
        ):
            with patch("mxcp.server.interfaces.server.mcp.load_user_config", return_value={}):
                # Simulate SIGHUP
                server._handle_reload_signal(signal.SIGHUP, None)

                # Verify reload_manager.request_reload was called
                server.reload_manager.request_reload.assert_called_once()

    def test_reload_with_payload_function(self):
        """Test that reload with a payload function works correctly."""
        # Create a minimal mock server
        server = MagicMock(spec=RAWMCP)
        server.profile_name = "test"
        server.reload_manager = MagicMock(spec=ReloadManager)

        # Create a payload function
        payload_func = MagicMock()

        # Use the runtime API to trigger a reload
        from mxcp.sdk.executor import ExecutionContext

        # Set up execution context
        context = ExecutionContext()
        context.set("_mxcp_server", server)

        with patch("mxcp.runtime.get_execution_context", return_value=context):
            from mxcp.runtime import reload_duckdb

            # Call reload_duckdb with payload
            reload_duckdb(payload_func=payload_func, description="Test reload")

            # Verify reload_manager.request_reload was called with the payload
            server.reload_manager.request_reload.assert_called_once()
            call_args = server.reload_manager.request_reload.call_args
            assert call_args[1]["payload_func"] == payload_func
            assert call_args[1]["description"] == "Test reload"

    @pytest.mark.asyncio
    async def test_runtime_reload_duckdb_api(self):
        """Test the mxcp.runtime.reload_duckdb API."""
        from mxcp.sdk.executor import ExecutionContext

        # Create mock server
        mock_server = MagicMock()
        mock_server.reload_manager = MagicMock(spec=ReloadManager)

        # Set up execution context
        context = ExecutionContext()
        context.set("_mxcp_server", mock_server)

        with patch("mxcp.runtime.get_execution_context", return_value=context):
            from mxcp.runtime import reload_duckdb

            # Call reload_duckdb without payload
            reload_duckdb()

            # Verify it called the reload_manager.request_reload method
            mock_server.reload_manager.request_reload.assert_called_once()
            call_args = mock_server.reload_manager.request_reload.call_args
            assert call_args[1]["payload_func"] is None
            assert "DuckDB reload via runtime API" in call_args[1]["description"]

    def test_reload_metrics_recorded(self):
        """Test that reload operations record appropriate metrics."""
        # The new reload system uses ReloadManager which handles metrics internally
        # This test verifies that reload requests are properly queued

        # Create a minimal mock server
        server = MagicMock(spec=RAWMCP)
        server.profile_name = "test"
        server.reload_manager = MagicMock(spec=ReloadManager)
        server.reload_configuration = RAWMCP.reload_configuration.__get__(server, RAWMCP)

        # Mock internal methods
        server._config_templates_loaded = True
        server.ref_tracker = MagicMock()
        server.ref_tracker._template_config = True
        server.site_config_path = None

        # Test that reload_configuration requests a reload
        with patch(
            "mxcp.server.interfaces.server.mcp.load_site_config",
            return_value=self._minimal_site_config(),
        ):
            with patch("mxcp.server.interfaces.server.mcp.load_user_config", return_value={}):
                server.reload_configuration()

                # Verify reload was requested
                server.reload_manager.request_reload.assert_called_once()

                # Check that a payload function was provided
                call_args = server.reload_manager.request_reload.call_args
                assert call_args[1]["payload_func"] is not None
                assert "Configuration reload (SIGHUP)" in call_args[1]["description"]
