"""Type definitions for MXCP telemetry.

This module wraps OpenTelemetry types to avoid direct dependencies
in user code.
"""

from enum import Enum
from typing import Any, Protocol


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
