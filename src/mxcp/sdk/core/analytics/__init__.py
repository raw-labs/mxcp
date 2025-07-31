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

import os
import time
from typing import Optional, Any
import logging
import functools
import threading
from concurrent.futures import ThreadPoolExecutor

from posthog import Posthog

try:
    from importlib.metadata import version
    PACKAGE_VERSION = version("mxcp")
except ImportError:
    # Fallback for Python < 3.8
    try:
        import pkg_resources  # type: ignore
        PACKAGE_VERSION = pkg_resources.get_distribution("mxcp").version
    except Exception:
        PACKAGE_VERSION = "unknown"

POSTHOG_API_KEY = "phc_6BP2PRVBewZUihdpac9Qk6QHd4eXykdhrvoFncqBjl0"
POSTHOG_HOST = "https://eu.i.posthog.com"  # Fixed: EU region
POSTHOG_TIMEOUT = 1 # Timeout for analytics requests - analytics is non-critical

# Create a thread pool for analytics
analytics_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="analytics")

# Global PostHog instance
posthog_client = None

def initialize_analytics() -> None:
    """
    Initialize PostHog analytics if not opted out.
    
    This function must be called once at application startup to enable analytics tracking.
    It creates a global PostHog client instance that will be used for all subsequent
    analytics operations.
    
    The initialization is safe to call multiple times - subsequent calls will be ignored
    if analytics is already initialized.
    
    Behavior:
        - If analytics is opted out via environment variable, no client is created
        - Uses asynchronous mode for better performance
        - Configures appropriate timeouts for non-critical operations
        - Sets up proper error handling and logging levels
    
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
    if not is_analytics_opted_out():
        posthog_client = Posthog(
            project_api_key=POSTHOG_API_KEY,
            host=POSTHOG_HOST,
            debug=False,
            sync_mode=False,  # Use async mode for better performance
            timeout=POSTHOG_TIMEOUT
        )

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

def track_event(event_name: str, properties: Optional[dict] = None) -> None:
    """
    Track an event in PostHog if analytics is enabled.
    
    This function provides the core event tracking functionality. It's completely
    non-blocking and will silently fail if there are any issues, ensuring that
    analytics problems never affect the main application.
    
    Args:
        event_name (str): Name of the event to track. Should be descriptive and
            follow a consistent naming convention (e.g., "config_loaded", "command_executed")
        properties (Optional[dict]): Optional dictionary of properties to include
            with the event. These provide additional context about the event.
    
    Behavior:
        - Runs asynchronously in a dedicated thread pool
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
        logging.getLogger('posthog').setLevel(logging.ERROR)
        logging.getLogger('urllib3').setLevel(logging.ERROR)

        def _track():
            try:
                # Add default properties
                event_properties = {
                    "app": "mxcp",
                    "version": PACKAGE_VERSION,  # Dynamic version from pyproject.toml
                    **(properties or {})
                }
                
                if posthog_client is not None:
                    posthog_client.capture(
                        distinct_id="anonymous",  # We don't track individual users
                        event=event_name,
                        properties=event_properties
                    )
            except Exception:
                # Silently fail - analytics should never affect the main application
                pass

        # Submit to thread pool and don't wait for result
        try:
            analytics_executor.submit(_track)
        except Exception:
            # Silently handle thread pool errors
            pass

def track_command(command_name: str, success: bool, error: Optional[str] = None, duration_ms: Optional[float] = None) -> None:
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
    def decorator(func):
        @functools.wraps(func)  # This preserves the function's metadata
        def wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = func(*args, **kwargs)
                try:
                    track_command(
                        command_name=command_name,
                        success=True,
                        duration_ms=(time.time() - start_time) * 1000
                    )
                except Exception:
                    # Silently handle analytics errors
                    pass
                return result
            except Exception as e:
                try:
                    track_command(
                        command_name=command_name,
                        success=False,
                        error=str(e),
                        duration_ms=(time.time() - start_time) * 1000
                    )
                except Exception:
                    # Silently handle analytics errors
                    pass
                raise
        return wrapper
    return decorator 