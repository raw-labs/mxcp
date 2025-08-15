"""Telemetry configuration for MXCP SDK.

This module handles OpenTelemetry configuration and initialization,
completely hiding the OpenTelemetry APIs from users.
"""

import logging
from dataclasses import dataclass
from typing import Any

# Import OpenTelemetry only in this module
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    ConsoleSpanExporter,
    SimpleSpanProcessor,
)

from mxcp.sdk.core import PACKAGE_NAME, PACKAGE_VERSION

logger = logging.getLogger(__name__)

# Global flag for telemetry state
_telemetry_enabled = False


@dataclass
class TelemetryConfig:
    """Configuration for telemetry."""

    enabled: bool = False
    endpoint: str | None = None
    service_name: str = PACKAGE_NAME
    service_version: str = PACKAGE_VERSION
    environment: str = "development"
    headers: dict[str, str] | None = None
    resource_attributes: dict[str, Any] | None = None
    console_export: bool = False  # For debugging

    @classmethod
    def from_dict(cls, config: dict[str, Any]) -> "TelemetryConfig":
        """Create config from dictionary (e.g., from mxcp-site.yml)."""
        return cls(
            enabled=config.get("enabled", False),
            endpoint=config.get("endpoint"),
            service_name=config.get("service_name", PACKAGE_NAME),
            service_version=config.get("service_version", PACKAGE_VERSION),
            environment=config.get("environment", "development"),
            headers=config.get("headers"),
            resource_attributes=config.get("resource_attributes"),
            console_export=config.get("console_export", False),
        )


def configure_telemetry(config: TelemetryConfig | None = None, **kwargs: Any) -> None:
    """Configure telemetry for MXCP.

    This completely wraps OpenTelemetry configuration so users don't need
    to interact with OpenTelemetry directly.

    Args:
        config: TelemetryConfig object
        **kwargs: Alternative to config, pass individual settings

    Examples:
        # Using config object
        configure_telemetry(TelemetryConfig(enabled=True, endpoint="..."))

        # Using kwargs
        configure_telemetry(enabled=True, endpoint="http://localhost:4318")
    """
    global _telemetry_enabled

    # Handle both config object and kwargs
    if config is None:
        config = TelemetryConfig(**kwargs)

    if not config.enabled:
        # Install no-op tracer
        logger.info("Telemetry disabled, installing no-op tracer")
        trace.set_tracer_provider(trace.NoOpTracerProvider())
        _telemetry_enabled = False
        return

    logger.info(f"Configuring telemetry with endpoint: {config.endpoint}")

    # Build resource attributes
    resource_attrs = {
        "service.name": config.service_name,
        "service.version": config.service_version,
        "deployment.environment": config.environment,
    }

    # Add any custom resource attributes
    if config.resource_attributes:
        resource_attrs.update(config.resource_attributes)

    # Create resource
    resource = Resource.create(resource_attrs)

    # Create tracer provider
    provider = TracerProvider(resource=resource)

    # Configure exporter
    exporter: ConsoleSpanExporter | OTLPSpanExporter
    processor: SimpleSpanProcessor | BatchSpanProcessor

    if config.console_export:
        # Console exporter for debugging
        exporter = ConsoleSpanExporter()
        processor = SimpleSpanProcessor(exporter)
    elif config.endpoint:
        # OTLP exporter for production
        exporter = OTLPSpanExporter(
            endpoint=f"{config.endpoint}/v1/traces", headers=config.headers or {}
        )
        processor = BatchSpanProcessor(exporter)
    else:
        # No exporter configured
        logger.warning("Telemetry enabled but no endpoint configured")
        _telemetry_enabled = False
        return

    # Add processor to provider
    provider.add_span_processor(processor)

    # Set as global tracer provider
    trace.set_tracer_provider(provider)
    _telemetry_enabled = True

    logger.info(f"Telemetry configured successfully with {type(provider).__name__}")


def shutdown_telemetry() -> None:
    """Shutdown telemetry and flush any pending spans."""
    provider = trace.get_tracer_provider()
    if hasattr(provider, "shutdown"):
        provider.shutdown()
    logger.info("Telemetry shutdown complete")


def is_telemetry_enabled() -> bool:
    """Check if telemetry is currently enabled."""
    return _telemetry_enabled
