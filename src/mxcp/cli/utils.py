import json
import logging
import os
import shutil
import traceback
from typing import Any, Dict, Optional

import click


def get_env_flag(env_var: str, default: bool = False) -> bool:
    """Get a boolean flag from an environment variable.

    Args:
        env_var: Name of the environment variable
        default: Default value if environment variable is not set

    Returns:
        True if the environment variable is set to "1", "true", or "yes" (case insensitive)
        False otherwise
    """
    value = os.environ.get(env_var, "").lower()
    return value in ("1", "true", "yes") if value else default


def get_env_profile() -> Optional[str]:
    """Get the profile name from environment variable.

    Returns:
        Profile name from MXCP_PROFILE environment variable, or None if not set
    """
    return os.environ.get("MXCP_PROFILE")


def check_command_available(command: str) -> bool:
    """Check if a command is available in the system PATH.

    Args:
        command: The command name to check

    Returns:
        True if command is available, False otherwise
    """
    return shutil.which(command) is not None


def configure_logging(debug: bool = False) -> None:
    """Configure logging for all modules.

    Args:
        debug: Whether to enable debug logging
    """
    # Check environment variable if debug flag is not set
    if not debug:
        debug = get_env_flag("MXCP_DEBUG")

    log_level = logging.DEBUG if debug else logging.WARNING

    # Configure root logger first
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # Remove any existing handlers to avoid duplicate messages
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Add a basic handler with the desired level
    handler = logging.StreamHandler()
    handler.setLevel(log_level)
    formatter = logging.Formatter("%(levelname)s:%(name)s:%(message)s")
    handler.setFormatter(formatter)
    root_logger.addHandler(handler)

    # Set level for all loggers
    for logger_name in logging.root.manager.loggerDict:
        logger = logging.getLogger(logger_name)
        logger.setLevel(log_level)
        # Ensure loggers propagate to root logger
        logger.propagate = True


def format_error(error: Exception, debug: bool = False) -> Dict[str, Any]:
    """Format an error for output.

    Args:
        error: The exception that occurred
        debug: Whether to include debug information

    Returns:
        Dict containing error information
    """
    error_info = {"error": str(error)}

    if debug:
        error_info["traceback"] = traceback.format_exc()
        error_info["type"] = error.__class__.__name__

    return error_info


def output_result(result: Any, json_output: bool = False, debug: bool = False) -> None:
    """Output a result in either JSON or human-readable format.

    Args:
        result: The result to output
        json_output: Whether to output in JSON format
        debug: Whether to include debug information
    """
    if json_output:
        print(json.dumps({"status": "ok", "result": result}, indent=2, default=str))
    else:
        if isinstance(result, list):
            for row in result:
                click.echo(row)
        else:
            click.echo(result)


def output_error(error: Exception, json_output: bool = False, debug: bool = False) -> None:
    """Output an error in either JSON or human-readable format.

    Args:
        error: The exception that occurred
        json_output: Whether to output in JSON format
        debug: Whether to include debug information
    """
    error_info = format_error(error, debug)

    if json_output:
        print(json.dumps({"status": "error", **error_info}, indent=2))
    else:
        click.echo(f"Error: {error_info['error']}", err=True)
        if debug and "traceback" in error_info:
            click.echo("\nTraceback:", err=True)
            click.echo(error_info["traceback"], err=True)

    raise click.Abort()
