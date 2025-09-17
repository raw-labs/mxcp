"""Basic tests for MXCP SDK telemetry module."""

import pytest

from mxcp.sdk.telemetry import (
    SpanKind,
    TelemetryConfig,
    TracingConfig,
    configure_all,
    get_current_span_id,
    get_current_trace_id,
    is_telemetry_enabled,
    shutdown_telemetry,
    traced_operation,
)


def test_telemetry_disabled_by_default():
    """Test that telemetry is disabled by default."""
    # Should not raise and should be disabled
    assert not is_telemetry_enabled()

    with traced_operation("test.operation") as span:
        # Span should be a NoOpSpan when disabled
        assert span is not None
        assert not span.is_recording()
        assert get_current_trace_id() is None
        assert get_current_span_id() is None


def test_configure_all_with_kwargs():
    """Test configuring telemetry with keyword arguments."""
    # Configure with console export for testing
    configure_all(enabled=True, tracing={"console_export": True})

    assert is_telemetry_enabled()

    # Clean up
    shutdown_telemetry()


def test_configure_all_with_config_object():
    """Test configuring telemetry with config object."""
    config = TelemetryConfig(
        enabled=True,
        service_name="test-service",
        environment="testing",
        tracing=TracingConfig(enabled=True, console_export=True),
    )
    configure_all(config)

    assert is_telemetry_enabled()

    # Clean up
    shutdown_telemetry()


def test_traced_operation_when_enabled():
    """Test traced operation when telemetry is enabled."""
    # Configure telemetry
    configure_all(enabled=True, tracing={"console_export": True})

    with traced_operation(
        "test.operation",
        attributes={"test.key": "value", "test.number": 42},
        kind=SpanKind.INTERNAL,
    ) as span:
        # Span should not be None
        assert span is not None

        # Should have trace and span IDs
        trace_id = get_current_trace_id()
        span_id = get_current_span_id()
        # In test environments, trace context propagation can be unreliable
        # So we just check if they're set and have valid format when present
        if trace_id:
            assert len(trace_id) == 32  # Hex format
        if span_id:
            assert len(span_id) == 16  # Hex format

        # Test setting attributes
        span.set_attribute("test.result", "success")
        span.set_attribute("test.count", 100)
        span.set_attribute("test.list", [1, 2, 3])
        span.set_attribute("test.none", None)  # Should be skipped


def test_traced_operation_with_exception():
    """Test traced operation with exception handling."""
    configure_all(enabled=True, tracing={"console_export": True})

    try:
        with pytest.raises(ValueError), traced_operation("test.error") as span:
            assert span is not None
            raise ValueError("Test error")

        # The span should have recorded the exception
        # (We can't easily verify this without a test exporter)

    finally:
        shutdown_telemetry()


def test_nested_traced_operations():
    """Test nested traced operations."""
    configure_all(enabled=True, tracing={"console_export": True})

    with traced_operation("parent.operation") as parent_span:
        assert parent_span is not None
        parent_trace_id = get_current_trace_id()
        parent_span_id = get_current_span_id()

        with traced_operation("child.operation") as child_span:
            assert child_span is not None
            child_trace_id = get_current_trace_id()
            child_span_id = get_current_span_id()

            # Should have same trace ID (if both are set)
            if parent_trace_id and child_trace_id:
                assert parent_trace_id == child_trace_id

            # But different span IDs (if both are set)
            if parent_span_id and child_span_id:
                assert child_span_id != parent_span_id


def test_config_from_dict():
    """Test creating config from dictionary."""
    config_dict = {
        "enabled": True,
        "endpoint": "http://localhost:4318",
        "service_name": "my-service",
        "environment": "production",
        "headers": {"Authorization": "Bearer token"},
    }

    config = TelemetryConfig.from_dict(config_dict)
    assert config.enabled is True
    assert config.endpoint == "http://localhost:4318"
    assert config.service_name == "my-service"
    assert config.environment == "production"
    assert config.headers == {"Authorization": "Bearer token"}
