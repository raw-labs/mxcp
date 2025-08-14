"""Server-side telemetry configuration and initialization.

This module configures OpenTelemetry based on user config settings,
using the SDK telemetry module for the actual implementation.
"""

import logging

from mxcp.sdk.telemetry import (
    TelemetryConfig,
    get_current_trace_id,
    shutdown_telemetry,
)
from mxcp.sdk.telemetry import (
    configure_telemetry as sdk_configure_telemetry,
)
from mxcp.server.core.config._types import UserConfig, UserTelemetryConfig

logger = logging.getLogger(__name__)


def configure_telemetry_from_config(
    user_config: UserConfig,
    project: str,
    profile: str,
) -> None:
    """Configure telemetry based on user config settings.

    This reads telemetry configuration from the user config at the profile level
    and initializes OpenTelemetry accordingly.

    Args:
        user_config: The loaded user configuration
        project: The current project name
        profile: The current profile name
    """
    # Get telemetry config for the current profile
    telemetry_config = _get_telemetry_config(user_config, project, profile)

    if not telemetry_config:
        logger.debug(f"No telemetry configuration found for {project}/{profile}")
        # Install no-op telemetry
        sdk_configure_telemetry(enabled=False)
        return

    # Create SDK telemetry config from user config
    config = TelemetryConfig(
        enabled=telemetry_config.get("enabled", False),
        endpoint=telemetry_config.get("endpoint"),
        service_name=telemetry_config.get("service_name") or "mxcp",
        service_version="0.4.0",  # TODO: Get from package
        environment=telemetry_config.get("environment") or profile,
        headers=telemetry_config.get("headers"),
        console_export=telemetry_config.get("console_export") or False,
    )

    # Add resource attributes for better identification
    config.resource_attributes = {
        "mxcp.project": project,
        "mxcp.profile": profile,
    }

    # Initialize telemetry
    logger.info(
        f"Configuring telemetry for {project}/{profile} "
        f"(enabled={config.enabled}, endpoint={config.endpoint})"
    )
    sdk_configure_telemetry(config)


def _get_telemetry_config(
    user_config: UserConfig,
    project: str,
    profile: str
) -> UserTelemetryConfig | None:
    """Extract telemetry config for a specific project/profile.

    Args:
        user_config: The loaded user configuration
        project: The project name
        profile: The profile name

    Returns:
        The telemetry configuration or None if not found
    """
    try:
        return user_config["projects"][project]["profiles"][profile].get("telemetry")
    except KeyError:
        return None


def get_trace_context() -> str | None:
    """Get current trace context for correlation with audit logs.

    This is a convenience wrapper around the SDK function.

    Returns:
        Trace ID as hex string or None
    """
    return get_current_trace_id()


# Re-export shutdown for clean server shutdown
__all__ = [
    "configure_telemetry_from_config",
    "get_trace_context",
    "shutdown_telemetry",
]
