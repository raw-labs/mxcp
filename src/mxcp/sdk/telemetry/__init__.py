"""MXCP SDK Telemetry - OpenTelemetry wrapper for observability.

This module provides a simplified telemetry API that wraps OpenTelemetry,
allowing MXCP server and SDK users to add distributed tracing without
directly depending on OpenTelemetry APIs.

Key Features:
    - Simple context manager for tracing operations
    - Automatic error handling and status setting
    - Configurable exporters (OTLP, Console, None)
    - Correlation with audit logs via trace IDs
    - Future-ready for attribute redaction

Quick Start:
    ```python
    from mxcp.sdk.telemetry import configure_telemetry, traced_operation

    # Configure once at startup
    configure_telemetry(enabled=True, endpoint="http://localhost:4318")

    # Use throughout your code
    with traced_operation("my.operation", {"key": "value"}) as span:
        # Your code here
        if span:
            span.set_attribute("result", "success")
    ```
"""

from ._config import (
    TelemetryConfig,
    configure_telemetry,
    is_telemetry_enabled,
    shutdown_telemetry,
)
from ._tracer import (
    SpanKind,
    get_current_span_id,
    get_current_trace_id,
    record_exception,
    set_span_attribute,
    traced_operation,
)
from ._types import (
    Span,
    Status,
    StatusCode,
)

__all__ = [
    # Configuration
    "configure_telemetry",
    "shutdown_telemetry",
    "is_telemetry_enabled",
    "TelemetryConfig",
    # Tracing
    "traced_operation",
    "get_current_trace_id",
    "get_current_span_id",
    "set_span_attribute",
    "record_exception",
    # Types
    "Span",
    "Status",
    "StatusCode",
    "SpanKind",
]
