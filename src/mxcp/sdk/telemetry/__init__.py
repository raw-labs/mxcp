"""MXCP SDK Telemetry - OpenTelemetry wrapper for observability.

This module provides a simplified telemetry API that wraps OpenTelemetry,
allowing MXCP server and SDK users to add distributed tracing and metrics
without directly depending on OpenTelemetry APIs.

Key Features:
    - Simple context manager for tracing operations
    - Metrics collection (counters, histograms, gauges)
    - Automatic error handling and status setting
    - Configurable exporters (OTLP, Console, Prometheus)
    - Correlation with audit logs via trace IDs
    - Privacy-first design with no sensitive data

Quick Start:
    ```python
    from mxcp.sdk.telemetry import (
        configure_telemetry, configure_metrics,
        traced_operation, record_counter, record_histogram
    )

    # Configure once at startup
    configure_telemetry(enabled=True, endpoint="http://localhost:4318")
    configure_metrics(enabled=True, endpoint="http://localhost:4318")

    # Use throughout your code
    with traced_operation("my.operation", {"key": "value"}) as span:
        # Your code here
        if span:
            span.set_attribute("result", "success")

    # Record metrics
    record_counter("mxcp.requests", attributes={"endpoint": "my_tool"})
    record_histogram("mxcp.duration", 0.123, attributes={"endpoint": "my_tool"})
    ```
"""

from .models import (
    MetricsConfigModel,
    Span,
    SpanKind,
    Status,
    StatusCode,
    TelemetryConfigModel,
    TracingConfigModel,
)
from .config import (
    configure_all,
    configure_tracing,
    is_telemetry_enabled,
    shutdown_telemetry,
)
from .metrics import (
    configure_metrics,
    decrement_gauge,
    get_metrics_manager,
    increment_gauge,
    record_counter,
    record_gauge,
    record_histogram,
    time_histogram,
)
from .tracer import (
    get_current_span,
    get_current_span_id,
    get_current_trace_id,
    record_exception,
    set_span_attribute,
    traced_operation,
)

__all__ = [
    # Configuration - New unified approach
    "configure_all",  # Main entry point
    "configure_tracing",  # Configure traces specifically
    "configure_metrics",  # Configure metrics specifically
    "shutdown_telemetry",
    "is_telemetry_enabled",
    # Configuration types
    "TelemetryConfigModel",  # Unified config
    "TracingConfigModel",  # Tracing-specific config
    "MetricsConfigModel",  # Metrics-specific config
    # Tracing
    "traced_operation",
    "get_current_trace_id",
    "get_current_span_id",
    "get_current_span",
    "set_span_attribute",
    "record_exception",
    # Metrics
    "get_metrics_manager",
    "record_counter",
    "record_histogram",
    "record_gauge",
    "increment_gauge",
    "decrement_gauge",
    "time_histogram",
    # Types
    "Span",
    "Status",
    "StatusCode",
    "SpanKind",
]
