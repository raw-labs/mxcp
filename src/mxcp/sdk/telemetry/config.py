"""Telemetry configuration for MXCP SDK.

This module handles OpenTelemetry configuration and initialization,
completely hiding the OpenTelemetry APIs from users.
"""

import logging
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

from ._types import TelemetryConfig

logger = logging.getLogger(__name__)

# Global flag for telemetry state
_telemetry_enabled = False


def configure_all(config: TelemetryConfig | None = None, **kwargs: Any) -> None:
    """Configure all telemetry signals (traces, metrics, logs).

    This is the main entry point for telemetry configuration, treating all
    signals as equal citizens.

    Args:
        config: TelemetryConfig object
        **kwargs: Alternative to config, pass individual settings

    Examples:
        # Using config object
        config = TelemetryConfig(
            enabled=True,
            endpoint="http://localhost:4318",
            tracing=TracingConfig(enabled=True),
            metrics=MetricsConfig(enabled=True, export_interval=60)
        )
        configure_all(config)

        # Using kwargs
        configure_all(enabled=True, endpoint="http://localhost:4318")
    """
    # Handle both config object and kwargs
    if config is None:
        config = TelemetryConfig.from_dict(kwargs)

    if not config.enabled:
        logger.info("Telemetry disabled globally")
        _disable_all()
        return

    logger.info(f"Configuring telemetry (endpoint={config.endpoint})")

    # Configure each signal if enabled
    if config.tracing.enabled:
        configure_tracing(config)
    else:
        logger.info("Tracing disabled")

    if config.metrics.enabled:
        _configure_metrics_from_config(config)
    else:
        logger.info("Metrics disabled")


def configure_tracing(config: TelemetryConfig) -> None:
    """Configure distributed tracing.

    This function specifically configures the tracing signal of telemetry.

    Args:
        config: Unified telemetry configuration
    """
    global _telemetry_enabled

    if not config.enabled or not config.tracing.enabled:
        logger.info("Tracing disabled")
        trace.set_tracer_provider(trace.NoOpTracerProvider())
        _telemetry_enabled = False
        return

    _telemetry_enabled = True
    logger.info(f"Configuring tracing (endpoint={config.endpoint})")

    # Build resource attributes
    resource_attrs = {
        "service.name": config.service_name,
        "service.version": config.service_version,
        "deployment.environment": config.environment,
    }

    # Add custom resource attributes
    if config.resource_attributes:
        resource_attrs.update(config.resource_attributes)

    # Create resource
    resource = Resource.create(resource_attrs)

    # Create tracer provider
    provider = TracerProvider(resource=resource)

    # Configure exporters
    if config.tracing.console_export:
        # Console exporter for debugging
        console_exporter = ConsoleSpanExporter()
        console_processor = SimpleSpanProcessor(console_exporter)
        provider.add_span_processor(console_processor)
        logger.info("Added console span exporter")

    if config.endpoint:
        # OTLP exporter
        endpoint = config.endpoint
        if not endpoint.endswith("/v1/traces"):
            endpoint = f"{endpoint}/v1/traces"

        otlp_exporter = OTLPSpanExporter(
            endpoint=endpoint,
            headers=config.headers or {},
        )
        otlp_processor = BatchSpanProcessor(otlp_exporter)
        provider.add_span_processor(otlp_processor)
        logger.info(f"Added OTLP span exporter to {endpoint}")

    # Set as global tracer provider
    trace.set_tracer_provider(provider)

    logger.info("Tracing configuration complete")


def _configure_metrics_from_config(config: TelemetryConfig) -> None:
    """Configure metrics collection from unified config.

    Args:
        config: Unified telemetry configuration
    """
    # Import here to avoid circular dependency
    from .metrics import configure_metrics

    # Build resource attributes (reuse from main config)
    resource_attrs = {
        "service.name": config.service_name,
        "service.version": config.service_version,
        "deployment.environment": config.environment,
    }
    if config.resource_attributes:
        resource_attrs.update(config.resource_attributes)

    configure_metrics(
        enabled=True,
        endpoint=config.endpoint,
        export_interval=config.metrics.export_interval,
        prometheus_port=config.metrics.prometheus_port,
        resource_attributes=resource_attrs,
    )


def _disable_all() -> None:
    """Disable all telemetry signals."""
    global _telemetry_enabled

    # Disable tracing
    _telemetry_enabled = False
    trace.set_tracer_provider(trace.NoOpTracerProvider())

    # Disable metrics
    from .metrics import configure_metrics

    configure_metrics(enabled=False)


def shutdown_telemetry() -> None:
    """Shutdown telemetry and flush any pending spans."""
    provider = trace.get_tracer_provider()
    if hasattr(provider, "shutdown"):
        provider.shutdown()
    logger.info("Telemetry shutdown complete")


def is_telemetry_enabled() -> bool:
    """Check if telemetry is currently enabled."""
    return _telemetry_enabled
