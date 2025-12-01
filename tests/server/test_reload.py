"""
Tests for server reload functionality (SIGHUP and DuckDB reload).

These tests focus on the public API and observable behavior,
not internal implementation details.
"""

import asyncio
import signal
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from mxcp.server.core.config.models import SiteConfigModel, UserConfigModel
from mxcp.server.core.reload import ReloadManager, ReloadableServer
from mxcp.server.interfaces.server.mcp import RAWMCP


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

        # Set up the event loop for signal handling
        loop = asyncio.new_event_loop()
        server._signal_loop = loop

        # Set up the methods we need
        server.reload_configuration = RAWMCP.reload_configuration.__get__(server, RAWMCP)
        server._handle_reload_signal = RAWMCP._handle_reload_signal.__get__(server, RAWMCP)
        server._handle_reload_signal_async = RAWMCP._handle_reload_signal_async.__get__(
            server, RAWMCP
        )

        # Mock load_site_config and load_user_config
        with patch(
            "mxcp.server.interfaces.server.mcp.load_site_config",
            return_value=self._minimal_site_config(),
        ):
            with patch(
                "mxcp.server.interfaces.server.mcp.load_user_config",
                return_value=UserConfigModel.model_validate({}),
            ):
                try:
                    # Simulate SIGHUP - this schedules the async handler
                    server._handle_reload_signal(signal.SIGHUP, None)

                    # Run the loop briefly to execute the scheduled task
                    loop.run_until_complete(asyncio.sleep(0.1))

                    # Verify reload_manager.request_reload was called
                    server.reload_manager.request_reload.assert_called_once()
                finally:
                    loop.close()

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
            with patch(
                "mxcp.server.interfaces.server.mcp.load_user_config",
                return_value=UserConfigModel.model_validate({}),
            ):
                server.reload_configuration()

                # Verify reload was requested
                server.reload_manager.request_reload.assert_called_once()

                # Check that a payload function was provided
                call_args = server.reload_manager.request_reload.call_args
                assert call_args[1]["payload_func"] is not None
                assert "Configuration reload (SIGHUP)" in call_args[1]["description"]


class TestReloadManagerShutdown:
    """Test ReloadManager behavior during shutdown scenarios."""

    @staticmethod
    def _create_mock_server() -> MagicMock:
        """Create a mock server implementing ReloadableServer protocol."""
        server = MagicMock(spec=ReloadableServer)
        server.active_requests = 0
        server.draining = False
        server.profile_name = "test"
        return server

    @pytest.mark.asyncio
    async def test_request_reload_after_stop_returns_completed_noop(self):
        """Test that request_reload after stop() returns a no-op request that's already complete."""
        server = self._create_mock_server()
        manager = ReloadManager(server)

        # Start and then stop the manager
        manager.start()
        await manager.stop()

        # Request reload after stop - should return immediately completed request
        request = manager.request_reload(description="After shutdown")

        # Should be immediately complete (not block for 60 seconds)
        completed = request.wait_for_completion(timeout=0.1)
        assert completed, "Request should be immediately complete after shutdown"

    @pytest.mark.asyncio
    async def test_request_reload_before_start_returns_completed_noop(self):
        """Test that request_reload before start() returns a no-op request that's already complete."""
        server = self._create_mock_server()
        manager = ReloadManager(server)

        # Don't call start() - manager is not running

        # Request reload before start - should return immediately completed request
        request = manager.request_reload(description="Before start")

        # Should be immediately complete
        completed = request.wait_for_completion(timeout=0.1)
        assert completed, "Request should be immediately complete before start"

    def test_sighup_during_shutdown_is_ignored(self):
        """Test that SIGHUP signals during shutdown are safely ignored."""
        # Create a minimal mock server
        server = MagicMock(spec=RAWMCP)
        server._signal_loop = None  # Simulates cleared during shutdown

        # Bind the real method
        server._handle_reload_signal = RAWMCP._handle_reload_signal.__get__(server, RAWMCP)

        # This should not raise and should not call reload_configuration
        server._handle_reload_signal(signal.SIGHUP, None)

        # reload_configuration should not be called since _signal_loop is None
        assert not hasattr(server, "reload_configuration") or not server.reload_configuration.called
