"""Server-side telemetry configuration and initialization.

This module configures OpenTelemetry based on user config settings,
using the SDK telemetry module for the actual implementation.
"""

import logging
import os
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
            f" (interval={config.metrics.export_interval}s)"
        )

    # Configure all telemetry signals
    configure_all(config)

    # Return whether telemetry is actually enabled
    return config.enabled


def _parse_resource_attributes(value: str) -> dict[str, str]:
    """Parse OTEL_RESOURCE_ATTRIBUTES format.

    Format: key1=value1,key2=value2

    Args:
        value: Comma-separated key=value pairs

    Returns:
        Dictionary of attributes
    """
    attrs = {}
    for pair in value.split(","):
        if "=" in pair:
            key, val = pair.split("=", 1)
            attrs[key.strip()] = val.strip()
    return attrs


def _parse_headers(value: str) -> dict[str, str]:
    """Parse OTEL_EXPORTER_OTLP_HEADERS format.

    Format: key1=value1,key2=value2

    Args:
        value: Comma-separated key=value pairs

    Returns:
        Dictionary of headers
    """
    headers = {}
    for pair in value.split(","):
        if "=" in pair:
            key, val = pair.split("=", 1)
            headers[key.strip()] = val.strip()
    return headers


def _get_telemetry_from_env() -> dict[str, Any] | None:
    """Get telemetry configuration from environment variables.

    Reads standard OpenTelemetry environment variables and MXCP-specific ones.

    Standard OTEL variables:
        - OTEL_EXPORTER_OTLP_ENDPOINT
        - OTEL_EXPORTER_OTLP_HEADERS
        - OTEL_SERVICE_NAME
        - OTEL_RESOURCE_ATTRIBUTES

    MXCP-specific variables:
        - MXCP_TELEMETRY_ENABLED
        - MXCP_TELEMETRY_TRACING_CONSOLE
        - MXCP_TELEMETRY_METRICS_INTERVAL

    Returns:
        Telemetry config dict or None if no env vars are set
    """
    config: dict[str, Any] = {}

    # Check if telemetry is explicitly enabled
    enabled = os.getenv("MXCP_TELEMETRY_ENABLED", "").lower()
    if enabled in ("true", "1", "yes"):
        config["enabled"] = True
    elif enabled in ("false", "0", "no"):
        config["enabled"] = False

    # Standard OTEL variables
    if endpoint := os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT"):
        config["endpoint"] = endpoint

    if headers_str := os.getenv("OTEL_EXPORTER_OTLP_HEADERS"):
        config["headers"] = _parse_headers(headers_str)

    if service_name := os.getenv("OTEL_SERVICE_NAME"):
        config["service_name"] = service_name

    if resource_attrs_str := os.getenv("OTEL_RESOURCE_ATTRIBUTES"):
        config["resource_attributes"] = _parse_resource_attributes(resource_attrs_str)

    # MXCP-specific tracing config
    tracing_config: dict[str, Any] = {}
    console_export = os.getenv("MXCP_TELEMETRY_TRACING_CONSOLE", "").lower()
    if console_export in ("true", "1", "yes"):
        tracing_config["console_export"] = True
    elif console_export in ("false", "0", "no"):
        tracing_config["console_export"] = False

    if tracing_config:
        config["tracing"] = tracing_config

    # MXCP-specific metrics config
    metrics_config: dict[str, Any] = {}
    if interval_str := os.getenv("MXCP_TELEMETRY_METRICS_INTERVAL"):
        try:
            metrics_config["export_interval"] = int(interval_str)
        except ValueError:
            logger.warning(
                f"Invalid MXCP_TELEMETRY_METRICS_INTERVAL value: {interval_str}, ignoring"
            )

    if metrics_config:
        config["metrics"] = metrics_config

    # Return None if no configuration was found
    return config if config else None


def _merge_telemetry_configs(
    file_config: UserTelemetryConfig | None, env_config: dict[str, Any] | None
) -> dict[str, Any] | None:
    """Merge telemetry configuration from file and environment.

    Environment variables take precedence over file configuration.

    Args:
        file_config: Configuration from user config file
        env_config: Configuration from environment variables

    Returns:
        Merged configuration or None if both are empty
    """
    if not file_config and not env_config:
        return None

    # Start with file config or empty dict
    merged: dict[str, Any] = dict(file_config) if file_config else {}

    # Apply env overrides
    if env_config:
        for key, value in env_config.items():
            if key in ("tracing", "metrics"):
                # Merge nested configs
                if key not in merged:
                    merged[key] = {}
                merged[key].update(value)
            else:
                # Override top-level keys
                merged[key] = value

    return merged


def _get_telemetry_config(
    user_config: UserConfig, project: str, profile: str
) -> dict[str, Any] | None:
    """Get telemetry configuration for a specific profile.

    Merges configuration from user config file and environment variables,
    with environment variables taking precedence.

    Args:
        user_config: The loaded user configuration
        project: The current project name
        profile: The current profile name

    Returns:
        Telemetry configuration dict or None if not found
    """
    # Get config from file
    try:
        file_config = user_config["projects"][project]["profiles"][profile].get("telemetry")
    except KeyError:
        file_config = None

    # Get config from environment
    env_config = _get_telemetry_from_env()

    # Merge with env taking precedence
    return _merge_telemetry_configs(file_config, env_config)


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
