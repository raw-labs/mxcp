"""Server-side telemetry configuration and initialization.

This module configures OpenTelemetry based on user config settings,
using the SDK telemetry module for the actual implementation.
"""

import logging
from typing import Any

from mxcp.sdk.core import PACKAGE_NAME, PACKAGE_VERSION
from mxcp.sdk.telemetry import (
    TelemetryConfig,
    configure_all,
    get_current_trace_id,
    shutdown_telemetry,
)
from mxcp.server.core.config._types import UserConfig, UserTelemetryConfig

logger = logging.getLogger(__name__)


def configure_telemetry_from_config(
    user_config: UserConfig,
    project: str,
    profile: str,
) -> bool:
    """Configure telemetry based on user config settings.

    This reads telemetry configuration from the user config at the profile level
    and initializes OpenTelemetry accordingly.

    Args:
        user_config: The loaded user configuration
        project: The current project name
        profile: The current profile name

    Returns:
        Whether telemetry is enabled
    """
    # Get telemetry config for the current profile
    telemetry_config = _get_telemetry_config(user_config, project, profile)

    if not telemetry_config:
        logger.debug(f"No telemetry configuration found for {project}/{profile}")
        # Disable all telemetry
        configure_all(enabled=False)
        return False

    # Create unified SDK telemetry config from user config
    # Build a proper dict from the TypedDict
    config_dict: dict[str, Any] = {
        "enabled": telemetry_config.get("enabled", False),
        "endpoint": telemetry_config.get("endpoint"),
        "headers": telemetry_config.get("headers"),
        "service_name": telemetry_config.get("service_name", PACKAGE_NAME),
        "service_version": telemetry_config.get("service_version", PACKAGE_VERSION),
        "environment": telemetry_config.get("environment", profile),
        "resource_attributes": {
            "mxcp.project": project,
            "mxcp.profile": profile,
        },
    }

    # Add any additional resource attributes from config
    if telemetry_config.get("resource_attributes"):
        config_dict["resource_attributes"].update(telemetry_config["resource_attributes"])

    # Handle signal-specific configs
    if "tracing" in telemetry_config:
        config_dict["tracing"] = telemetry_config["tracing"]
    if "metrics" in telemetry_config:
        config_dict["metrics"] = telemetry_config["metrics"]

    # Create config object
    config = TelemetryConfig.from_dict(config_dict)

    # Log configuration details
    logger.info(
        f"Configuring telemetry for {project}/{profile} "
        f"(enabled={config.enabled}, endpoint={config.endpoint})"
    )

    if config.enabled:
        logger.info(
            f"  Tracing: {'enabled' if config.tracing.enabled else 'disabled'}"
            f"{' (console export)' if config.tracing.console_export else ''}"
        )
        logger.info(
            f"  Metrics: {'enabled' if config.metrics.enabled else 'disabled'}"
            f" (interval={config.metrics.export_interval}s"
            + (
                f", prometheus_port={config.metrics.prometheus_port}"
                if config.metrics.prometheus_port
                else ""
            )
            + ")"
        )

    # Configure all telemetry signals
    configure_all(config)

    # Return whether telemetry is actually enabled
    return config.enabled


def _get_telemetry_config(
    user_config: UserConfig, project: str, profile: str
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
