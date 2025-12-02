"""Pydantic models for MXCP telemetry configuration.

This module contains Pydantic model definitions for telemetry configuration,
including tracing and metrics settings.
"""

from enum import Enum
from typing import Any, Protocol

from pydantic import ConfigDict, Field

from mxcp.sdk.core import PACKAGE_NAME, PACKAGE_VERSION
from mxcp.sdk.models import SdkBaseModel


class StatusCode(Enum):
    """Span status codes.

    Used to indicate the outcome of a traced operation:
    - UNSET: Status not explicitly set
    - OK: Operation completed successfully
    - ERROR: Operation failed with an error
    """

    UNSET = 0
    OK = 1
    ERROR = 2


class Status:
    """Span status.

    Combines a status code with an optional description for
    providing context about the operation outcome.

    Attributes:
        status_code: The status code indicating success, error, or unset
        description: Optional human-readable description of the status
    """

    def __init__(self, status_code: StatusCode, description: str | None = None):
        self.status_code = status_code
        self.description = description


class SpanKind(Enum):
    """Type of span.

    Describes the relationship of a span to other spans:
    - INTERNAL: Default, internal operation
    - SERVER: Server-side handling of a request
    - CLIENT: Client-side request to another service
    - PRODUCER: Message producer
    - CONSUMER: Message consumer
    """

    INTERNAL = 0
    SERVER = 1
    CLIENT = 2
    PRODUCER = 3
    CONSUMER = 4


class Span(Protocol):
    """Protocol for span objects.

    This protocol allows implementations to be swapped without changing
    user code. It defines the minimal interface required for span operations.
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


class TracingConfigModel(SdkBaseModel):
    """Configuration for distributed tracing.

    Controls how traces are collected and exported for observability.

    Attributes:
        enabled: Whether tracing is enabled
        console_export: Whether to print spans to console (for debugging)

    Example:
        >>> config = TracingConfigModel(enabled=True, console_export=True)
    """

    # Override frozen to allow mutability during configuration
    model_config = ConfigDict(extra="forbid", frozen=False)

    enabled: bool = True
    console_export: bool = False


class MetricsConfigModel(SdkBaseModel):
    """Configuration for metrics collection.

    Controls how metrics are collected and exported.

    Attributes:
        enabled: Whether metrics collection is enabled
        export_interval: How often to export metrics in seconds

    Example:
        >>> config = MetricsConfigModel(enabled=True, export_interval=30)
    """

    # Override frozen to allow mutability during configuration
    model_config = ConfigDict(extra="forbid", frozen=False)

    enabled: bool = True
    export_interval: int = Field(default=60, ge=1)


class TelemetryConfigModel(SdkBaseModel):
    """Unified configuration for all telemetry signals.

    This configuration treats traces and metrics as equal citizens
    in the observability stack. It provides global settings that apply
    to all signals as well as signal-specific configurations.

    Attributes:
        enabled: Global enable/disable for all telemetry
        endpoint: OTLP endpoint URL (e.g., http://localhost:4318)
        headers: Additional headers for OTLP requests
        service_name: Name of the service for identification
        service_version: Version of the service
        environment: Deployment environment (e.g., 'production', 'development')
        resource_attributes: Additional resource attributes
        tracing: Tracing-specific configuration
        metrics: Metrics-specific configuration

    Example:
        >>> config = TelemetryConfigModel(
        ...     enabled=True,
        ...     endpoint="http://localhost:4318",
        ...     service_name="my-service",
        ...     environment="production",
        ...     tracing=TracingConfigModel(enabled=True),
        ...     metrics=MetricsConfigModel(enabled=True, export_interval=30)
        ... )
    """

    # Override frozen to allow mutability during configuration
    model_config = ConfigDict(extra="forbid", frozen=False)

    # Global settings (apply to all signals)
    enabled: bool = False
    endpoint: str | None = None
    headers: dict[str, str] | None = None

    # Service identification
    service_name: str = PACKAGE_NAME
    service_version: str = PACKAGE_VERSION
    environment: str = "development"

    # Additional resource attributes
    resource_attributes: dict[str, Any] | None = None

    # Signal-specific configurations
    tracing: TracingConfigModel = Field(default_factory=TracingConfigModel)
    metrics: MetricsConfigModel = Field(default_factory=MetricsConfigModel)
