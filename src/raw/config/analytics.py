import os
import time
from typing import Optional, Any
import logging
import functools

import posthog

# Configure logging to be less verbose
logging.getLogger('posthog').setLevel(logging.WARNING)
logging.getLogger('urllib3').setLevel(logging.WARNING)

POSTHOG_API_KEY = "phc_6BP2PRVBewZUihdpac9Qk6QHd4eXykdhrvoFncqBjl0"
POSTHOG_HOST = "https://app.posthog.com"

def initialize_analytics() -> None:
    """
    Initialize PostHog analytics if not opted out.
    """
    if not is_analytics_opted_out():
        posthog.api_key = POSTHOG_API_KEY
        posthog.host = POSTHOG_HOST
        # Set default properties for all events
        posthog.default_properties = {
            "app": "raw-mcp",
            "version": "0.1.0",  # TODO: Get this from package version
        }
        # Configure PostHog to be less verbose and more efficient
        posthog.debug = False
        posthog.sync_mode = False  # Use async mode for better performance

def is_analytics_opted_out() -> bool:
    """
    Check if analytics is opted out via environment variable.
    """
    return os.getenv("RAW_DISABLE_ANALYTICS", "").lower() in ("1", "true", "yes")

def track_event(event_name: str, properties: Optional[dict] = None) -> None:
    """
    Track an event in PostHog if analytics is enabled.
    
    Args:
        event_name: Name of the event to track
        properties: Optional properties to include with the event
    """
    if not is_analytics_opted_out():
        try:
            posthog.capture(
                distinct_id="anonymous",  # We don't track individual users
                event=event_name,
                properties=properties or {}
            )
        except Exception:
            # Silently fail - analytics should never affect the main application
            pass

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