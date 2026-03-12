"""Request-local execution event collection helpers."""

import contextvars
import logging
import time
from datetime import datetime, timezone
from typing import Any

from .models import ExecutionEventKind, ExecutionEventModel, ExecutionEventSpan, Status

logger = logging.getLogger(__name__)

_execution_events_var = contextvars.ContextVar[list[ExecutionEventModel] | None](
    "execution_events",
    default=None,
)


def set_execution_events() -> contextvars.Token[list[ExecutionEventModel] | None]:
    """Start a fresh request-local execution event list."""
    return _execution_events_var.set([])


def reset_execution_events(
    token: contextvars.Token[list[ExecutionEventModel] | None],
) -> None:
    """Reset the request-local execution event list to the previous state."""
    _execution_events_var.reset(token)


def begin_execution_event() -> ExecutionEventSpan:
    """Capture the start time for a later execution event append."""
    return ExecutionEventSpan(
        started_at=datetime.now(timezone.utc),
        monotonic_start=time.perf_counter(),
    )


def add_execution_event(
    *,
    span: ExecutionEventSpan,
    kind: ExecutionEventKind = "external",
    status: Status = "success",
    target: str | None = None,
    operation: str | None = None,
    summary: str | None = None,
    error: str | None = None,
    details: dict[str, Any] | None = None,
) -> ExecutionEventModel:
    """Finalize and append an execution event to the current request context."""
    duration_ms = max(0, int((time.perf_counter() - span.monotonic_start) * 1000))
    event = ExecutionEventModel(
        kind=kind,
        started_at=span.started_at,
        duration_ms=duration_ms,
        status=status,
        target=target,
        operation=operation,
        summary=summary,
        error=error,
        details=details or {},
    )

    current_events = _execution_events_var.get()
    if current_events is None:
        logger.debug("Ignoring execution event because no collector is active")
        return event

    current_events.append(event)
    return event


def get_execution_events() -> list[ExecutionEventModel] | None:
    """Return a copy of the current request-local execution events, or None if no collector is active."""
    current_events = _execution_events_var.get()
    if current_events is None:
        return None
    return list(current_events)
