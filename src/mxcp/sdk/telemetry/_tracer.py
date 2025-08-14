"""Tracing functionality for MXCP SDK.

This module provides the core tracing API, wrapping OpenTelemetry's
tracer functionality.
"""

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from opentelemetry import trace
from opentelemetry.trace import Status as OTelStatus
from opentelemetry.trace import StatusCode as OTelStatusCode

from ._types import Span, SpanKind, Status, StatusCode

logger = logging.getLogger(__name__)

__all__ = [
    "traced_operation",
    "get_current_trace_id",
    "get_current_span_id",
    "set_span_attribute",
    "record_exception",
    "SpanKind",
]

# Convert our enums to OpenTelemetry enums
_STATUS_CODE_MAP = {
    StatusCode.UNSET: OTelStatusCode.UNSET,
    StatusCode.OK: OTelStatusCode.OK,
    StatusCode.ERROR: OTelStatusCode.ERROR,
}

_SPAN_KIND_MAP = {
    SpanKind.INTERNAL: trace.SpanKind.INTERNAL,
    SpanKind.SERVER: trace.SpanKind.SERVER,
    SpanKind.CLIENT: trace.SpanKind.CLIENT,
    SpanKind.PRODUCER: trace.SpanKind.PRODUCER,
    SpanKind.CONSUMER: trace.SpanKind.CONSUMER,
}


class NoOpSpan:
    """No-op span for when telemetry is disabled."""

    def set_attribute(self, key: str, value: Any) -> None:
        """No-op."""
        pass

    def set_status(self, status: Status) -> None:
        """No-op."""
        pass

    def record_exception(self, exception: Exception) -> None:
        """No-op."""
        pass

    def is_recording(self) -> bool:
        """Always False for no-op span."""
        return False


class SpanWrapper:
    """Wraps OpenTelemetry span to implement our Span protocol."""

    def __init__(self, otel_span: Any) -> None:
        self._span = otel_span

    def set_attribute(self, key: str, value: Any) -> None:
        """Set an attribute on the span."""
        if self._span and self._span.is_recording():
            # Filter to valid OpenTelemetry attribute types
            if value is None:
                return  # Skip None values
            elif isinstance(value, str | int | float | bool):
                self._span.set_attribute(key, value)
            elif isinstance(value, list | tuple):
                # OpenTelemetry supports homogeneous lists
                if all(isinstance(v, str | int | float | bool) for v in value):
                    self._span.set_attribute(key, list(value))
                else:
                    self._span.set_attribute(key, str(value))
            else:
                # Convert other types to string
                self._span.set_attribute(key, str(value))

    def set_status(self, status: Status) -> None:
        """Set the span status."""
        if self._span and self._span.is_recording():
            otel_code = _STATUS_CODE_MAP.get(status.status_code, OTelStatusCode.UNSET)
            self._span.set_status(OTelStatus(otel_code, status.description))

    def record_exception(self, exception: Exception) -> None:
        """Record an exception on the span."""
        if self._span and self._span.is_recording():
            self._span.record_exception(exception)

    def is_recording(self) -> bool:
        """Check if span is recording."""
        if self._span is None:
            return False
        # Check if the wrapped span has is_recording method
        if hasattr(self._span, 'is_recording'):
            return bool(self._span.is_recording())
        # If no is_recording method, check if it's a valid span context
        return hasattr(self._span, 'get_span_context')


# Global tracer instance
_tracer: trace.Tracer | None = None


def _get_tracer() -> trace.Tracer:
    """Get or create the MXCP tracer."""
    global _tracer
    if _tracer is None:
        _tracer = trace.get_tracer("mxcp", "1.0.0")
    return _tracer


@contextmanager
def traced_operation(
    name: str,
    attributes: dict[str, Any] | None = None,
    kind: SpanKind = SpanKind.INTERNAL,
) -> Iterator[Span]:
    """Context manager for tracing operations.

    This is the main API for adding telemetry to MXCP code.

    Args:
        name: Operation name (e.g., "mxcp.endpoint.execute")
        attributes: Initial span attributes
        kind: Type of span (INTERNAL, SERVER, CLIENT, etc.)

    Yields:
        Span object or None if telemetry is disabled

    Example:
        ```python
        with traced_operation("my.operation", {"user": "alice"}) as span:
            # Do work
            if span:
                span.set_attribute("result.count", 42)
        ```
    """
    tracer = _get_tracer()

    # Check if telemetry is configured by trying to get a tracer
    # If we have a NoOpTracerProvider, tracer operations will be no-ops
    from ._config import is_telemetry_enabled
    if not is_telemetry_enabled():
        yield NoOpSpan()
        return

    # Convert our SpanKind to OpenTelemetry SpanKind
    otel_kind = _SPAN_KIND_MAP.get(kind, trace.SpanKind.INTERNAL)

    # Start span
    with tracer.start_as_current_span(name, kind=otel_kind) as otel_span:
        # Wrap in our interface
        span = SpanWrapper(otel_span)

        # Set initial attributes
        if attributes:
            for key, value in attributes.items():
                span.set_attribute(key, value)

        try:
            yield span
        except Exception as e:
            # Automatically record exceptions
            span.record_exception(e)
            span.set_status(Status(StatusCode.ERROR, str(e)))
            raise


def get_current_trace_id() -> str | None:
    """Get the current trace ID for correlation with audit logs.

    Returns:
        Trace ID as hex string or None if not in a trace
    """
    span = trace.get_current_span()
    if span.is_recording():
        span_context = span.get_span_context()
        return format(span_context.trace_id, '032x')
    return None


def get_current_span_id() -> str | None:
    """Get the current span ID.

    Returns:
        Span ID as hex string or None if not in a span
    """
    span = trace.get_current_span()
    if span.is_recording():
        span_context = span.get_span_context()
        return format(span_context.span_id, '016x')
    return None


def set_span_attribute(key: str, value: Any) -> None:
    """Set an attribute on the current span.

    This is useful when you don't have direct access to the span object.

    Args:
        key: Attribute name
        value: Attribute value
    """
    span = trace.get_current_span()
    if span.is_recording():
        wrapped = SpanWrapper(span)
        wrapped.set_attribute(key, value)


def record_exception(exception: Exception) -> None:
    """Record an exception on the current span.

    Args:
        exception: The exception to record
    """
    span = trace.get_current_span()
    if span.is_recording():
        span.record_exception(exception)
        span.set_status(OTelStatus(OTelStatusCode.ERROR, str(exception)))
