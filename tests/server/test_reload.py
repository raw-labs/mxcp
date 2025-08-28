"""
Tests for server reload functionality (SIGHUP and DuckDB reload).

These tests focus on the public API and observable behavior,
not internal implementation details.
"""

import signal
from unittest.mock import MagicMock, patch

import pytest

from mxcp.server.interfaces.server.mcp import RAWMCP


class TestReloadFunctionality:
    """Test reload functionality for both SIGHUP and DuckDB reloads."""
    
    def test_sighup_triggers_full_reload(self):
        """Test that SIGHUP signal triggers full system reload."""
        # Create a minimal mock server
        server = MagicMock(spec=RAWMCP)
        server.draining = False
        server._config_templates_loaded = True
        server.ref_tracker = MagicMock()
        server.ref_tracker._template_config = True
        server.reload_configuration = RAWMCP.reload_configuration.__get__(server, RAWMCP)
        server._handle_reload_signal = RAWMCP._handle_reload_signal.__get__(server, RAWMCP)
        
        # Mock _drain_all_requests_and_reload
        server._drain_all_requests_and_reload = MagicMock()
        
        # Patch record_counter to avoid metric recording issues
        with patch('mxcp.server.interfaces.server.mcp.record_counter'):
            # Simulate SIGHUP
            server._handle_reload_signal(signal.SIGHUP, None)
            
            # Wait for the thread to complete
            import time
            time.sleep(0.1)
        
            # Verify reload_configuration was called which calls _drain_all_requests_and_reload
            server._drain_all_requests_and_reload.assert_called_once()
        
    def test_reload_duckdb_only_calls_executor(self):
        """Test that reload_duckdb_only properly calls the executor's reload method."""
        # Create a minimal mock server
        server = MagicMock(spec=RAWMCP)
        server.profile_name = "test"
        server.reload_duckdb_only = RAWMCP.reload_duckdb_only.__get__(server, RAWMCP)
        
        # Mock the DuckDB executor
        mock_executor = MagicMock()
        mock_executor.reload_connection = MagicMock()
        
        # Set up the execution engine
        server.execution_engine = MagicMock()
        server.execution_engine._executors = {"sql": mock_executor}
        
        # Mock isinstance check
        with patch('mxcp.server.interfaces.server.mcp.isinstance', return_value=True):
            # Call reload_duckdb_only
            server.reload_duckdb_only()
            
            # Verify the executor's reload_connection was called
            mock_executor.reload_connection.assert_called_once()
            
    @pytest.mark.asyncio
    async def test_runtime_reload_duckdb_api(self):
        """Test the mxcp.runtime.reload_duckdb API."""
        from mxcp.sdk.executor import ExecutionContext
        
        # Create mock server
        mock_server = MagicMock()
        mock_server.reload_duckdb_only = MagicMock()
        
        # Set up execution context
        context = ExecutionContext()
        context.set("_mxcp_server", mock_server)
        
        with patch("mxcp.runtime.get_execution_context", return_value=context):
            from mxcp.runtime import reload_duckdb
            
            # Call reload_duckdb
            reload_duckdb()
            
            # Verify it called the server's reload_duckdb_only method
            mock_server.reload_duckdb_only.assert_called_once()
            
    def test_reload_metrics_recorded(self):
        """Test that reload operations record appropriate metrics."""
        # Create a minimal mock server
        server = MagicMock(spec=RAWMCP)
        server.profile_name = "test"
        server.reload_configuration = RAWMCP.reload_configuration.__get__(server, RAWMCP)
        server.reload_duckdb_only = RAWMCP.reload_duckdb_only.__get__(server, RAWMCP)
        
        # Mock internal methods
        server._config_templates_loaded = True
        server._drain_all_requests_and_reload = MagicMock()
        server.ref_tracker = MagicMock()
        server.ref_tracker._template_config = True
        
        # Mock the DuckDB executor for reload_duckdb_only
        mock_executor = MagicMock()
        mock_executor.reload_connection = MagicMock()
        server.execution_engine = MagicMock()
        server.execution_engine._executors = {"sql": mock_executor}
        
        # Test 1: Successful config reload records success metric
        with patch('mxcp.server.interfaces.server.mcp.record_counter') as mock_counter:
            server.reload_configuration()
            
            # Verify success metric was recorded
            mock_counter.assert_called_with(
                "mxcp.config_reloads_total",
                attributes={"status": "success", "profile": "test"},
                description="Total configuration reload operations",
            )
            
        # Test 2: Failed config reload records error metric
        server._drain_all_requests_and_reload.side_effect = Exception("Reload failed")
        
        with patch('mxcp.server.interfaces.server.mcp.record_counter') as mock_counter:
            with pytest.raises(Exception):
                server.reload_configuration()
                
            # Verify error metric was recorded
            mock_counter.assert_called_with(
                "mxcp.config_reloads_total",
                attributes={"status": "error", "profile": "test"},
                description="Total configuration reload operations",
            )
            
        # Test 3: Successful DuckDB reload records success metric
        with patch('mxcp.server.interfaces.server.mcp.isinstance', return_value=True):
            with patch('mxcp.server.interfaces.server.mcp.record_counter') as mock_counter:
                server.reload_duckdb_only()
                
                # Verify success metric was recorded
                mock_counter.assert_called_with(
                    "mxcp.duckdb_reloads_total",
                    attributes={"status": "success", "profile": "test"},
                    description="Total DuckDB reload operations",
                )
