import os
import time
from typing import Optional, Any
import logging
import functools
import threading
from concurrent.futures import ThreadPoolExecutor

import posthog

POSTHOG_API_KEY = "phc_6BP2PRVBewZUihdpac9Qk6QHd4eXykdhrvoFncqBjl0"
POSTHOG_HOST = "https://app.posthog.com"
POSTHOG_TIMEOUT = 0.4 # Timeout for analytics requests - analytics is non-critical

# Create a thread pool for analytics
analytics_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="analytics")

def initialize_analytics() -> None:
    """
    Initialize PostHog analytics if not opted out.
    """
    if not is_analytics_opted_out():
        posthog.api_key = POSTHOG_API_KEY
        posthog.host = POSTHOG_HOST
        # Set default properties for all events
        posthog.default_properties = {
            "app": "mxcp-mcp",
            "version": "0.1.0",  # TODO: Get this from package version
        }
        # Configure PostHog to be less verbose and more efficient
        posthog.debug = False
        posthog.sync_mode = False  # Use async mode for better performance
        # Set a timeout for all requests
        posthog.timeout = POSTHOG_TIMEOUT

def is_analytics_opted_out() -> bool:
    """
    Check if analytics is opted out via environment variable.
    """
    return os.getenv("MXCP_DISABLE_ANALYTICS", "").lower() in ("1", "true", "yes")

def track_event(event_name: str, properties: Optional[dict] = None) -> None:
    """
    Track an event in PostHog if analytics is enabled.
    This is completely non-blocking and will silently fail if there are any issues.
    
    Args:
        event_name: Name of the event to track
        properties: Optional properties to include with the event
    """
    if not is_analytics_opted_out():
        # Configure logging to be less verbose
        logging.getLogger('posthog').setLevel(logging.ERROR)
        logging.getLogger('urllib3').setLevel(logging.ERROR)

        def _track():
            try:
                posthog.capture(
                    distinct_id="anonymous",  # We don't track individual users
                    event=event_name,
                    properties=properties or {}
                )
            except Exception:
                # Silently fail - analytics should never affect the main application
                pass

        # Submit to thread pool and don't wait for result
        analytics_executor.submit(_track)

def track_command(command_name: str, success: bool, error: Optional[str] = None, duration_ms: Optional[float] = None) -> None:
    """
    Track CLI command execution.
    
    Args:
        command_name: Name of the command executed
        success: Whether the command succeeded
        error: Error message if command failed
        duration_ms: Command execution time in milliseconds
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
    """
    track_command("base", True)

def track_command_with_timing(command_name: str) -> Any:
    """
    Decorator to track command execution with timing.
    
    Args:
        command_name: Name of the command to track
    """
    def decorator(func):
        @functools.wraps(func)  # This preserves the function's metadata
        def wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = func(*args, **kwargs)
                track_command(
                    command_name=command_name,
                    success=True,
                    duration_ms=(time.time() - start_time) * 1000
                )
                return result
            except Exception as e:
                track_command(
                    command_name=command_name,
                    success=False,
                    error=str(e),
                    duration_ms=(time.time() - start_time) * 1000
                )
                raise
        return wrapper
    return decorator 