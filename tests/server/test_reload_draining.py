"""Comprehensive test suite for request draining and reload functionality.

This test suite covers:
1. Request draining during reload
2. Custom reload functionality
3. Execution locking
4. Concurrent request scenarios
5. Error handling and edge cases
"""

import asyncio
import concurrent.futures
import os
import signal
import threading
import time
from pathlib import Path
from typing import Any, Optional
from unittest.mock import MagicMock, patch, AsyncMock

import pytest
import yaml

from mxcp.server.core.config._types import SiteConfig, UserConfig
from mxcp.sdk.executor import ExecutionEngine
from mxcp.server.executor.engine import create_execution_engine
from mxcp.server.interfaces.server.mcp import RAWMCP
from mxcp.server.services.endpoints.service import execute_endpoint_with_engine


def patch_execute_endpoint():
    """Helper to patch endpoint execution to avoid file lookup issues."""

    async def mock_execute(*args, **kwargs):
        """Mock execution that returns immediately."""
        return {"status": "ok"}

    return patch("mxcp.server.interfaces.server.mcp.execute_endpoint_with_engine", new=mock_execute)


class MockExecutionEngine(ExecutionEngine):
    """Mock execution engine for testing."""

    def __init__(self):
        super().__init__()
        self.execute_call_count = 0
        self.shutdown_called = False
        self.startup_called = False
        self.execution_delay = 0  # Configurable delay for simulating long operations

    async def execute(
        self,
        language: str,
        endpoint_type: str,
        endpoint_name: str,
        code: str,
        file_path: Optional[str],
        params: dict[str, Any],
        input_schema: Optional[dict[str, Any]],
        output_schema: Optional[dict[str, Any]],
        user_context: Optional[Any] = None,
    ) -> Any:
        """Mock execute that can simulate delays."""
        self.execute_call_count += 1
        if self.execution_delay > 0:
            await asyncio.sleep(self.execution_delay)
        return {"result": f"mock result {self.execute_call_count}"}

    async def startup(self) -> None:
        """Track startup calls."""
        self.startup_called = True

    async def shutdown(self) -> None:
        """Track shutdown calls."""
        self.shutdown_called = True


class TestRequestDraining:
    """Test request draining functionality during reload."""

    @pytest.fixture
    def mock_server(self, tmp_path):
        """Create a mock RAWMCP server for testing."""
        # Create minimal configs
        site_config = {
            "version": 1,
            "mxcp": {
                "endpoint_dirs": ["endpoints"],
                "default_output_dir": str(tmp_path / "output"),
            },
        }

        user_config = {
            "version": 1,
            "projects": {
                "test": {
                    "profiles": {
                        "default": {
                            "secrets": [],
                            "settings": {},
                        }
                    }
                }
            },
        }

        # Create mock server - we'll bypass normal initialization
        server = RAWMCP.__new__(RAWMCP)

        # Set minimal required attributes directly
        server.site_config = site_config
        server.user_config = user_config
        server.profile_name = "default"
        server.transport = "stdio"
        server.readonly = False
        server.active_requests = 0
        server.requests_lock = threading.Lock()
        server.draining = False
        server.drain_complete = threading.Event()
        server.execution_lock = threading.RLock()
        server._shutdown_called = False
        server.site_config_path = tmp_path
        server.ref_tracker = MagicMock()
        server._config_templates_loaded = True
        server.active_profile = {"name": "default", "settings": {}}

        # Replace execution engine with mock
        server.execution_engine = MockExecutionEngine()

        # Mock the methods we need
        server._shutdown_runtime_components = MagicMock()
        server._initialize_runtime_components = MagicMock()

        # Create required directory structure
        (tmp_path / "mxcp-site.yml").write_text("version: 1\nmxcp:\n  endpoint_dirs: []\n")

        return server

    @pytest.mark.asyncio
    async def test_requests_complete_before_reload(self, mock_server):
        """Test that active requests complete before reload proceeds."""
        # Track reload progress
        reload_started = threading.Event()
        reload_completed = threading.Event()

        # Manually simulate active requests
        with mock_server.requests_lock:
            mock_server.active_requests = 2  # Simulate 2 active requests

        def reload_func():
            """Custom reload function that tracks progress."""
            reload_started.set()
            time.sleep(0.1)  # Simulate some work
            reload_completed.set()

        # Start reload in a separate thread (simulating SIGHUP handler)
        reload_thread = threading.Thread(
            target=lambda: mock_server.reload_with_custom_logic(reload_func)
        )
        reload_thread.start()

        # Give reload time to start draining
        await asyncio.sleep(0.1)

        # Verify reload is waiting (draining flag set, but reload not started)
        assert mock_server.draining
        assert not reload_started.is_set()
        assert mock_server.active_requests == 2  # Still has active requests

        # Simulate one request completing
        with mock_server.requests_lock:
            mock_server.active_requests -= 1

        await asyncio.sleep(0.1)

        # Still waiting - one request remains
        assert not reload_started.is_set()

        # Simulate last request completing
        with mock_server.requests_lock:
            mock_server.active_requests -= 1
            if mock_server.active_requests == 0 and mock_server.draining:
                mock_server.drain_complete.set()

        # Now reload should proceed
        reload_thread.join(timeout=2.0)
        assert reload_started.is_set()
        assert reload_completed.is_set()
        assert not mock_server.draining
        assert mock_server.active_requests == 0

    @pytest.mark.asyncio
    async def test_new_requests_wait_during_draining(self, mock_server):
        """Test that new requests wait while draining is in progress."""
        with patch_execute_endpoint():
            # Start draining
            mock_server.draining = True

            wait_times = []

            async def timed_request():
                """Request that measures wait time."""
                start = time.time()
                result = await mock_server._execute_with_draining(
                    endpoint_type="tool",
                    name="test",
                    params={},
                )
                wait_time = time.time() - start
                wait_times.append(wait_time)
                return result

            # Start request while draining
            request_task = asyncio.create_task(timed_request())

            # Let it wait a bit
            await asyncio.sleep(0.5)

            # Stop draining
            mock_server.draining = False

            # Request should now complete
            await request_task

            # Verify it waited
            assert len(wait_times) == 1
            assert wait_times[0] >= 0.5  # Should have waited at least 0.5 seconds

    @pytest.mark.asyncio
    async def test_draining_timeout(self, mock_server):
        """Test that requests timeout if draining takes too long."""
        with patch_execute_endpoint():
            # Start draining
            mock_server.draining = True

            # Patch the timeout to be shorter for testing
            with patch("mxcp.server.interfaces.server.mcp.time.time") as mock_time:
                # Mock time to simulate timeout
                mock_time.side_effect = [0, 0, 31, 31]  # Start time, check time, timeout

                with pytest.raises(RuntimeError, match="Service is reloading"):
                    await mock_server._execute_with_draining(
                        endpoint_type="tool",
                        name="test",
                        params={},
                    )

    def test_execution_lock_prevents_concurrent_execution(self, mock_server):
        """Test that execution lock prevents concurrent execution during reload."""
        execution_order = []

        def request_a():
            """First request."""
            with mock_server.execution_lock:
                execution_order.append("a_start")
                time.sleep(0.2)
                execution_order.append("a_end")

        def request_b():
            """Second request."""
            with mock_server.execution_lock:
                execution_order.append("b_start")
                time.sleep(0.1)
                execution_order.append("b_end")

        # Run concurrently in threads
        thread_a = threading.Thread(target=request_a)
        thread_b = threading.Thread(target=request_b)

        thread_a.start()
        thread_b.start()

        thread_a.join()
        thread_b.join()

        # Verify they didn't interleave
        assert execution_order in [
            ["a_start", "a_end", "b_start", "b_end"],
            ["b_start", "b_end", "a_start", "a_end"],
        ]

    @pytest.mark.asyncio
    async def test_custom_reload_function_called(self, mock_server):
        """Test that custom reload function is called correctly."""
        custom_called = threading.Event()
        custom_error = None

        def custom_rebuild():
            """Custom rebuild function."""
            try:
                # Simulate some database rebuilding
                custom_called.set()
                # Verify we're under exclusive lock
                assert mock_server.execution_lock._is_owned()
            except Exception as e:
                nonlocal custom_error
                custom_error = e
                raise

        # No active requests, should proceed immediately
        mock_server.reload_with_custom_logic(custom_rebuild)

        assert custom_called.is_set()
        assert custom_error is None
        assert not mock_server.draining

    @pytest.mark.asyncio
    async def test_custom_reload_error_handling(self, mock_server):
        """Test error handling in custom reload function."""

        def failing_rebuild():
            """Rebuild function that fails."""
            raise ValueError("Rebuild failed!")

        # Should raise and clean up properly
        with pytest.raises(ValueError, match="Rebuild failed!"):
            mock_server.reload_with_custom_logic(failing_rebuild)

        # Verify cleanup happened
        assert not mock_server.draining

    @pytest.mark.asyncio
    async def test_concurrent_requests_during_reload(self, mock_server):
        """Test multiple concurrent requests during reload."""
        # Simulate multiple active requests
        num_requests = 5
        with mock_server.requests_lock:
            mock_server.active_requests = num_requests

        # Track when reload completes
        reload_complete = threading.Event()

        def reload_func():
            """Custom reload function."""
            time.sleep(0.1)
            reload_complete.set()

        # Start reload in background
        reload_thread = threading.Thread(
            target=lambda: mock_server.reload_with_custom_logic(reload_func)
        )
        reload_thread.start()

        # Give reload time to start draining
        await asyncio.sleep(0.1)

        # Verify reload is waiting
        assert mock_server.draining
        assert not reload_complete.is_set()
        assert mock_server.active_requests == num_requests

        # Simulate requests completing one by one
        for i in range(num_requests):
            with mock_server.requests_lock:
                mock_server.active_requests -= 1
                if mock_server.active_requests == 0 and mock_server.draining:
                    mock_server.drain_complete.set()
            await asyncio.sleep(0.05)

        # Wait for reload to complete
        reload_thread.join(timeout=2.0)

        # Verify everything completed
        assert reload_complete.is_set()
        assert not mock_server.draining
        assert mock_server.active_requests == 0

    @pytest.mark.asyncio
    async def test_runtime_request_reload_api(self, mock_server):
        """Test the mxcp.runtime.request_reload API."""
        from mxcp.sdk.executor import ExecutionContext

        # Set up execution context with server reference
        context = ExecutionContext()
        context.set("_mxcp_server", mock_server)

        reload_called = threading.Event()

        def custom_rebuild():
            reload_called.set()

        # Mock get_execution_context to return our context
        with patch("mxcp.runtime.get_execution_context", return_value=context):
            from mxcp.runtime import request_reload

            # Test with custom function
            request_reload(custom_rebuild)
            assert reload_called.is_set()

            # Test without custom function (should use regular reload)
            mock_server.reload_configuration = MagicMock()
            request_reload()
            mock_server.reload_configuration.assert_called_once()

    def test_request_tracking_accuracy(self, mock_server):
        """Test that request counting is accurate even with errors."""

        def failing_request():
            """Request that fails."""
            with pytest.raises(ValueError):
                with mock_server.requests_lock:
                    mock_server.active_requests += 1
                try:
                    raise ValueError("Request failed!")
                finally:
                    with mock_server.requests_lock:
                        mock_server.active_requests -= 1

        # Even with failure, count should go back to 0
        initial_count = mock_server.active_requests
        failing_request()
        assert mock_server.active_requests == initial_count

    @pytest.mark.asyncio
    async def test_drain_complete_event(self, mock_server):
        """Test that drain_complete event is properly signaled."""
        # Start with active request
        mock_server.active_requests = 1
        mock_server.draining = True
        mock_server.drain_complete.clear()

        # Simulate request completion in another thread
        def complete_request():
            time.sleep(0.5)
            with mock_server.requests_lock:
                mock_server.active_requests = 0
                mock_server.drain_complete.set()

        thread = threading.Thread(target=complete_request)
        thread.start()

        # Wait for drain complete
        start = time.time()
        mock_server.drain_complete.wait(timeout=2.0)
        duration = time.time() - start

        thread.join()

        # Should have waited about 0.5 seconds
        assert 0.4 < duration < 0.7
        assert mock_server.active_requests == 0

    def test_reload_configuration_uses_common_pattern(self, mock_server):
        """Test that reload_configuration uses the common _reload_with_draining."""
        with patch.object(mock_server, "_reload_with_draining") as mock_reload:
            mock_server.reload_configuration()

            # Verify it was called with appropriate parameters
            mock_reload.assert_called_once()
            # Get the call args
            call_args = mock_reload.call_args

            # Check kwargs
            kwargs = call_args.kwargs
            assert "reload_func" in kwargs
            assert callable(kwargs["reload_func"])
            assert kwargs["operation_name"] == "configuration reload"
            assert kwargs["metric_name"] == "config_reloads_total"

    @pytest.mark.asyncio
    async def test_reload_with_mix_of_sql_and_python_endpoints(self, mock_server):
        """Test reload with both SQL and Python endpoints active."""
        with patch_execute_endpoint():
            sql_done = asyncio.Event()
            python_done = asyncio.Event()

            async def sql_request():
                """Simulate SQL endpoint."""
                await mock_server._execute_with_draining(
                    endpoint_type="tool",
                    name="sql_query",
                    params={"query": "SELECT 1"},
                )
                sql_done.set()

            async def python_request():
                """Simulate Python endpoint."""
                await mock_server._execute_with_draining(
                    endpoint_type="tool",
                    name="python_func",
                    params={"data": "test"},
                )
                python_done.set()

            # Start both types of requests
            sql_task = asyncio.create_task(sql_request())
            python_task = asyncio.create_task(python_request())

            # Give them time to start
            await asyncio.sleep(0.1)

            # Start reload
            reload_done = threading.Event()

            def reload_func():
                reload_done.set()

            reload_thread = threading.Thread(
                target=lambda: mock_server.reload_with_custom_logic(reload_func)
            )
            reload_thread.start()

            # Complete requests
            await asyncio.gather(sql_task, python_task)

            # Wait for reload
            reload_thread.join(timeout=2.0)

            # Verify everything completed
            assert sql_done.is_set()
            assert python_done.is_set()
            assert reload_done.is_set()

    @pytest.mark.asyncio
    async def test_signal_handler_integration(self, mock_server):
        """Test that SIGHUP handler integrates with draining."""
        # Mock the signal handler being called
        reload_called = threading.Event()

        with patch.object(mock_server, "reload_configuration") as mock_reload:

            def track_reload():
                reload_called.set()
                # Simulate the real reload_configuration behavior
                mock_server._reload_with_draining(
                    lambda: None,
                    operation_name="configuration reload",
                    metric_name="config_reloads_total",
                )

            mock_reload.side_effect = track_reload

            # Simulate SIGHUP
            mock_server._handle_reload_signal(signal.SIGHUP, None)

            # Verify reload was called
            assert reload_called.is_set()

    def test_engine_lifecycle_during_reload(self, mock_server):
        """Test that execution engine is properly shut down and recreated."""
        old_engine = mock_server.execution_engine

        # Track lifecycle
        shutdown_order = []

        # Mock the shutdown_runtime_components to track shutdown
        def mock_shutdown():
            shutdown_order.append("shutdown")
            # Simulate shutting down engine
            old_engine.shutdown_called = True

        mock_server._shutdown_runtime_components = mock_shutdown

        # Perform reload
        def rebuild():
            shutdown_order.append("rebuild")

        mock_server.reload_with_custom_logic(rebuild)

        # Verify order: shutdown -> rebuild
        assert shutdown_order == ["shutdown", "rebuild"]
        assert old_engine.shutdown_called

    def test_reentrant_lock_behavior(self, mock_server):
        """Test that RLock allows reentrant locking from same thread."""
        # This should work with RLock
        with mock_server.execution_lock:
            with mock_server.execution_lock:  # Reentrant
                assert mock_server.execution_lock._is_owned()

    def test_thread_safety_of_request_counting(self, mock_server):
        """Test thread-safe request counting under high concurrency."""
        num_threads = 20
        increments_per_thread = 100

        def increment_counter():
            for _ in range(increments_per_thread):
                with mock_server.requests_lock:
                    mock_server.active_requests += 1
                # Simulate some work
                time.sleep(0.0001)
                with mock_server.requests_lock:
                    mock_server.active_requests -= 1

        # Run many threads concurrently
        threads = []
        for _ in range(num_threads):
            t = threading.Thread(target=increment_counter)
            t.start()
            threads.append(t)

        # Wait for all to complete
        for t in threads:
            t.join()

        # Should be back to 0
        assert mock_server.active_requests == 0


class TestProductionScenarios:
    """Test production-relevant scenarios for reload functionality."""

    @pytest.fixture
    def production_server(self, tmp_path):
        """Create a more realistic server setup."""
        # Create config files
        site_config_path = tmp_path / "mxcp-site.yml"
        site_config_path.write_text(
            """
version: 1
mxcp:
  endpoint_dirs: 
    - sql
    - python
  plugin_dirs:
    - plugins
"""
        )

        user_config_path = tmp_path / "mxcp-config.yml"
        user_config_path.write_text(
            """
version: 1
projects:
  production:
    profiles:
      default:
        secrets:
          - name: api_secret
            type: custom
            parameters:
              key: "prod-key-123"
        settings:
          timeout: 30
          max_retries: 3
"""
        )

        # Create endpoint files
        sql_dir = tmp_path / "sql"
        sql_dir.mkdir()

        python_dir = tmp_path / "python"
        python_dir.mkdir()

        # Create configs directly
        site_config = {
            "version": 1,
            "mxcp": {
                "endpoint_dirs": ["sql", "python"],
                "plugin_dirs": ["plugins"],
                "default_output_dir": str(tmp_path / "output"),
            },
        }

        user_config = {
            "version": 1,
            "projects": {
                "production": {
                    "profiles": {
                        "default": {
                            "secrets": [
                                {
                                    "name": "api_secret",
                                    "type": "custom",
                                    "parameters": {"key": "prod-key-123"},
                                }
                            ],
                            "settings": {
                                "timeout": 30,
                                "max_retries": 3,
                            },
                        }
                    }
                }
            },
        }

        # Create mock server bypassing initialization
        server = RAWMCP.__new__(RAWMCP)
        server.site_config = site_config
        server.user_config = user_config
        server.profile_name = "default"
        server.transport = "http"
        server.readonly = False
        server.active_requests = 0
        server.requests_lock = threading.Lock()
        server.draining = False
        server.drain_complete = threading.Event()
        server.execution_lock = threading.RLock()
        server._shutdown_called = False
        server.site_config_path = tmp_path
        server.ref_tracker = MagicMock()
        server._config_templates_loaded = True
        server.active_profile = {"name": "default", "settings": {}}
        server.execution_engine = MockExecutionEngine()

        # Mock the methods we need
        server._shutdown_runtime_components = MagicMock()
        server._initialize_runtime_components = MagicMock()

        return server

    @pytest.mark.asyncio
    async def test_production_reload_with_active_database_migration(self, production_server):
        """Test reload during an active database migration scenario."""
        with patch_execute_endpoint():
            migration_phases = []

            async def long_migration():
                """Simulate a long-running database migration."""
                migration_phases.append("start")
                result = await production_server._execute_with_draining(
                    endpoint_type="tool",
                    name="migrate_database",
                    params={"version": "2.0"},
                )
                migration_phases.append("complete")
                return result

            def rebuild_database():
                """Rebuild function that updates schema."""
                migration_phases.append("rebuild_start")
                # Simulate rebuilding database file
                time.sleep(0.5)
                migration_phases.append("rebuild_complete")

            # Start migration
            migration_task = asyncio.create_task(long_migration())
            await asyncio.sleep(0.1)

            # Attempt reload while migration is active
            reload_thread = threading.Thread(
                target=lambda: production_server.reload_with_custom_logic(rebuild_database)
            )
            reload_thread.start()

            # Complete migration
            await migration_task
            reload_thread.join(timeout=5.0)

            # Verify correct order
            assert migration_phases == ["start", "complete", "rebuild_start", "rebuild_complete"]

    @pytest.mark.asyncio
    async def test_graceful_shutdown_during_reload(self, production_server):
        """Test graceful shutdown request during reload process."""
        # Start a reload that takes time
        reload_started = threading.Event()
        shutdown_requested = threading.Event()

        def slow_rebuild():
            reload_started.set()
            # Wait for shutdown signal
            for _ in range(50):  # 5 seconds max
                if shutdown_requested.is_set():
                    raise KeyboardInterrupt("Shutdown requested")
                time.sleep(0.1)

        reload_thread = threading.Thread(
            target=lambda: production_server.reload_with_custom_logic(slow_rebuild)
        )
        reload_thread.start()

        # Wait for reload to start
        reload_started.wait(timeout=2.0)

        # Request shutdown
        shutdown_requested.set()

        # Reload should handle the interrupt gracefully
        reload_thread.join(timeout=3.0)

        # Server should be in a consistent state
        assert not production_server.draining

    @pytest.mark.asyncio
    async def test_memory_pressure_during_reload(self, production_server):
        """Test reload behavior under memory pressure."""
        # Track memory allocations during reload
        allocations = []

        def memory_intensive_rebuild():
            """Rebuild that uses significant memory."""
            # Simulate loading large dataset
            large_data = [0] * (10 * 1024 * 1024)  # ~80MB
            allocations.append(len(large_data))

            # Process data
            time.sleep(0.1)

            # Clear to free memory
            large_data.clear()

        # Monitor active requests don't leak memory
        initial_requests = production_server.active_requests

        # Perform multiple reloads
        for i in range(3):
            production_server.reload_with_custom_logic(memory_intensive_rebuild)
            # Verify state is clean after each reload
            assert production_server.active_requests == initial_requests
            assert not production_server.draining

        # All allocations should have completed
        assert len(allocations) == 3
