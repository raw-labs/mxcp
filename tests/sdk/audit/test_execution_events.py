"""Tests for execution event helper APIs."""

import asyncio
from datetime import datetime, timezone

import pytest

from mxcp.sdk.audit import add_execution_event, begin_execution_event, get_execution_events
from mxcp.sdk.audit.context import (
    reset_execution_events,
    set_execution_events,
)
from mxcp.sdk.audit.models import ExecutionEventModel


@pytest.mark.asyncio
async def test_add_execution_event_appends_to_active_collector():
    token = set_execution_events()
    try:
        start = begin_execution_event()
        event = add_execution_event(
            span=start,
            status="success",
            target="api.example.com",
            operation="GET /customers/{id}",
            summary="Fetch customer",
            details={"kind": "http", "status_code": 200},
        )

        assert isinstance(event, ExecutionEventModel)
        assert event.started_at.tzinfo == timezone.utc
        assert event.duration_ms >= 0
        assert event.target == "api.example.com"

        events = get_execution_events()
        assert events == [event]
    finally:
        reset_execution_events(token)


@pytest.mark.asyncio
async def test_execution_event_collectors_are_isolated_per_task():
    async def collect_event(target: str) -> list[ExecutionEventModel] | None:
        token = set_execution_events()
        try:
            start = begin_execution_event()
            await asyncio.sleep(0)
            add_execution_event(
                span=start,
                status="success",
                target=target,
                operation="call",
                details={"kind": "test"},
            )
            return get_execution_events()
        finally:
            reset_execution_events(token)

    first, second = await asyncio.gather(
        collect_event("service-a"),
        collect_event("service-b"),
    )

    assert first is not None
    assert second is not None
    assert [event.target for event in first] == ["service-a"]
    assert [event.target for event in second] == ["service-b"]


def test_begin_execution_event_returns_wall_clock_timestamp():
    start = begin_execution_event()

    assert isinstance(start.started_at, datetime)
    assert start.started_at.tzinfo == timezone.utc
    assert isinstance(start.monotonic_start, float)
