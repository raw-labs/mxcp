"""
Analytics module for MXCP core functionality.

This module provides comprehensive analytics tracking capabilities for MXCP applications,
including event tracking, command execution monitoring, and performance metrics collection.
The analytics system is designed to be:

- **Non-blocking**: All analytics operations run asynchronously in background threads
- **Fault-tolerant**: Analytics failures never affect the main application flow
- **Privacy-respecting**: No personal data is collected, only anonymous usage statistics
- **Configurable**: Can be completely disabled via environment variables

Key Features:
    - PostHog integration for event tracking
    - Command execution timing and success/failure tracking
    - Thread-safe asynchronous operation
    - Comprehensive error handling
    - Environment-based opt-out mechanism

Quick Start:
    ```python
    from mxcp.sdk.core.analytics import initialize_analytics, track_event, track_command

    # Initialize analytics (call once at application startup)
    initialize_analytics()

    # Track custom events
    track_event("user_action", {"feature": "config_load", "success": True})

    # Track command execution
    track_command("validate", success=True, duration_ms=150.2)
    ```

Environment Variables:
    - `MXCP_DISABLE_ANALYTICS`: Set to "1", "true", or "yes" to disable all analytics

Thread Safety:
    This module is fully thread-safe and uses a dedicated thread pool for analytics operations.
"""

import contextlib
import functools
import hashlib
import logging
import os
import threading
import time
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

from posthog import Posthog

from mxcp.sdk.core.version import PACKAGE_NAME, PACKAGE_VERSION

POSTHOG_API_KEY = "phc_6BP2PRVBewZUihdpac9Qk6QHd4eXykdhrvoFncqBjl0"
POSTHOG_HOST = "https://eu.i.posthog.com"  # Fixed: EU region
POSTHOG_TIMEOUT = 10  # Timeout for HTTP requests (PostHog handles this in background thread)

# Global PostHog instance
posthog_client: Posthog | None = None

# Installation ID for anonymous but distinct user tracking
_installation_id: str | None = None
_installation_id_lock = threading.Lock()
_INSTALLATION_ID_FILE = Path.home() / ".config" / "mxcp" / "installation_id"


def _get_installation_id() -> str:
    """Get or create a unique installation ID for this machine.

    The ID is a random UUID generated on first run and stored in
    ~/.config/mxcp/installation_id. This allows tracking distinct
    installations without collecting any personal information.

    Users can delete this file to reset their installation ID,
    or set MXCP_DISABLE_ANALYTICS=1 to disable tracking entirely.

    Thread-safe: Uses a lock to prevent race conditions on first access.
    """
    global _installation_id

    # Fast path: return cached ID without lock
    if _installation_id is not None:
        return _installation_id

    # Slow path: acquire lock for initialization
    with _installation_id_lock:
        # Double-check after acquiring lock (another thread may have initialized)
        if _installation_id is not None:
            return _installation_id

        try:
            # Try to read existing ID
            if _INSTALLATION_ID_FILE.exists():
                cached_id = _INSTALLATION_ID_FILE.read_text().strip()
                if cached_id:
                    _installation_id = cached_id
                    return _installation_id

            # Generate new ID
            new_id = str(uuid.uuid4())

            # Save it (create directory if needed)
            _INSTALLATION_ID_FILE.parent.mkdir(parents=True, exist_ok=True)
            _INSTALLATION_ID_FILE.write_text(new_id)

            _installation_id = new_id
            return _installation_id
        except Exception:
            # If anything fails, use a session-only ID (not persisted)
            _installation_id = str(uuid.uuid4())
            return _installation_id


def _hash_name(name: str) -> str:
    """Hash an endpoint name for anonymous tracking.

    Returns first 12 characters of SHA256 hash - enough to identify patterns
    without revealing the actual name.
    """
    return hashlib.sha256(name.encode()).hexdigest()[:12]


def initialize_analytics() -> None:
    """
    Initialize PostHog analytics if not opted out.

    This function must be called once at application startup to enable analytics tracking.
    It creates a global PostHog client instance that will be used for all subsequent
    analytics operations.

    The initialization is safe to call multiple times - subsequent calls will be ignored
    if analytics is already initialized.

    PostHog Configuration:
        - Async mode (sync_mode=False): Events are queued and sent in background thread
        - flush_interval=0.5: Auto-flush every 0.5 seconds (PostHog default)
        - flush_at=100: Auto-flush when 100 events are queued (PostHog default)

    Note:
        We intentionally do NOT register an atexit handler to flush events.
        Analytics is non-critical, and blocking on process exit (which flush can do
        indefinitely on network issues) is unacceptable. PostHog's auto-flush handles
        the common case; some events may be lost on abrupt termination.

    Environment Variables:
        MXCP_DISABLE_ANALYTICS: Set to "1", "true", or "yes" to disable analytics

    Example:
        ```python
        from mxcp.sdk.core.analytics import initialize_analytics

        # Call once at application startup
        initialize_analytics()
        ```

    Note:
        This function is thread-safe and can be called from any thread.
    """
    global posthog_client
    if not is_analytics_opted_out() and posthog_client is None:
        posthog_client = Posthog(
            project_api_key=POSTHOG_API_KEY,
            host=POSTHOG_HOST,
            debug=False,
            sync_mode=False,  # Async mode: PostHog handles threading internally
            timeout=POSTHOG_TIMEOUT,
            # Default flush_interval=0.5 and flush_at=100 handle periodic flushing
        )
        # Eagerly load installation ID to avoid blocking file I/O in async context
        _get_installation_id()


def is_analytics_opted_out() -> bool:
    """
    Check if analytics is opted out via environment variable.

    This function checks the MXCP_DISABLE_ANALYTICS environment variable to determine
    if analytics tracking should be disabled. This provides users with a simple way
    to opt out of all analytics collection.

    Returns:
        bool: True if analytics is opted out, False otherwise

    Recognized Values:
        The following environment variable values are considered "opted out":
        - "1" (string one)
        - "true" (case-insensitive)
        - "yes" (case-insensitive)

    Example:
        ```python
        from mxcp.sdk.core.analytics import is_analytics_opted_out

        if not is_analytics_opted_out():
            # Analytics is enabled
            track_event("app_started")
        ```

    Environment Variables:
        MXCP_DISABLE_ANALYTICS: Set to disable analytics tracking
    """
    return os.getenv("MXCP_DISABLE_ANALYTICS", "").lower() in ("1", "true", "yes")


def track_event(event_name: str, properties: dict[str, Any] | None = None) -> None:
    """
    Track an event in PostHog if analytics is enabled.

    This function provides the core event tracking functionality. It's non-blocking
    and will silently fail if there are any issues, ensuring that analytics problems
    never affect the main application.

    Args:
        event_name (str): Name of the event to track. Should be descriptive and
            follow a consistent naming convention (e.g., "config_loaded", "command_executed")
        properties (Optional[dict]): Optional dictionary of properties to include
            with the event. These provide additional context about the event.

    Behavior:
        - Non-blocking: PostHog handles async delivery internally with background thread
        - Auto-flush every 0.5 seconds (PostHog default)
        - Auto-flush at 100 queued events (PostHog default)
        - Automatically adds default properties (app name, version)
        - Silently handles all errors to prevent analytics from affecting the main app
        - Respects the analytics opt-out setting
        - Uses anonymous tracking (no personal data)

    Default Properties:
        The following properties are automatically added to all events:
        - "app": Always set to "mxcp"
        - "version": Current package version from pyproject.toml

    Example:
        ```python
        from mxcp.sdk.core.analytics import track_event

        # Simple event tracking
        track_event("user_login")

        # Event with additional properties
        track_event("config_loaded", {
            "config_type": "yaml",
            "file_size": 1024,
            "validation_success": True
        })
        ```

    Thread Safety:
        This function is fully thread-safe and can be called from any thread.
    """
    if not is_analytics_opted_out() and posthog_client is not None:
        # Configure logging to be less verbose
        logging.getLogger("posthog").setLevel(logging.ERROR)
        logging.getLogger("urllib3").setLevel(logging.ERROR)

        try:
            # Add default properties
            event_properties = {
                "app": PACKAGE_NAME,
                "version": PACKAGE_VERSION,
                **(properties or {}),
            }

            # PostHog.capture() is non-blocking in async mode - it queues the event
            # and returns immediately. PostHog's internal thread handles delivery.
            posthog_client.capture(
                distinct_id=_get_installation_id(),
                event=event_name,
                properties=event_properties,
            )
        except Exception:
            # Silently fail - analytics should never affect the main application
            pass


def track_command(
    command_name: str,
    success: bool,
    error: str | None = None,
    duration_ms: float | None = None,
) -> None:
    """
    Track CLI command execution with success/failure and timing information.

    This specialized tracking function is designed for monitoring command-line
    operations, providing insights into command usage patterns, success rates,
    and performance characteristics.

    Args:
        command_name (str): Name of the command that was executed (e.g., "validate", "run", "init")
        success (bool): Whether the command execution was successful
        error (Optional[str]): Error message if the command failed. Only included when success=False
        duration_ms (Optional[float]): Command execution time in milliseconds. Useful for performance monitoring

    Behavior:
        - Automatically tracks the "cli_command_executed" event
        - Includes command name, success status, and optional error/timing data
        - Follows the same non-blocking, fault-tolerant pattern as track_event
        - Respects analytics opt-out settings

    Event Properties:
        The following properties are included in the tracked event:
        - "command": The command name that was executed
        - "success": Boolean indicating success/failure
        - "error": Error message (only when success=False)
        - "duration_ms": Execution time in milliseconds (when provided)

    Example:
        ```python
        from mxcp.sdk.core.analytics import track_command

        # Track successful command
        track_command("validate", success=True, duration_ms=150.2)

        # Track failed command
        track_command("run", success=False, error="Configuration file not found", duration_ms=25.8)
        ```

    Thread Safety:
        This function is fully thread-safe and can be called from any thread.
    """
    properties = {
        "command": command_name,
        "success": success,
    }
    if error:
        properties["error"] = error
    if duration_ms:
        properties["duration_ms"] = duration_ms

    track_event("cli_command_executed", properties)


def track_base_command() -> None:
    """
    Track when user runs just 'mxcp' without any command.

    This function is specifically designed to track when users run the base command
    without any subcommands, which typically displays help information. This helps
    understand user behavior and the need for better command discovery.

    Behavior:
        - Tracks a successful "base" command execution
        - Uses the standard command tracking mechanism
        - Provides insights into help/usage patterns

    Example:
        ```python
        from mxcp.sdk.core.analytics import track_base_command

        # Called when user runs 'mxcp' without arguments
        track_base_command()
        ```

    Implementation:
        This is a convenience function that calls track_command("base", True)
    """
    track_command("base", True)


def track_command_with_timing(command_name: str) -> Any:
    """
    Decorator to track command execution with automatic timing.

    This decorator provides an elegant way to add analytics tracking to command
    functions without modifying their implementation. It automatically measures
    execution time and tracks both successful and failed executions.

    Args:
        command_name (str): Name of the command to track in analytics

    Returns:
        Any: A decorator function that can be applied to command functions

    Behavior:
        - Measures execution time from start to finish
        - Tracks successful executions with timing data
        - Tracks failed executions with error information and timing
        - Preserves the original function's metadata (name, docstring, etc.)
        - Re-raises exceptions after tracking them

    Tracked Data:
        - Command name
        - Success/failure status
        - Execution duration in milliseconds
        - Error message (for failures)

    Example:
        ```python
        from mxcp.sdk.core.analytics import track_command_with_timing

        @track_command_with_timing("validate_config")
        def validate_config(config_path: str) -> bool:
            # Your command implementation here
            return True

        @track_command_with_timing("process_data")
        def process_data(data: dict) -> dict:
            # This will be automatically tracked with timing
            return processed_data
        ```

    Error Handling:
        - Exceptions are tracked with error messages and timing
        - Original exceptions are re-raised after tracking
        - Analytics failures never affect the decorated function

    Thread Safety:
        The decorator is thread-safe and can be used on functions called from any thread.
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(func)  # This preserves the function's metadata
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            start_time = time.time()
            try:
                result = func(*args, **kwargs)
                with contextlib.suppress(Exception):
                    track_command(
                        command_name=command_name,
                        success=True,
                        duration_ms=(time.time() - start_time) * 1000,
                    )
                return result
            except Exception as e:
                with contextlib.suppress(Exception):
                    track_command(
                        command_name=command_name,
                        success=False,
                        error=str(e),
                        duration_ms=(time.time() - start_time) * 1000,
                    )
                raise

        return wrapper

    return decorator


def track_endpoint_execution(
    endpoint_type: str,
    endpoint_name: str,
    success: bool,
    duration_ms: float,
    transport: str | None = None,
) -> None:
    """
    Track MCP endpoint (tool/resource/prompt) execution.

    Privacy: The endpoint name is hashed to prevent revealing proprietary tool names
    while still allowing pattern analysis (e.g., "tool X is called 100x more than tool Y").

    Args:
        endpoint_type: Type of endpoint ("tool", "resource", "prompt")
        endpoint_name: Name of the endpoint (will be hashed for privacy)
        success: Whether the execution succeeded
        duration_ms: Execution time in milliseconds
        transport: Transport mode ("stdio", "http", or None)

    Example:
        ```python
        from mxcp.sdk.core.analytics import track_endpoint_execution

        track_endpoint_execution(
            endpoint_type="tool",
            endpoint_name="my_tool",  # Will be hashed
            success=True,
            duration_ms=150.5,
            transport="http"
        )
        ```

    Privacy Note:
        The endpoint name is hashed using SHA256, with only the first 12 characters
        retained. This allows for pattern matching and usage analysis without
        revealing the actual tool names, which may be considered proprietary.
    """
    properties: dict[str, Any] = {
        "endpoint_type": endpoint_type,
        "endpoint_hash": _hash_name(endpoint_name),
        "success": success,
        "duration_ms": duration_ms,
    }
    if transport:
        properties["transport"] = transport

    track_event("mcp_endpoint_executed", properties)
