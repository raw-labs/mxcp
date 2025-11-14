"""Tests for telemetry configuration via environment variables."""

import os
from unittest import mock

import pytest

from mxcp.server.core.telemetry import (
    _get_telemetry_from_env,
    _merge_telemetry_configs,
    _parse_headers,
    _parse_resource_attributes,
)


def test_parse_resource_attributes():
    """Test parsing OTEL_RESOURCE_ATTRIBUTES format."""
    result = _parse_resource_attributes("environment=production,team=platform,region=us-east")
    assert result == {
        "environment": "production",
        "team": "platform",
        "region": "us-east",
    }

    # Test empty string
    result = _parse_resource_attributes("")
    assert result == {}

    # Test with spaces
    result = _parse_resource_attributes("key1=value1, key2=value2")
    assert result == {"key1": "value1", "key2": "value2"}


def test_parse_headers():
    """Test parsing OTEL_EXPORTER_OTLP_HEADERS format."""
    result = _parse_headers("Authorization=Bearer token,X-Custom=value")
    assert result == {
        "Authorization": "Bearer token",
        "X-Custom": "value",
    }

    # Test empty string
    result = _parse_headers("")
    assert result == {}


@mock.patch.dict(os.environ, {}, clear=True)
def test_get_telemetry_from_env_empty():
    """Test that empty environment returns None."""
    result = _get_telemetry_from_env()
    assert result is None


@mock.patch.dict(
    os.environ,
    {
        "MXCP_TELEMETRY_ENABLED": "true",
        "OTEL_EXPORTER_OTLP_ENDPOINT": "http://otel-collector:4318",
        "OTEL_SERVICE_NAME": "mxcp-prod",
    },
    clear=True,
)
def test_get_telemetry_from_env_basic():
    """Test basic telemetry configuration from environment."""
    result = _get_telemetry_from_env()
    assert result is not None
    assert result["enabled"] is True
    assert result["endpoint"] == "http://otel-collector:4318"
    assert result["service_name"] == "mxcp-prod"


@mock.patch.dict(
    os.environ,
    {
        "MXCP_TELEMETRY_ENABLED": "true",
        "OTEL_EXPORTER_OTLP_ENDPOINT": "http://localhost:4318",
        "OTEL_EXPORTER_OTLP_HEADERS": "Authorization=Bearer token,X-Custom=value",
        "OTEL_SERVICE_NAME": "mxcp-test",
        "OTEL_RESOURCE_ATTRIBUTES": "environment=production,team=platform",
        "MXCP_TELEMETRY_TRACING_CONSOLE": "true",
        "MXCP_TELEMETRY_METRICS_INTERVAL": "30",
    },
    clear=True,
)
def test_get_telemetry_from_env_full():
    """Test full telemetry configuration from environment."""
    result = _get_telemetry_from_env()
    assert result is not None
    assert result["enabled"] is True
    assert result["endpoint"] == "http://localhost:4318"
    assert result["headers"] == {"Authorization": "Bearer token", "X-Custom": "value"}
    assert result["service_name"] == "mxcp-test"
    assert result["resource_attributes"] == {
        "environment": "production",
        "team": "platform",
    }
    assert result["tracing"]["console_export"] is True
    assert result["metrics"]["export_interval"] == 30


@mock.patch.dict(
    os.environ,
    {"MXCP_TELEMETRY_ENABLED": "false"},
    clear=True,
)
def test_get_telemetry_from_env_disabled():
    """Test disabled telemetry via environment."""
    result = _get_telemetry_from_env()
    assert result is not None
    assert result["enabled"] is False


@mock.patch.dict(
    os.environ,
    {"MXCP_TELEMETRY_METRICS_INTERVAL": "invalid"},
    clear=True,
)
def test_get_telemetry_from_env_invalid_interval():
    """Test handling of invalid metrics interval."""
    result = _get_telemetry_from_env()
    # Should not crash, just skip the invalid value
    assert result is None or "metrics" not in result


def test_merge_telemetry_configs_both_none():
    """Test merging when both configs are None."""
    result = _merge_telemetry_configs(None, None)
    assert result is None


def test_merge_telemetry_configs_only_file():
    """Test merging with only file config."""
    file_config = {
        "enabled": True,
        "endpoint": "http://localhost:4318",
        "service_name": "mxcp-file",
    }
    result = _merge_telemetry_configs(file_config, None)
    assert result == file_config


def test_merge_telemetry_configs_only_env():
    """Test merging with only env config."""
    env_config = {
        "enabled": True,
        "endpoint": "http://localhost:4318",
        "service_name": "mxcp-env",
    }
    result = _merge_telemetry_configs(None, env_config)
    assert result == env_config


def test_merge_telemetry_configs_env_overrides():
    """Test that environment variables override file config."""
    file_config = {
        "enabled": False,
        "endpoint": "http://file-endpoint:4318",
        "service_name": "mxcp-file",
        "tracing": {"enabled": True, "console_export": False},
    }
    env_config = {
        "enabled": True,
        "endpoint": "http://env-endpoint:4318",
        "tracing": {"console_export": True},
    }
    result = _merge_telemetry_configs(file_config, env_config)

    # Env should override top-level keys
    assert result["enabled"] is True
    assert result["endpoint"] == "http://env-endpoint:4318"

    # File config value should remain if not overridden
    assert result["service_name"] == "mxcp-file"

    # Nested configs should merge
    assert result["tracing"]["enabled"] is True  # from file
    assert result["tracing"]["console_export"] is True  # from env


def test_merge_telemetry_configs_nested_merge():
    """Test merging of nested tracing and metrics configs."""
    file_config = {
        "enabled": True,
        "tracing": {"enabled": True, "console_export": False},
        "metrics": {"enabled": True, "export_interval": 60},
    }
    env_config = {
        "tracing": {"console_export": True},
        "metrics": {"export_interval": 30},
    }
    result = _merge_telemetry_configs(file_config, env_config)

    # Top level should remain
    assert result["enabled"] is True

    # Nested configs should merge
    assert result["tracing"]["enabled"] is True  # from file
    assert result["tracing"]["console_export"] is True  # from env (overrides)
    assert result["metrics"]["enabled"] is True  # from file
    assert result["metrics"]["export_interval"] == 30  # from env (overrides)
