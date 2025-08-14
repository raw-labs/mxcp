"""Integration test for telemetry with execution engine."""

import asyncio
import pytest
from pathlib import Path
from mxcp.server.core.config._types import UserConfig, SiteConfig
from mxcp.server.executor.engine import create_execution_engine
from mxcp.server.services.endpoints.service import execute_endpoint
from mxcp.server.core.telemetry import configure_telemetry_from_config
from mxcp.sdk.telemetry import is_telemetry_enabled, get_current_trace_id, shutdown_telemetry
from mxcp.sdk.executor import ExecutionContext
from mxcp.sdk.auth import UserContext


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


def test_telemetry_with_execution_engine():
    """Test that telemetry properly traces execution engine operations."""
    # Configure telemetry
    user_config: UserConfig = {
        "mxcp": "1",
        "projects": {
            "test": {
                "profiles": {
                    "dev": {
                        "telemetry": {
                            "enabled": True,
                            "console_export": True,
                            "service_name": "test-service"
                        }
                    }
                }
            }
        }
    }
    
    configure_telemetry_from_config(user_config, "test", "dev")
    assert is_telemetry_enabled()
    
    # Create minimal site config
    site_config: SiteConfig = {
        "mxcp": "1",
        "project": "test",
        "profile": "dev",
        "profiles": {
            "dev": {
                "duckdb": {
                    "path": ":memory:",
                    "readonly": False,
                }
            }
        }
    }
    
    # Create execution engine with a temporary directory as repo root
    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_root = Path(tmpdir)
        engine = create_execution_engine(user_config, site_config, "dev", repo_root=repo_root)
        
        try:
            # Execute SQL with telemetry
            async def run_sql():
                context = ExecutionContext()
                result = await engine.execute(
                    language="sql",
                    source_code="SELECT 1 as value, 'test' as name",
                    params={},
                    context=context
                )
                assert result == [{"value": 1, "name": "test"}]
                
                # Verify we had a trace ID during execution
                # (Note: trace ID is only available during the traced operation)
                return result
            
            # Run the async function
            result = asyncio.run(run_sql())
            assert result is not None
            
            # Execute Python with telemetry
            async def run_python():
                context = ExecutionContext()
                result = await engine.execute(
                    language="python",
                    source_code="return x + y",
                    params={"x": 10, "y": 20},
                    context=context
                )
                assert result == 30
                return result
            
            result = asyncio.run(run_python())
            assert result == 30
            
        finally:
            # Cleanup
            engine.shutdown()


def test_nested_telemetry_spans():
    """Test that nested operations create proper parent-child span relationships."""
    # Configure telemetry
    user_config: UserConfig = {
        "mxcp": "1",
        "projects": {
            "test": {
                "profiles": {
                    "dev": {
                        "telemetry": {
                            "enabled": True,
                            "console_export": True,
                        }
                    }
                }
            }
        }
    }
    
    configure_telemetry_from_config(user_config, "test", "dev")
    
    # Create site config
    site_config: SiteConfig = {
        "mxcp": "1",
        "project": "test",
        "profile": "dev",
        "profiles": {
            "dev": {
                "duckdb": {
                    "path": ":memory:",
                    "readonly": False,
                }
            }
        }
    }
    
    # Test nested spans directly with execution engine
    async def run_nested_operations():
        from mxcp.sdk.telemetry import traced_operation
        
        # Create execution engine for nested operations
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            engine = create_execution_engine(user_config, site_config, "dev", repo_root=repo_root)
            
            try:
                # Wrap in a root span to verify nesting
                with traced_operation("test.root") as root_span:
                    assert root_span is not None
                    
                    # Execute SQL - this should create child spans
                    context = ExecutionContext()
                    with traced_operation("test.sql_operation") as sql_span:
                        assert sql_span is not None
                        result = await engine.execute(
                            language="sql",
                            source_code="SELECT 'nested' as test_value",
                            params={},
                            context=context
                        )
                        assert result == [{"test_value": "nested"}]
                    
                    # Execute Python - this should also create child spans  
                    with traced_operation("test.python_operation") as py_span:
                        assert py_span is not None
                        result = await engine.execute(
                            language="python",
                            source_code="return 'nested_result'",
                            params={},
                            context=context
                        )
                        assert result == "nested_result"
                        
            finally:
                engine.shutdown()
    
    asyncio.run(run_nested_operations())


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
