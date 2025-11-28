import asyncio
import json
import logging
import logging.handlers
import os
import shutil
import sys
import traceback
from collections.abc import Coroutine
from pathlib import Path
from typing import Any, TypeVar

import click

from mxcp.server.core.config.models import SiteConfigModel, UserConfigModel


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


def get_env_profile() -> str | None:
    """Get the profile name from environment variable.

    Returns:
        Profile name from MXCP_PROFILE environment variable, or None if not set
    """
    return os.environ.get("MXCP_PROFILE")


def resolve_profile(cli_profile: str | None, site_config: SiteConfigModel) -> str:
    """Resolve the active profile with clear priority.

    Priority order:
    1. CLI argument (--profile) - highest priority, explicit override
    2. Environment variable (MXCP_PROFILE) - medium priority, session-level
    3. Site config (mxcp-site.yml) - lowest priority, project default

    Args:
        cli_profile: Profile from CLI argument (--profile flag)
        site_config: The loaded site configuration

    Returns:
        The resolved profile name (never None)
    """
    if cli_profile:
        return cli_profile

    env_profile = get_env_profile()
    if env_profile:
        return env_profile

    return site_config.profile


def get_env_admin_socket_enabled() -> bool:
    """Get whether the admin socket should be enabled from environment variable.

    Returns:
        True if MXCP_ADMIN_ENABLED is set to "1", "true", or "yes" (case insensitive)
        False otherwise (default: disabled)
    """
    return get_env_flag("MXCP_ADMIN_ENABLED", default=False)


def get_env_admin_socket_path() -> str:
    """Get the admin socket path from environment variable.

    Returns:
        Path from MXCP_ADMIN_SOCKET environment variable, or default path
    """
    return os.environ.get("MXCP_ADMIN_SOCKET", "/run/mxcp/mxcp.sock")


def check_command_available(command: str) -> bool:
    """Check if a command is available in the system PATH.

    Args:
        command: The command name to check

    Returns:
        True if command is available, False otherwise
    """
    return shutil.which(command) is not None


def configure_logging(
    debug: bool = False,
    transport: str | None = None,
    log_file: Path | None = None,
    log_level: str | None = None,
    max_bytes: int = 10 * 1024 * 1024,
    backup_count: int = 5,
) -> None:
    """Configure logging for all modules.

    Args:
        debug: Whether to enable debug logging (overrides log_level if True)
        transport: Transport mode ("stdio", "streamable-http", "sse") - disables stderr for stdio
        log_file: Optional path to log file for persistent logging
        log_level: Log level string ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")
        max_bytes: Maximum log file size in bytes before rotation (default: 10MB)
        backup_count: Number of rotated log files to keep (default: 5)
    """
    # Check environment variable if debug flag is not set
    if not debug:
        debug = get_env_flag("MXCP_DEBUG")

    # Determine log level
    if debug:
        level = logging.DEBUG
    elif log_level:
        level = getattr(logging, log_level.upper(), logging.WARNING)
    else:
        level = logging.WARNING

    # Configure root logger first
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Remove any existing handlers to avoid duplicate messages
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Formatter with timestamps for file logs
    detailed_formatter = logging.Formatter(
        "%(asctime)s - %(levelname)s - %(name)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Simple formatter for stderr (no timestamps, Docker adds them)
    simple_formatter = logging.Formatter("%(levelname)s:%(name)s:%(message)s")

    # Add file handler if log_file is provided
    if log_file:
        try:
            # Ensure log directory exists
            log_file.parent.mkdir(parents=True, exist_ok=True)

            file_handler = logging.handlers.RotatingFileHandler(
                log_file,
                maxBytes=max_bytes,
                backupCount=backup_count,
            )
            file_handler.setLevel(level)
            file_handler.setFormatter(detailed_formatter)
            root_logger.addHandler(file_handler)
        except Exception as e:
            # If file logging fails, warn but continue
            print(f"Warning: Failed to setup file logging to {log_file}: {e}", file=sys.stderr)

    # Add stderr handler ONLY if not stdio mode
    # (stdio mode uses stdout/stdin for MCP protocol, stderr would corrupt messages)
    if transport != "stdio":
        stream_handler = logging.StreamHandler()
        stream_handler.setLevel(level)
        stream_handler.setFormatter(simple_formatter)
        root_logger.addHandler(stream_handler)

    # Set level for all existing loggers
    for logger_name in logging.root.manager.loggerDict:
        logger = logging.getLogger(logger_name)
        logger.setLevel(level)
        # Ensure loggers propagate to root logger
        logger.propagate = True


def format_error(error: Exception, debug: bool = False) -> dict[str, Any]:
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


T = TypeVar("T")


def run_async_cli(coro: Coroutine[Any, Any, T]) -> T:
    """Execute an async CLI implementation from a synchronous entrypoint.

    Args:
        coro: The coroutine to run.

    Returns:
        The result of the coroutine.
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    if loop.is_running():
        raise RuntimeError("Cannot run CLI coroutine while an event loop is already running.")

    future = asyncio.ensure_future(coro, loop=loop)
    return loop.run_until_complete(future)


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


def configure_logging_from_config(
    user_config: UserConfigModel,
    debug: bool = False,
    transport: str | None = None,
) -> None:
    """Configure logging using user config settings.

    This is the canonical way to setup logging for all CLI commands.
    Centralizes logging configuration logic and ensures consistent behavior.

    Logging is configured at the top level of user config (not per profile).

    Args:
        user_config: The loaded user configuration
        debug: Whether to enable debug logging (overrides config level)
        transport: Transport mode ("stdio", "streamable-http", "sse")
                   If "stdio", stderr logging is disabled to avoid protocol corruption
    """
    # Get top-level logging config
    logging_config = user_config.logging

    # If logging config is not set or disabled, use basic logging
    if not logging_config.enabled:
        # Logging disabled - only configure basic stderr (unless stdio)
        configure_logging(debug=debug, transport=transport)
        return

    # Get logging settings
    log_path_str = logging_config.path
    log_file = Path(log_path_str) if log_path_str else None
    log_level = logging_config.level
    max_bytes = logging_config.max_bytes
    backup_count = logging_config.backup_count

    # Configure logging with all settings
    configure_logging(
        debug=debug,
        transport=transport,
        log_file=log_file,
        log_level=log_level,
        max_bytes=max_bytes,
        backup_count=backup_count,
    )
