"""Type definitions for MXCP telemetry.

This module wraps OpenTelemetry types to avoid direct dependencies
in user code.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol

from mxcp.sdk.core import PACKAGE_NAME, PACKAGE_VERSION


class StatusCode(Enum):
    """Span status codes."""

    UNSET = 0
    OK = 1
    ERROR = 2


class Status:
    """Span status."""

    def __init__(self, status_code: StatusCode, description: str | None = None):
        self.status_code = status_code
        self.description = description


class SpanKind(Enum):
    """Type of span."""

    INTERNAL = 0
    SERVER = 1
    CLIENT = 2
    PRODUCER = 3
    CONSUMER = 4


class Span(Protocol):
    """Protocol for span objects.

    This allows us to swap implementations without changing user code.
    """

    def set_attribute(self, key: str, value: Any) -> None:
        """Set an attribute on the span."""
        ...

    def set_status(self, status: Status) -> None:
        """Set the span status."""
        ...

    def record_exception(self, exception: Exception) -> None:
        """Record an exception on the span."""
        ...

    def is_recording(self) -> bool:
        """Check if span is recording."""
        ...


# Configuration types


@dataclass
class TracingConfig:
    """Configuration for distributed tracing."""

    enabled: bool = True
    console_export: bool = False  # For debugging - print spans to console

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "enabled": self.enabled,
            "console_export": self.console_export,
        }


@dataclass
class MetricsConfig:
    """Configuration for metrics collection."""

    enabled: bool = True
    export_interval: int = 60  # How often to export metrics (seconds)
    prometheus_port: int | None = None  # Optional Prometheus scraping endpoint

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "enabled": self.enabled,
            "export_interval": self.export_interval,
            "prometheus_port": self.prometheus_port,
        }


@dataclass
class TelemetryConfig:
    """Unified configuration for all telemetry signals.

    This configuration treats traces and metrics as equal citizens
    in the observability stack.
    """

    # Global settings (apply to all signals)
    enabled: bool = False
    endpoint: str | None = None  # OTLP endpoint (e.g., http://localhost:4318)
    headers: dict[str, str] | None = None  # Additional headers for OTLP

    # Service identification
    service_name: str = PACKAGE_NAME
    service_version: str = PACKAGE_VERSION
    environment: str = "development"

    # Additional resource attributes
    resource_attributes: dict[str, Any] | None = None

    # Signal-specific configurations
    tracing: TracingConfig = field(default_factory=TracingConfig)
    metrics: MetricsConfig = field(default_factory=MetricsConfig)

    @classmethod
    def from_dict(cls, config: dict[str, Any]) -> "TelemetryConfig":
        """Create config from dictionary (e.g., from user config)."""
        # Extract nested configs if present
        tracing_config = config.get("tracing", {})
        metrics_config = config.get("metrics", {})

        return cls(
            enabled=config.get("enabled", False),
            endpoint=config.get("endpoint"),
            headers=config.get("headers"),
            service_name=config.get("service_name", PACKAGE_NAME),
            service_version=config.get("service_version", PACKAGE_VERSION),
            environment=config.get("environment", "development"),
            resource_attributes=config.get("resource_attributes"),
            tracing=TracingConfig(**tracing_config) if tracing_config else TracingConfig(),
            metrics=MetricsConfig(**metrics_config) if metrics_config else MetricsConfig(),
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "enabled": self.enabled,
            "endpoint": self.endpoint,
            "headers": self.headers,
            "service_name": self.service_name,
            "service_version": self.service_version,
            "environment": self.environment,
            "resource_attributes": self.resource_attributes,
            "tracing": self.tracing.to_dict(),
            "metrics": self.metrics.to_dict(),
        }
