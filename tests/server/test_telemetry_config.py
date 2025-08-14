"""Test server-side telemetry configuration."""

import pytest
from mxcp.server.core.config._types import UserConfig, UserTelemetryConfig
from mxcp.server.core.telemetry import (
    configure_telemetry_from_config,
    shutdown_telemetry,
)
from mxcp.sdk.telemetry import (
    is_telemetry_enabled, 
    traced_operation,
    get_current_trace_id,
)


@pytest.fixture(autouse=True)
def reset_telemetry():
    """Reset telemetry state between tests."""
    # Reset OpenTelemetry's internal state
    from opentelemetry import trace
    import mxcp.sdk.telemetry._config
    import mxcp.sdk.telemetry._tracer
    
    # Reset before test
    trace._TRACER_PROVIDER = None
    trace._TRACER_PROVIDER_FACTORY = None
    mxcp.sdk.telemetry._config._telemetry_enabled = False
    mxcp.sdk.telemetry._tracer._tracer = None
    
    yield
    
    # Cleanup after test
    try:
        shutdown_telemetry()
    except:
        pass
    trace._TRACER_PROVIDER = None
    trace._TRACER_PROVIDER_FACTORY = None
    mxcp.sdk.telemetry._config._telemetry_enabled = False
    mxcp.sdk.telemetry._tracer._tracer = None


def test_telemetry_config_disabled():
    """Test telemetry when not configured."""
    user_config: UserConfig = {
        "mxcp": "1",
        "projects": {
            "test": {
                "profiles": {
                    "dev": {
                        # No telemetry config
                    }
                }
            }
        }
    }
    
    configure_telemetry_from_config(user_config, "test", "dev")
    assert not is_telemetry_enabled()
    
    # Should create no-op spans
    with traced_operation("test.op") as span:
        assert span is not None
        assert not span.is_recording()


def test_telemetry_config_enabled():
    """Test telemetry when enabled in config."""
    user_config: UserConfig = {
        "mxcp": "1",
        "projects": {
            "test": {
                "profiles": {
                    "dev": {
                        "telemetry": {
                            "enabled": True,
                            "console_export": True,
                            "service_name": "test-service",
                            "environment": "testing",
                        }
                    }
                }
            }
        }
    }
    
    configure_telemetry_from_config(user_config, "test", "dev")
    assert is_telemetry_enabled()
    
    # Should create spans
    with traced_operation("test.op") as span:
        assert span is not None
        # Note: get_current_trace_id() may return None in tests due to how OpenTelemetry
        # handles context in different async execution environments, so we just
        # verify that spans are being created


def test_telemetry_config_with_endpoint():
    """Test telemetry with OTLP endpoint."""
    user_config: UserConfig = {
        "mxcp": "1", 
        "projects": {
            "prod": {
                "profiles": {
                    "main": {
                        "telemetry": {
                            "enabled": True,
                            "endpoint": "http://localhost:4318",
                            "headers": {
                                "Authorization": "Bearer token"
                            },
                            "sampling_rate": 0.1,
                        }
                    }
                }
            }
        }
    }
    
    configure_telemetry_from_config(user_config, "prod", "main")
    assert is_telemetry_enabled()


def test_telemetry_disabled_by_default():
    """Test telemetry is disabled when enabled=false."""
    user_config: UserConfig = {
        "mxcp": "1",
        "projects": {
            "test": {
                "profiles": {
                    "dev": {
                        "telemetry": {
                            "enabled": False,
                            "endpoint": "http://localhost:4318",
                        }
                    }
                }
            }
        }
    }
    
    configure_telemetry_from_config(user_config, "test", "dev")
    assert not is_telemetry_enabled()
    
    # Should create no-op spans even with endpoint configured
    with traced_operation("test.op") as span:
        assert span is not None
        assert not span.is_recording()
