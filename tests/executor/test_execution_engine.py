"""Tests for ExecutionEngine integration.

These tests focus on the ExecutionEngine functionality that manages
multiple executor plugins and provides a unified interface for code execution.
"""

import pytest
import asyncio
import tempfile
from pathlib import Path
from typing import Dict, Any
from unittest.mock import Mock

from mxcp.executor import ExecutionEngine
from mxcp.executor.plugins import PythonExecutor, DuckDBExecutor
from mxcp.executor.plugins.duckdb_plugin.types import DatabaseConfig, PluginConfig
from mxcp.core import ExecutionContext
from mxcp.validator import TypeValidator, ValidationError


@pytest.fixture
def temp_repo_dir():
    """Create a temporary repository directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_dir = Path(tmpdir)
        (repo_dir / "python").mkdir()
        yield repo_dir


@pytest.fixture
def mock_user_config():
    """Create a mock user config."""
    return {
        "mxcp": 1,
        "projects": {
            "test-project": {
                "profiles": {
                    "test": {
                        "duckdb": {"secrets": {}},
                        "plugin": {"config": {}}
                    }
                }
            }
        }
    }


@pytest.fixture
def mock_site_config():
    """Create a mock site config."""
    return {
        "mxcp": 1,
        "project": "test-project",
        "profile": "test",
        "profiles": {
            "test": {
                "duckdb": {"path": ":memory:"}
            }
        },
        "paths": {"tools": "tools"},
        "extensions": []
    }


@pytest.fixture
def mock_context(mock_user_config, mock_site_config):
    """Create a mock execution context with configs."""
    return ExecutionContext(
        user_id="test_user_123",
        username="test_user",
        provider="test",
        external_token="test_token_123",
        email="test@example.com"
    )


@pytest.fixture
def engine_with_executors(temp_repo_dir):
    """Create an execution engine with both Python and DuckDB executors."""
    engine = ExecutionEngine()
    
    python_executor = PythonExecutor(repo_root=temp_repo_dir)
    duckdb_executor = DuckDBExecutor(database_config=DatabaseConfig(path=":memory:", readonly=False, extensions=[]), plugins=[], plugin_config=PluginConfig(plugins_path="plugins", config={}), secrets=[])
    
    engine.register_executor(python_executor)
    engine.register_executor(duckdb_executor)
    
    return engine


class TestExecutionEngineBasics:
    """Test basic ExecutionEngine functionality."""
    
    def test_engine_initialization(self):
        """Test engine initialization."""
        engine = ExecutionEngine()
        
        assert not engine.is_initialized()
        assert engine.get_available_languages() == []
    
    def test_engine_initialization_strict_mode(self):
        """Test engine initialization in strict mode."""
        engine = ExecutionEngine(strict=True)
        
        assert not engine.is_initialized()
        assert engine.get_available_languages() == []
    
    def test_executor_registration(self, temp_repo_dir):
        """Test registering executor plugins."""
        engine = ExecutionEngine()
        
        python_executor = PythonExecutor(repo_root=temp_repo_dir)
        duckdb_executor = DuckDBExecutor(database_config=DatabaseConfig(path=":memory:", readonly=False, extensions=[]), plugins=[], plugin_config=PluginConfig(plugins_path="plugins", config={}), secrets=[])
        
        engine.register_executor(python_executor)
        engine.register_executor(duckdb_executor)
        
        available_languages = engine.get_available_languages()
        assert "python" in available_languages
        assert "sql" in available_languages
    
    def test_duplicate_language_registration(self, temp_repo_dir):
        """Test registering executors with duplicate languages."""
        engine = ExecutionEngine()
        
        python_executor1 = PythonExecutor(repo_root=temp_repo_dir)
        python_executor2 = PythonExecutor(repo_root=temp_repo_dir)
        
        engine.register_executor(python_executor1)
        
        # Should raise error for duplicate language
        with pytest.raises(ValueError, match="already registered"):
            engine.register_executor(python_executor2)
    
    def test_startup_shutdown_lifecycle(self, engine_with_executors, mock_context):
        """Test engine startup and shutdown lifecycle."""
        engine = engine_with_executors
        
        assert not engine.is_initialized()
        
        # Startup
        engine.startup(mock_context)
        assert engine.is_initialized()
        
        # Shutdown
        engine.shutdown()
        assert not engine.is_initialized()
    
    def test_simplified_lifecycle(self, engine_with_executors, mock_context):
        """Test simplified engine lifecycle (no startup/reload needed)."""
        engine = engine_with_executors
        
        # Engine is ready immediately after construction and registration
        # No startup or reload methods needed
        
        # Should be able to execute immediately
        assert "python" in [executor.language for executor in engine._executors.values()]
        assert "sql" in [executor.language for executor in engine._executors.values()]
        
        # Shutdown cleans up all executors
        engine.shutdown()


class TestExecutionEngineCodeExecution:
    """Test code execution through ExecutionEngine."""
    
    @pytest.mark.asyncio
    async def test_python_execution(self, engine_with_executors, mock_context):
        """Test Python code execution through engine."""
        engine = engine_with_executors
        engine.startup(mock_context)
        
        code = """
def add_numbers(a, b):
    return {"result": a + b}
"""
        
        result = await engine.execute(
            language="python",
            source_code=code,
            params={"a": 5, "b": 3}
        )
        
        assert result == {"result": 8}
    
    @pytest.mark.asyncio
    async def test_sql_execution(self, engine_with_executors, mock_context):
        """Test SQL execution through engine."""
        engine = engine_with_executors
        engine.startup(mock_context)
        
        result = await engine.execute(
            language="sql",
            source_code="SELECT $a + $b as result",
            params={"a": 5, "b": 3}
        )
        
        assert len(result) == 1
        assert result[0]["result"] == 8
    
    @pytest.mark.asyncio
    async def test_unsupported_language_error(self, engine_with_executors, mock_context):
        """Test error for unsupported language."""
        engine = engine_with_executors
        engine.startup(mock_context)
        
        with pytest.raises(ValueError, match="No executor found for language"):
            await engine.execute(
                language="javascript",
                source_code="console.log('hello')",
                params={}
            )
    
    @pytest.mark.asyncio
    async def test_execution_before_startup(self, engine_with_executors):
        """Test error when executing before startup."""
        engine = engine_with_executors
        
        with pytest.raises(RuntimeError, match="not initialized"):
            await engine.execute(
                language="python",
                source_code="def test(): return 'hello'",
                params={}
            )


class TestExecutionEngineValidation:
    """Test input/output validation functionality."""
    
    @pytest.mark.asyncio
    async def test_input_validation_with_schema(self, engine_with_executors, mock_context):
        """Test input parameter validation."""
        engine = engine_with_executors
        engine.startup(mock_context)
        
        input_schema = [
            {
                "name": "a",
                "type": "integer",
                "description": "First number"
            },
            {
                "name": "b", 
                "type": "integer",
                "description": "Second number"
            }
        ]
        
        code = """
def add_numbers(a, b):
    return {"result": a + b}
"""
        
        # Valid parameters
        result = await engine.execute(
            language="python",
            source_code=code,
            params={"a": 5, "b": 3},
            input_schema=input_schema
        )
        
        assert result == {"result": 8}
    
    @pytest.mark.asyncio
    async def test_input_validation_failure(self, engine_with_executors, mock_context):
        """Test input validation failure."""
        engine = engine_with_executors
        engine.startup(mock_context)
        
        input_schema = [
            {
                "name": "a",
                "type": "integer",
                "description": "Must be integer"
            }
        ]
        
        code = """
def test_function(a):
    return {"value": a}
"""
        
        # Invalid parameter type
        with pytest.raises(ValidationError):
            await engine.execute(
                language="python",
                source_code=code,
                params={"a": "not_a_number"},
                input_schema=input_schema
            )
    
    @pytest.mark.asyncio
    async def test_output_validation_with_schema(self, engine_with_executors, mock_context):
        """Test output validation."""
        engine = engine_with_executors
        engine.startup(mock_context)
        
        output_schema = {
            "type": "object",
            "properties": {
                "result": {"type": "integer"}
            },
            "required": ["result"]
        }
        
        code = """
def calculate():
    return {"result": 42}
"""
        
        result = await engine.execute(
            language="python",
            source_code=code,
            params={},
            output_schema=output_schema
        )
        
        assert result == {"result": 42}
    
    @pytest.mark.asyncio
    async def test_output_validation_failure(self, engine_with_executors, mock_context):
        """Test output validation failure."""
        engine = engine_with_executors
        engine.startup(mock_context)
        
        output_schema = {
            "type": "object",
            "properties": {
                "result": {"type": "integer"}
            },
            "required": ["result"]
        }
        
        code = """
def calculate():
    return {"wrong_field": "not_integer"}
"""
        
        with pytest.raises(ValidationError):
            await engine.execute(
                language="python",
                source_code=code,
                params={},
                output_schema=output_schema
            )
    
    @pytest.mark.asyncio
    async def test_default_parameter_handling(self, engine_with_executors, mock_context):
        """Test handling of default parameters."""
        engine = engine_with_executors
        engine.startup(mock_context)
        
        input_schema = [
            {
                "name": "name",
                "type": "string",
                "description": "Name to greet"
            },
            {
                "name": "greeting",
                "type": "string", 
                "description": "Greeting prefix",
                "default": "Hello"
            }
        ]
        
        code = """
def greet(name, greeting="Hello"):
    return {"message": f"{greeting}, {name}!"}
"""
        
        # Without default parameter
        result = await engine.execute(
            language="python",
            source_code=code,
            params={"name": "World"},
            input_schema=input_schema
        )
        
        assert result == {"message": "Hello, World!"}
        
        # With explicit parameter
        result = await engine.execute(
            language="python",
            source_code=code,
            params={"name": "World", "greeting": "Hi"},
            input_schema=input_schema
        )
        
        assert result == {"message": "Hi, World!"}


class TestExecutionEngineErrorHandling:
    """Test error handling in ExecutionEngine."""
    
    @pytest.mark.asyncio
    async def test_executor_error_propagation(self, engine_with_executors, mock_context):
        """Test that executor errors are properly propagated."""
        engine = engine_with_executors
        engine.startup(mock_context)
        
        # Python syntax error
        with pytest.raises(Exception):
            await engine.execute(
                language="python",
                source_code="def invalid syntax:",
                params={}
            )
        
        # SQL syntax error
        with pytest.raises(Exception):
            await engine.execute(
                language="sql",
                source_code="SELECT FROM WHERE",
                params={}
            )
    
    @pytest.mark.asyncio
    async def test_validation_error_handling(self, engine_with_executors, mock_context):
        """Test validation error handling."""
        engine = engine_with_executors
        engine.startup(mock_context)
        
        input_schema = [
            {
                "name": "required_param",
                "type": "string",
                "description": "Required parameter"
            }
        ]
        
        # Missing required parameter
        with pytest.raises(ValidationError, match="Required parameter missing"):
            await engine.execute(
                language="python",
                source_code="def test(): return 'hello'",
                params={},
                input_schema=input_schema
            )
    
    @pytest.mark.asyncio
    async def test_engine_state_consistency(self, engine_with_executors, mock_context):
        """Test that engine remains in consistent state after errors."""
        engine = engine_with_executors
        engine.startup(mock_context)
        
        # Cause an error
        try:
            await engine.execute(
                language="python",
                source_code="def invalid syntax:",
                params={}
            )
        except Exception:
            pass
        
        # Engine should still be usable
        assert engine.is_initialized()
        
        # Should be able to execute valid code
        result = await engine.execute(
            language="python",
            source_code="def test(): return {'status': 'ok'}",
            params={}
        )
        
        assert result == {"status": "ok"}


class TestExecutionEngineIntegration:
    """Test integration scenarios between different executors."""
    
    @pytest.mark.asyncio
    async def test_multiple_language_execution(self, engine_with_executors, mock_context):
        """Test executing different languages in sequence."""
        engine = engine_with_executors
        engine.startup(mock_context)
        
        # Create table with SQL
        await engine.execute(
            language="sql",
            source_code="""
                CREATE TABLE test_integration (
                    id INTEGER,
                    name VARCHAR
                )
            """,
            params={}
        )
        
        # Insert data with SQL
        await engine.execute(
            language="sql",
            source_code="""
                INSERT INTO test_integration VALUES 
                (1, 'first'),
                (2, 'second')
            """,
            params={}
        )
        
        # Process with Python (conceptually - Python executor doesn't have DB access in these tests)
        result = await engine.execute(
            language="python",
            source_code="""
def process_data():
    # In real usage, this would access the database
    return {"processed": True, "count": 2}
""",
            params={}
        )
        
        assert result == {"processed": True, "count": 2}
        
        # Verify with SQL
        sql_result = await engine.execute(
            language="sql",
            source_code="SELECT COUNT(*) as total FROM test_integration",
            params={}
        )
        
        assert sql_result[0]["total"] == 2
    
    @pytest.mark.asyncio
    async def test_concurrent_execution(self, engine_with_executors, mock_context):
        """Test concurrent execution of different languages."""
        engine = engine_with_executors
        engine.startup(mock_context)
        
        # Execute both languages concurrently
        python_task = engine.execute(
            language="python",
            source_code="def slow_calc(): return {'result': 42}",
            params={}
        )
        
        sql_task = engine.execute(
            language="sql",
            source_code="SELECT 24 + 18 as result",
            params={}
        )
        
        python_result, sql_result = await asyncio.gather(python_task, sql_task)
        
        assert python_result == {"result": 42}
        assert sql_result[0]["result"] == 42
    
    def test_executor_isolation(self, temp_repo_dir, mock_context):
        """Test that executors maintain proper isolation."""
        engine1 = ExecutionEngine()
        engine2 = ExecutionEngine()
        
        # Register same executor types
        engine1.register_executor(PythonExecutor(repo_root=temp_repo_dir))
        engine1.register_executor(DuckDBExecutor(database_config=DatabaseConfig(path=":memory:", readonly=False, extensions=[]), plugins=[], plugin_config=PluginConfig(plugins_path="plugins", config={}), secrets=[]))
        
        engine2.register_executor(PythonExecutor(repo_root=temp_repo_dir))
        engine2.register_executor(DuckDBExecutor(database_config=DatabaseConfig(path=":memory:", readonly=False, extensions=[]), plugins=[], plugin_config=PluginConfig(plugins_path="plugins", config={}), secrets=[]))
        
        # Start both engines
        engine1.startup(mock_context)
        engine2.startup(mock_context)
        
        # Engines should be independent
        assert engine1.is_initialized()
        assert engine2.is_initialized()
        
        # Shutdown one engine
        engine1.shutdown()
        assert not engine1.is_initialized()
        assert engine2.is_initialized()
        
        # Cleanup
        engine2.shutdown() 