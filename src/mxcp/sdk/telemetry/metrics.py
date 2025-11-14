"""
Metrics support for MXCP using OpenTelemetry.

This module provides a simplified API for metrics collection that wraps
OpenTelemetry's metrics API.
"""

import logging
from collections.abc import Callable
from typing import Any

from opentelemetry import metrics
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.metrics import Counter, Histogram, UpDownCounter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource

from mxcp.sdk.core import PACKAGE_NAME, PACKAGE_VERSION

from .config import _telemetry_enabled

logger = logging.getLogger(__name__)

# Global metrics state
_metrics_manager: "MetricsManager | None" = None


class MetricsManager:
    """Manages OpenTelemetry metrics for MXCP."""

    def __init__(self, meter: metrics.Meter) -> None:
        """Initialize metrics manager.

        Args:
            meter: OpenTelemetry meter instance
        """
        self._meter = meter
        self._metrics: dict[str, Any] = {}

    def get_counter(self, name: str, description: str = "", unit: str = "") -> Counter:
        """Get or create a counter metric.

        Args:
            name: Metric name (e.g., "mxcp.endpoint.requests")
            description: Human-readable description
            unit: Unit of measurement (e.g., "1", "bytes")

        Returns:
            Counter instance
        """
        if name not in self._metrics:
            self._metrics[name] = self._meter.create_counter(
                name, description=description, unit=unit
            )
        return self._metrics[name]  # type: ignore[no-any-return]

    def get_histogram(self, name: str, description: str = "", unit: str = "") -> Histogram:
        """Get or create a histogram metric.

        Args:
            name: Metric name (e.g., "mxcp.endpoint.duration")
            description: Human-readable description
            unit: Unit of measurement (e.g., "s", "ms")

        Returns:
            Histogram instance
        """
        if name not in self._metrics:
            self._metrics[name] = self._meter.create_histogram(
                name, description=description, unit=unit
            )
        return self._metrics[name]  # type: ignore[no-any-return]

    def get_gauge(self, name: str, description: str = "", unit: str = "") -> UpDownCounter:
        """Get or create a gauge metric.

        Note: OpenTelemetry uses UpDownCounter for gauge-like metrics.

        Args:
            name: Metric name (e.g., "mxcp.connections.active")
            description: Human-readable description
            unit: Unit of measurement

        Returns:
            UpDownCounter instance (acts as gauge)
        """
        if name not in self._metrics:
            self._metrics[name] = self._meter.create_up_down_counter(
                name, description=description, unit=unit
            )
        return self._metrics[name]  # type: ignore[no-any-return]


def configure_metrics(
    *,
    enabled: bool = True,
    endpoint: str | None = None,
    export_interval: int = 60,
    resource_attributes: dict[str, Any] | None = None,
) -> None:
    """Configure metrics collection.

    Args:
        enabled: Whether metrics are enabled
        endpoint: OTLP endpoint for metrics export
        export_interval: Export interval in seconds
        resource_attributes: Additional resource attributes
    """
    global _metrics_manager

    if not enabled:
        logger.info("Metrics collection disabled")
        _metrics_manager = None
        return

    # Build resource
    resource_attrs = {
        "service.name": PACKAGE_NAME,
        "service.version": PACKAGE_VERSION,
    }
    if resource_attributes:
        resource_attrs.update(resource_attributes)

    resource = Resource.create(resource_attrs)

    # Create readers based on configuration
    from opentelemetry.sdk.metrics.export import MetricReader

    readers: list[MetricReader] = []

    # OTLP exporter if endpoint provided
    if endpoint:
        exporter = OTLPMetricExporter(
            endpoint=endpoint if endpoint.endswith("/v1/metrics") else f"{endpoint}/v1/metrics",
            headers={},
        )
        readers.append(
            PeriodicExportingMetricReader(
                exporter=exporter,
                export_interval_millis=export_interval * 1000,
            )
        )
        logger.info(f"Configured OTLP metrics export to {endpoint}")
    else:
        logger.warning("No OTLP endpoint configured for metrics")
        return

    if not readers:
        logger.warning("No metrics exporters configured")
        return

    # Create meter provider
    provider = MeterProvider(resource=resource, metric_readers=readers)
    metrics.set_meter_provider(provider)

    # Create metrics manager
    meter = metrics.get_meter(PACKAGE_NAME, PACKAGE_VERSION)
    _metrics_manager = MetricsManager(meter)

    logger.info("Metrics collection configured successfully")


def get_metrics_manager() -> MetricsManager | None:
    """Get the global metrics manager.

    Returns:
        MetricsManager instance or None if metrics are disabled
    """
    return _metrics_manager


def record_counter(
    name: str,
    value: int = 1,
    attributes: dict[str, Any] | None = None,
    description: str = "",
    unit: str = "1",
) -> None:
    """Record a counter metric.

    Args:
        name: Metric name
        value: Value to add (default: 1)
        attributes: Metric attributes/labels
        description: Metric description
        unit: Unit of measurement
    """
    if not _metrics_manager or not _telemetry_enabled:
        return

    try:
        counter = _metrics_manager.get_counter(name, description, unit)
        counter.add(value, attributes=attributes or {})
    except Exception as e:
        logger.debug(f"Failed to record counter {name}: {e}")


def record_histogram(
    name: str,
    value: float,
    attributes: dict[str, Any] | None = None,
    description: str = "",
    unit: str = "s",
) -> None:
    """Record a histogram metric.

    Args:
        name: Metric name
        value: Value to record
        attributes: Metric attributes/labels
        description: Metric description
        unit: Unit of measurement
    """
    if not _metrics_manager or not _telemetry_enabled:
        return

    try:
        histogram = _metrics_manager.get_histogram(name, description, unit)
        histogram.record(value, attributes=attributes or {})
    except Exception as e:
        logger.debug(f"Failed to record histogram {name}: {e}")


def record_gauge(
    name: str,
    value: int,
    attributes: dict[str, Any] | None = None,
    description: str = "",
    unit: str = "1",
) -> None:
    """Record a gauge metric (using UpDownCounter).

    Args:
        name: Metric name
        value: Current value (positive or negative)
        attributes: Metric attributes/labels
        description: Metric description
        unit: Unit of measurement
    """
    if not _metrics_manager or not _telemetry_enabled:
        return

    try:
        gauge = _metrics_manager.get_gauge(name, description, unit)
        gauge.add(value, attributes=attributes or {})
    except Exception as e:
        logger.debug(f"Failed to record gauge {name}: {e}")


def time_histogram(
    name: str,
    attributes: dict[str, Any] | None = None,
    description: str = "",
    unit: str = "s",
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorator to time a function and record as histogram.

    Args:
        name: Metric name
        attributes: Metric attributes/labels
        description: Metric description
        unit: Unit of measurement

    Returns:
        Decorator function
    """
    import time
    from functools import wraps

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            start = time.time()
            try:
                return func(*args, **kwargs)
            finally:
                duration = time.time() - start
                record_histogram(name, duration, attributes, description, unit)

        return wrapper

    return decorator


def increment_gauge(
    name: str,
    attributes: dict[str, Any] | None = None,
    description: str = "",
    unit: str = "1",
) -> None:
    """Increment a gauge metric by 1.

    Args:
        name: Metric name
        attributes: Metric attributes/labels
        description: Metric description
        unit: Unit of measurement
    """
    record_gauge(name, 1, attributes, description, unit)


def decrement_gauge(
    name: str,
    attributes: dict[str, Any] | None = None,
    description: str = "",
    unit: str = "1",
) -> None:
    """Decrement a gauge metric by 1.

    Args:
        name: Metric name
        attributes: Metric attributes/labels
        description: Metric description
        unit: Unit of measurement
    """
    record_gauge(name, -1, attributes, description, unit)
