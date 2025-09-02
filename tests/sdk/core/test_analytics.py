"""
Comprehensive tests for mxcp.sdk.core.analytics module.

This test suite covers all aspects of the analytics functionality including:
- PostHog client initialization and configuration
- Event tracking with various property types
- Command tracking with success/failure scenarios
- Timing decorator functionality
- Environment variable opt-out behavior
- Error handling and fault tolerance
- Thread safety and asynchronous operations
"""

import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import Mock, patch

import pytest

from mxcp.sdk.core.analytics import (
    PACKAGE_VERSION,
    POSTHOG_API_KEY,
    POSTHOG_HOST,
    POSTHOG_TIMEOUT,
    analytics_executor,
    initialize_analytics,
    is_analytics_opted_out,
    track_base_command,
    track_command,
    track_command_with_timing,
    track_event,
)


class TestAnalyticsConfiguration:
    """Test configuration and initialization of analytics."""

    def test_package_version_detection(self):
        """Test that package version is properly detected."""
        assert PACKAGE_VERSION is not None
        assert isinstance(PACKAGE_VERSION, str)
        assert len(PACKAGE_VERSION) > 0

    def test_analytics_constants(self):
        """Test that analytics constants are properly configured."""
        assert POSTHOG_API_KEY == "phc_6BP2PRVBewZUihdpac9Qk6QHd4eXykdhrvoFncqBjl0"
        assert POSTHOG_HOST == "https://eu.i.posthog.com"
        assert POSTHOG_TIMEOUT == 1
        assert isinstance(analytics_executor, ThreadPoolExecutor)

    def test_opt_out_detection_true_values(self):
        """Test analytics opt-out detection with various true values."""
        test_values = ["1", "true", "True", "TRUE", "yes", "Yes", "YES"]

        for value in test_values:
            with patch.dict(os.environ, {"MXCP_DISABLE_ANALYTICS": value}):
                assert is_analytics_opted_out() is True

    def test_opt_out_detection_false_values(self):
        """Test analytics opt-out detection with various false values."""
        test_values = ["0", "false", "False", "no", "No", ""]

        for value in test_values:
            with patch.dict(os.environ, {"MXCP_DISABLE_ANALYTICS": value}):
                assert is_analytics_opted_out() is False

    def test_opt_out_detection_no_env_var(self):
        """Test analytics opt-out detection when environment variable is not set."""
        with patch.dict(os.environ, {}, clear=True):
            if "MXCP_DISABLE_ANALYTICS" in os.environ:
                del os.environ["MXCP_DISABLE_ANALYTICS"]
            assert is_analytics_opted_out() is False


class TestAnalyticsInitialization:
    """Test analytics initialization with different scenarios."""

    @patch("mxcp.sdk.core.analytics.Posthog")
    def test_initialize_analytics_when_enabled(self, mock_posthog):
        """Test analytics initialization when not opted out."""
        mock_client = Mock()
        mock_posthog.return_value = mock_client

        with patch.dict(os.environ, {"MXCP_DISABLE_ANALYTICS": "false"}):
            with patch("mxcp.sdk.core.analytics.posthog_client", None):
                initialize_analytics()

                mock_posthog.assert_called_once_with(
                    project_api_key=POSTHOG_API_KEY,
                    host=POSTHOG_HOST,
                    debug=False,
                    sync_mode=False,
                    timeout=POSTHOG_TIMEOUT,
                )

    @patch("mxcp.sdk.core.analytics.Posthog")
    def test_initialize_analytics_when_opted_out(self, mock_posthog):
        """Test analytics initialization when opted out."""
        with patch.dict(os.environ, {"MXCP_DISABLE_ANALYTICS": "true"}):
            with patch("mxcp.sdk.core.analytics.posthog_client", None):
                initialize_analytics()

                mock_posthog.assert_not_called()


class TestEventTracking:
    """Test event tracking functionality."""

    @patch("mxcp.sdk.core.analytics.posthog_client")
    def test_track_event_basic(self, mock_client):
        """Test basic event tracking."""
        mock_client.capture = Mock()

        with patch.dict(os.environ, {"MXCP_DISABLE_ANALYTICS": "false"}):
            track_event("test_event")

            # Wait for async operation
            time.sleep(0.1)

            # Verify the event was tracked
            mock_client.capture.assert_called_once()
            call_args = mock_client.capture.call_args

            assert call_args[1]["distinct_id"] == "anonymous"
            assert call_args[1]["event"] == "test_event"
            assert call_args[1]["properties"]["app"] == "mxcp"
            assert call_args[1]["properties"]["version"] == PACKAGE_VERSION

    @patch("mxcp.sdk.core.analytics.posthog_client")
    def test_track_event_with_properties(self, mock_client):
        """Test event tracking with custom properties."""
        mock_client.capture = Mock()

        custom_props = {"feature": "config_load", "success": True, "file_size": 1024}

        with patch.dict(os.environ, {"MXCP_DISABLE_ANALYTICS": "false"}):
            track_event("config_loaded", custom_props)

            # Wait for async operation
            time.sleep(0.1)

            # Verify the event was tracked with custom properties
            mock_client.capture.assert_called_once()
            call_args = mock_client.capture.call_args

            properties = call_args[1]["properties"]
            assert properties["app"] == "mxcp"
            assert properties["version"] == PACKAGE_VERSION
            assert properties["feature"] == "config_load"
            assert properties["success"] is True
            assert properties["file_size"] == 1024

    @patch("mxcp.sdk.core.analytics.posthog_client")
    def test_track_event_when_opted_out(self, mock_client):
        """Test that events are not tracked when opted out."""
        mock_client.capture = Mock()

        with patch.dict(os.environ, {"MXCP_DISABLE_ANALYTICS": "true"}):
            track_event("test_event")

            # Wait for potential async operation
            time.sleep(0.1)

            # Verify no events were tracked
            mock_client.capture.assert_not_called()

    @patch("mxcp.sdk.core.analytics.posthog_client")
    def test_track_event_client_none(self, mock_client):
        """Test event tracking when client is None."""

        with patch.dict(os.environ, {"MXCP_DISABLE_ANALYTICS": "false"}):
            # This should not raise an exception
            track_event("test_event")

            # Wait for potential async operation
            time.sleep(0.1)

    @patch("mxcp.sdk.core.analytics.posthog_client")
    def test_track_event_error_handling(self, mock_client):
        """Test that analytics errors are handled gracefully."""
        mock_client.capture = Mock(side_effect=Exception("Analytics error"))

        with patch.dict(os.environ, {"MXCP_DISABLE_ANALYTICS": "false"}):
            # This should not raise an exception
            track_event("test_event")

            # Wait for async operation
            time.sleep(0.1)

            # Verify capture was called but error was handled
            mock_client.capture.assert_called_once()


class TestCommandTracking:
    """Test command tracking functionality."""

    @patch("mxcp.sdk.core.analytics.track_event")
    def test_track_command_success(self, mock_track_event):
        """Test tracking successful command execution."""
        track_command("validate", True, duration_ms=150.2)

        expected_properties = {"command": "validate", "success": True, "duration_ms": 150.2}

        mock_track_event.assert_called_once_with("cli_command_executed", expected_properties)

    @patch("mxcp.sdk.core.analytics.track_event")
    def test_track_command_failure(self, mock_track_event):
        """Test tracking failed command execution."""
        track_command("run", False, error="Configuration not found", duration_ms=25.8)

        expected_properties = {
            "command": "run",
            "success": False,
            "error": "Configuration not found",
            "duration_ms": 25.8,
        }

        mock_track_event.assert_called_once_with("cli_command_executed", expected_properties)

    @patch("mxcp.sdk.core.analytics.track_event")
    def test_track_command_minimal(self, mock_track_event):
        """Test tracking command with minimal parameters."""
        track_command("init", True)

        expected_properties = {"command": "init", "success": True}

        mock_track_event.assert_called_once_with("cli_command_executed", expected_properties)

    @patch("mxcp.sdk.core.analytics.track_command")
    def test_track_base_command(self, mock_track_command):
        """Test tracking base command execution."""
        track_base_command()

        mock_track_command.assert_called_once_with("base", True)


class TestTimingDecorator:
    """Test the timing decorator functionality."""

    @patch("mxcp.sdk.core.analytics.track_command")
    def test_timing_decorator_success(self, mock_track_command):
        """Test timing decorator with successful function execution."""

        @track_command_with_timing("test_command")
        def test_function():
            time.sleep(0.1)  # Simulate some work
            return "success"

        result = test_function()

        assert result == "success"
        mock_track_command.assert_called_once()

        # Verify call arguments
        call_kwargs = mock_track_command.call_args.kwargs

        assert call_kwargs.get("command_name") == "test_command"
        assert call_kwargs.get("success") is True
        assert call_kwargs.get("error") is None
        assert call_kwargs.get("duration_ms") is not None
        assert call_kwargs.get("duration_ms") > 0

    @patch("mxcp.sdk.core.analytics.track_command")
    def test_timing_decorator_failure(self, mock_track_command):
        """Test timing decorator with function that raises exception."""

        @track_command_with_timing("failing_command")
        def failing_function():
            time.sleep(0.05)  # Simulate some work
            raise ValueError("Test error")

        with pytest.raises(ValueError, match="Test error"):
            failing_function()

        mock_track_command.assert_called_once()

        # Verify call arguments
        call_kwargs = mock_track_command.call_args.kwargs

        assert call_kwargs.get("command_name") == "failing_command"
        assert call_kwargs.get("success") is False
        assert call_kwargs.get("error") == "Test error"
        assert call_kwargs.get("duration_ms") is not None
        assert call_kwargs.get("duration_ms") > 0

    def test_timing_decorator_preserves_metadata(self):
        """Test that timing decorator preserves function metadata."""

        @track_command_with_timing("test_command")
        def documented_function():
            """This is a test function."""
            return "test"

        assert documented_function.__name__ == "documented_function"
        assert documented_function.__doc__ == "This is a test function."

    @patch("mxcp.sdk.core.analytics.track_command")
    def test_timing_decorator_with_args_kwargs(self, mock_track_command):
        """Test timing decorator with function that takes arguments."""

        @track_command_with_timing("parametrized_command")
        def parametrized_function(arg1, arg2, kwarg1=None):
            return f"{arg1}-{arg2}-{kwarg1}"

        result = parametrized_function("test", "value", kwarg1="keyword")

        assert result == "test-value-keyword"
        mock_track_command.assert_called_once()

        # Verify tracking was called correctly
        call_kwargs = mock_track_command.call_args.kwargs
        assert call_kwargs.get("command_name") == "parametrized_command"
        assert call_kwargs.get("success") is True


class TestThreadSafety:
    """Test thread safety of analytics operations."""

    @patch("mxcp.sdk.core.analytics.posthog_client")
    def test_concurrent_event_tracking(self, mock_client):
        """Test concurrent event tracking from multiple threads."""
        mock_client.capture = Mock()

        def track_events():
            for i in range(5):
                track_event(f"event_{threading.current_thread().name}_{i}")

        threads = []
        for i in range(3):
            thread = threading.Thread(target=track_events, name=f"thread_{i}")
            threads.append(thread)
            thread.start()

        for thread in threads:
            thread.join()

        # Wait for all async operations
        time.sleep(0.5)

        # Verify all events were tracked
        assert mock_client.capture.call_count == 15  # 3 threads * 5 events each

    @patch("mxcp.sdk.core.analytics.track_command")
    def test_concurrent_decorator_usage(self, mock_track_command):
        """Test concurrent usage of timing decorator."""

        @track_command_with_timing("concurrent_command")
        def concurrent_function(thread_id):
            time.sleep(0.1)
            return f"result_{thread_id}"

        def run_function(thread_id):
            return concurrent_function(thread_id)

        threads = []
        results = []

        for i in range(3):
            thread = threading.Thread(target=lambda i=i: results.append(run_function(i)))
            threads.append(thread)
            thread.start()

        for thread in threads:
            thread.join()

        # Verify all commands were tracked
        assert mock_track_command.call_count == 3
        assert len(results) == 3


class TestErrorHandling:
    """Test error handling and fault tolerance."""

    @patch("mxcp.sdk.core.analytics.posthog_client")
    def test_posthog_client_error_handling(self, mock_client):
        """Test error handling when PostHog client raises exceptions."""
        mock_client.capture = Mock(side_effect=Exception("PostHog error"))

        with patch.dict(os.environ, {"MXCP_DISABLE_ANALYTICS": "false"}):
            # This should not raise an exception
            track_event("test_event")

            # Wait for async operation
            time.sleep(0.1)

            # Verify capture was called
            mock_client.capture.assert_called_once()

    @patch("mxcp.sdk.core.analytics.analytics_executor")
    def test_thread_pool_error_handling(self, mock_executor):
        """Test error handling when thread pool operations fail."""
        mock_executor.submit = Mock(side_effect=Exception("Thread pool error"))

        with patch.dict(os.environ, {"MXCP_DISABLE_ANALYTICS": "false"}):
            with patch("mxcp.sdk.core.analytics.posthog_client", Mock()):
                # This should not raise an exception
                track_event("test_event")

    @patch("mxcp.sdk.core.analytics.track_command")
    def test_decorator_analytics_error_handling(self, mock_track_command):
        """Test that decorator still works when analytics tracking fails."""
        mock_track_command.side_effect = Exception("Analytics error")

        @track_command_with_timing("error_command")
        def test_function():
            return "success"

        # Function should still execute successfully
        result = test_function()
        assert result == "success"

        # Analytics was attempted
        mock_track_command.assert_called_once()
