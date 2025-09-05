"""Tests for ExecutionEngine integration.

These tests focus on the ExecutionEngine functionality that manages
multiple executor plugins and provides a unified interface for code execution.
"""

import asyncio
import contextlib
import tempfile
from pathlib import Path

import pytest

from mxcp.sdk.auth import UserContext
from mxcp.sdk.executor import ExecutionContext, ExecutionEngine
from mxcp.sdk.executor.plugins import DuckDBExecutor, PythonExecutor
from mxcp.sdk.duckdb import DatabaseConfig, PluginConfig, DuckDBRuntime
from mxcp.sdk.validator import ValidationError


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
                "profiles": {"test": {"duckdb": {"secrets": {}}, "plugin": {"config": {}}}}
            }
        },
    }


@pytest.fixture
def mock_site_config():
    """Create a mock site config."""
    return {
        "mxcp": 1,
        "project": "test-project",
        "profile": "test",
        "profiles": {"test": {"duckdb": {"path": "test.duckdb"}}},
        "paths": {"tools": "tools"},
        "extensions": [],
    }


@pytest.fixture
def mock_context(mock_user_config, mock_site_config):
    """Create a mock execution context with configs."""
    user_context = UserContext(
        user_id="test_user_123",
        username="test_user",
        provider="test",
        external_token="test_token_123",
        email="test@example.com",
    )
    return ExecutionContext(user_context=user_context)


@pytest.fixture
def engine_with_executors(temp_repo_dir, tmp_path):
    """Create an execution engine with both Python and DuckDB executors."""
    engine = ExecutionEngine()

    # Create shared runtime
    db_path = tmp_path / "test_engine.duckdb"
    runtime = DuckDBRuntime(
        database_config=DatabaseConfig(path=str(db_path), readonly=False, extensions=[]),
        plugins=[],
        plugin_config=PluginConfig(plugins_path="plugins", config={}),
        secrets=[],
    )

    python_executor = PythonExecutor(repo_root=temp_repo_dir)
    duckdb_executor = DuckDBExecutor(runtime)

    engine.register_executor(python_executor)
    engine.register_executor(duckdb_executor)

    # Store runtime for cleanup
    engine._test_runtime = runtime

    return engine


class TestExecutionEngineBasics:
    """Test basic ExecutionEngine functionality."""

    def test_engine_initialization(self):
        """Test engine initialization."""
        engine = ExecutionEngine()

        assert len(engine._executors) == 0
        assert len(engine._executors) == 0

    def test_engine_initialization_strict_mode(self):
        """Test engine initialization in strict mode."""
        engine = ExecutionEngine(strict=True)

        assert len(engine._executors) == 0
        assert len(engine._executors) == 0

    def test_executor_registration(self, temp_repo_dir):
        """Test registering executor plugins."""
        engine = ExecutionEngine()

        python_executor = PythonExecutor(repo_root=temp_repo_dir)

        # Create DuckDB runtime first
        duckdb_runtime = DuckDBRuntime(
            database_config=DatabaseConfig(
                path=str(temp_repo_dir / "test.db"), readonly=False, extensions=[]
            ),
            plugins=[],
            plugin_config=PluginConfig(plugins_path="plugins", config={}),
            secrets=[],
        )
        duckdb_executor = DuckDBExecutor(runtime=duckdb_runtime)

        engine.register_executor(python_executor)
        engine.register_executor(duckdb_executor)

        available_languages = list(engine._executors.keys())
        assert "python" in available_languages
        assert "sql" in available_languages

        # Clean up
        duckdb_runtime.shutdown()

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
        """Test engine shutdown lifecycle (executors are ready immediately after registration)."""
        engine = engine_with_executors

        # Executors are ready immediately after registration
        assert len(engine._executors) == 2

        # Shutdown
        engine.shutdown()
        assert len(engine._executors) == 0

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

        code = """
def add_numbers(a, b):
    return {"result": a + b}
"""

        result = await engine.execute(
            language="python", source_code=code, params={"a": 5, "b": 3}, context=mock_context
        )

        assert result == {"result": 8}

    @pytest.mark.asyncio
    async def test_sql_execution(self, engine_with_executors, mock_context):
        """Test SQL execution through engine."""
        engine = engine_with_executors

        result = await engine.execute(
            language="sql",
            source_code="SELECT $a + $b as result",
            params={"a": 5, "b": 3},
            context=mock_context,
        )

        assert len(result) == 1
        assert result[0]["result"] == 8

    @pytest.mark.asyncio
    async def test_unsupported_language_error(self, engine_with_executors, mock_context):
        """Test error for unsupported language."""
        engine = engine_with_executors

        with pytest.raises(ValueError, match="Language .* not supported"):
            await engine.execute(
                language="javascript",
                source_code="console.log('hello')",
                params={},
                context=mock_context,
            )

    @pytest.mark.asyncio
    async def test_execution_with_unregistered_language(self, mock_context):
        """Test error when executing with unregistered language."""
        engine = ExecutionEngine()
        # Don't register any executors

        with pytest.raises(ValueError, match="Language .* not supported"):
            await engine.execute(
                language="python",
                source_code="def test(): return 'hello'",
                params={},
                context=mock_context,
            )


class TestExecutionEngineValidation:
    """Test input/output validation functionality."""

    @pytest.mark.asyncio
    async def test_input_validation_with_schema(self, engine_with_executors, mock_context):
        """Test input parameter validation."""
        engine = engine_with_executors

        input_schema = [
            {"name": "a", "type": "integer", "description": "First number"},
            {"name": "b", "type": "integer", "description": "Second number"},
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
            context=mock_context,
            input_schema=input_schema,
        )

        assert result == {"result": 8}

    @pytest.mark.asyncio
    async def test_input_validation_failure(self, engine_with_executors, mock_context):
        """Test input validation failure."""
        engine = engine_with_executors

        input_schema = [{"name": "a", "type": "integer", "description": "Must be integer"}]

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
                context=mock_context,
                input_schema=input_schema,
            )

    @pytest.mark.asyncio
    async def test_output_validation_with_schema(self, engine_with_executors, mock_context):
        """Test output validation."""
        engine = engine_with_executors

        output_schema = {
            "type": "object",
            "properties": {"result": {"type": "integer"}},
            "required": ["result"],
        }

        code = """
def calculate():
    return {"result": 42}
"""

        result = await engine.execute(
            language="python",
            source_code=code,
            params={},
            context=mock_context,
            output_schema=output_schema,
        )

        assert result == {"result": 42}

    @pytest.mark.asyncio
    async def test_output_validation_failure(self, engine_with_executors, mock_context):
        """Test output validation failure."""
        engine = engine_with_executors

        output_schema = {
            "type": "object",
            "properties": {"result": {"type": "integer"}},
            "required": ["result"],
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
                context=mock_context,
                output_schema=output_schema,
            )

    @pytest.mark.asyncio
    async def test_default_parameter_handling(self, engine_with_executors, mock_context):
        """Test handling of default parameters."""
        engine = engine_with_executors

        input_schema = [
            {"name": "name", "type": "string", "description": "Name to greet"},
            {
                "name": "greeting",
                "type": "string",
                "description": "Greeting prefix",
                "default": "Hello",
            },
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
            context=mock_context,
            input_schema=input_schema,
        )

        assert result == {"message": "Hello, World!"}

        # With explicit parameter
        result = await engine.execute(
            language="python",
            source_code=code,
            params={"name": "World", "greeting": "Hi"},
            context=mock_context,
            input_schema=input_schema,
        )

        assert result == {"message": "Hi, World!"}


class TestExecutionEngineErrorHandling:
    """Test error handling in ExecutionEngine."""

    @pytest.mark.asyncio
    async def test_executor_error_propagation(self, engine_with_executors, mock_context):
        """Test that executor errors are properly propagated."""
        engine = engine_with_executors

        # Python syntax error
        with pytest.raises(Exception):
            await engine.execute(
                language="python",
                source_code="def invalid syntax:",
                params={},
                context=mock_context,
            )

        # SQL syntax error
        with pytest.raises(Exception):
            await engine.execute(
                language="sql", source_code="SELECT FROM WHERE", params={}, context=mock_context
            )

    @pytest.mark.asyncio
    async def test_validation_error_handling(self, engine_with_executors, mock_context):
        """Test validation error handling."""
        engine = engine_with_executors

        input_schema = [
            {"name": "required_param", "type": "string", "description": "Required parameter"}
        ]

        # Missing required parameter
        with pytest.raises(ValidationError, match="Required parameter missing"):
            await engine.execute(
                language="python",
                source_code="def test(): return 'hello'",
                params={},
                context=mock_context,
                input_schema=input_schema,
            )

    @pytest.mark.asyncio
    async def test_engine_state_consistency(self, engine_with_executors, mock_context):
        """Test that engine remains in consistent state after errors."""
        engine = engine_with_executors

        # Cause an error
        with contextlib.suppress(Exception):
            await engine.execute(
                language="python",
                source_code="def invalid syntax:",
                params={},
                context=mock_context,
            )

        # Engine should still be usable
        assert len(engine._executors) > 0

        # Should be able to execute valid code
        result = await engine.execute(
            language="python",
            source_code="def test(): return {'status': 'ok'}",
            params={},
            context=mock_context,
        )

        assert result == {"status": "ok"}


class TestExecutionEngineIntegration:
    """Test integration scenarios between different executors."""

    @pytest.mark.asyncio
    async def test_multiple_language_execution(self, engine_with_executors, mock_context):
        """Test executing different languages in sequence."""
        engine = engine_with_executors

        # Create table with SQL
        await engine.execute(
            language="sql",
            source_code="""
                CREATE TABLE test_integration (
                    id INTEGER,
                    name VARCHAR
                )
            """,
            params={},
            context=mock_context,
        )

        # Insert data with SQL
        await engine.execute(
            language="sql",
            source_code="""
                INSERT INTO test_integration VALUES
                (1, 'first'),
                (2, 'second')
            """,
            params={},
            context=mock_context,
        )

        # Process with Python (conceptually - Python executor doesn't have DB access in these tests)
        result = await engine.execute(
            language="python",
            source_code="""
def process_data():
    # In real usage, this would access the database
    return {"processed": True, "count": 2}
""",
            params={},
            context=mock_context,
        )

        assert result == {"processed": True, "count": 2}

        # Verify with SQL
        sql_result = await engine.execute(
            language="sql",
            source_code="SELECT COUNT(*) as total FROM test_integration",
            params={},
            context=mock_context,
        )

        assert sql_result[0]["total"] == 2

    @pytest.mark.asyncio
    async def test_concurrent_execution(self, engine_with_executors, mock_context):
        """Test concurrent execution of different languages."""
        engine = engine_with_executors

        # Execute both languages concurrently
        python_task = engine.execute(
            language="python",
            source_code="def slow_calc(): return {'result': 42}",
            params={},
            context=mock_context,
        )

        sql_task = engine.execute(
            language="sql", source_code="SELECT 24 + 18 as result", params={}, context=mock_context
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
        runtime1 = DuckDBRuntime(
            database_config=DatabaseConfig(
                path=str(temp_repo_dir / "test1.db"), readonly=False, extensions=[]
            ),
            plugins=[],
            plugin_config=PluginConfig(plugins_path="plugins", config={}),
            secrets=[],
        )
        engine1.register_executor(DuckDBExecutor(runtime=runtime1))

        engine2.register_executor(PythonExecutor(repo_root=temp_repo_dir))
        runtime2 = DuckDBRuntime(
            database_config=DatabaseConfig(
                path=str(temp_repo_dir / "test2.db"), readonly=False, extensions=[]
            ),
            plugins=[],
            plugin_config=PluginConfig(plugins_path="plugins", config={}),
            secrets=[],
        )
        engine2.register_executor(DuckDBExecutor(runtime=runtime2))

        # Start both engines

        # Engines should be independent
        assert len(engine1._executors) > 0
        assert len(engine2._executors) > 0

        # Shutdown one engine
        engine1.shutdown()
        assert len(engine1._executors) == 0
        assert len(engine2._executors) > 0

        # Cleanup
        engine1.shutdown()
        engine2.shutdown()
        runtime1.shutdown()
        runtime2.shutdown()
