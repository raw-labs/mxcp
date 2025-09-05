"""Tests for Python executor plugin.

These tests focus on the core Python execution functionality of the executor
plugin, including code execution, parameter handling, lifecycle management,
and error conditions.
"""

import tempfile
from pathlib import Path

import pytest

from mxcp.sdk.auth import UserContext
from mxcp.sdk.executor import ExecutionContext
from mxcp.sdk.executor.plugins import PythonExecutor


@pytest.fixture
def temp_repo_dir():
    """Create a temporary repository directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_dir = Path(tmpdir)
        (repo_dir / "python").mkdir()
        yield repo_dir


@pytest.fixture
def mock_context():
    """Create a mock execution context."""
    # Create minimal context with user information
    user_context = UserContext(
        user_id="test_user_123",
        username="test_user",
        provider="test",
        external_token="test_token_123",
        email="test@example.com",
    )
    return ExecutionContext(user_context=user_context)


class TestPythonExecutorBasics:
    """Test basic Python executor functionality."""

    def test_executor_initialization(self, temp_repo_dir):
        """Test executor initialization."""
        executor = PythonExecutor(repo_root=temp_repo_dir)

        assert executor.language == "python"
        assert executor.repo_root == temp_repo_dir
        # Executor is ready immediately after construction
        assert executor._loader is not None  # Ready immediately after construction

    def test_executor_initialization_without_repo_root(self):
        """Test executor initialization without explicit repo root."""
        executor = PythonExecutor()

        assert executor.language == "python"
        assert executor.repo_root is not None  # Should default to cwd

    def test_startup_shutdown_lifecycle(self, temp_repo_dir, mock_context):
        """Test executor startup and shutdown lifecycle."""
        executor = PythonExecutor(repo_root=temp_repo_dir)

        # Should be ready immediately after construction
        assert executor.loader is not None

        # Start up
        # Executor is ready immediately after construction
        assert executor._loader is not None
        assert executor.loader is not None

        # Shutdown
        executor.shutdown()
        # Executor is ready immediately after construction
        # Loader should still exist but be cleaned up

    def test_new_instance_pattern(self, temp_repo_dir, mock_context):
        """Test creating new instances for config changes (instead of reload)."""
        # Create initial executor
        executor1 = PythonExecutor(repo_root=temp_repo_dir)

        loader1 = executor1._loader
        assert loader1 is not None

        # Create a test module to verify different instances have separate state
        python_file = temp_repo_dir / "python" / "instance_test_module.py"
        python_file.write_text("def test_func(): return 'test'")
        loader1.load_python_module(python_file)
        modules_count_after_manual_load = len(loader1._loaded_modules)

        # Create new executor instance with same config
        # This will auto-preload all modules, including the one we just created
        executor2 = PythonExecutor(repo_root=temp_repo_dir)
        loader2 = executor2._loader
        assert loader2 is not None

        # New instance should have separate loader object
        assert loader2 is not loader1

        # Both loaders should have loaded the same module due to auto-preloading
        # but they should be separate instances with their own state
        assert len(loader2._loaded_modules) == modules_count_after_manual_load

        # Verify they have separate state by loading an additional module on loader1
        python_file2 = temp_repo_dir / "python" / "instance_test_module2.py"
        python_file2.write_text("def test_func2(): return 'test2'")
        loader1.load_python_module(python_file2)

        # loader1 should now have one more module than loader2
        assert len(loader1._loaded_modules) == len(loader2._loaded_modules) + 1

        # Clean up
        executor1.shutdown()
        executor2.shutdown()

    def test_validate_source_code(self, temp_repo_dir, mock_context):
        """Test source code validation."""
        executor = PythonExecutor(repo_root=temp_repo_dir)
        # Executor is ready immediately after construction

        # Valid Python code
        assert executor.validate_source("def hello(): return 'world'")
        assert executor.validate_source("x = 1 + 2")
        assert executor.validate_source("import os")  # Valid import

        # Invalid Python code (syntax errors)
        assert not executor.validate_source("def invalid syntax:")
        assert not executor.validate_source("if incomplete")
        assert not executor.validate_source("for x in:")


class TestPythonCodeExecution:
    """Test Python code execution functionality."""

    @pytest.mark.asyncio
    async def test_execute_inline_code(self, temp_repo_dir, mock_context):
        """Test executing inline Python code."""
        executor = PythonExecutor(repo_root=temp_repo_dir)
        # Executor is ready immediately after construction

        # Simple function
        code = """
def add_numbers(a, b):
    return {"result": a + b}
"""

        result = await executor.execute(code, {"a": 5, "b": 3}, mock_context)
        assert result == {"result": 8}

    @pytest.mark.asyncio
    async def test_execute_from_file(self, temp_repo_dir, mock_context):
        """Test executing Python code from file."""
        executor = PythonExecutor(repo_root=temp_repo_dir)
        # Executor is ready immediately after construction

        # Create Python file with unique name to avoid sys.modules conflicts
        python_file = temp_repo_dir / "python" / "executor_test_multiply.py"
        python_file.write_text(
            """
def multiply(a, b):
    return {"result": a * b}

def divide(a, b):
    if b == 0:
        raise ValueError("Cannot divide by zero")
    return {"result": a / b}
"""
        )

        # Execute specific function from file
        result = await executor.execute(
            "python/executor_test_multiply.py:multiply", {"a": 4, "b": 5}, mock_context
        )
        assert result == {"result": 20}

    @pytest.mark.asyncio
    async def test_execute_async_function(self, temp_repo_dir, mock_context):
        """Test executing async Python functions."""
        executor = PythonExecutor(repo_root=temp_repo_dir)
        # Executor is ready immediately after construction

        code = """
import asyncio

async def async_add(a, b):
    await asyncio.sleep(0.01)  # Small delay
    return {"result": a + b, "async": True}
"""

        result = await executor.execute(code, {"a": 10, "b": 20}, mock_context)
        assert result == {"result": 30, "async": True}

    @pytest.mark.asyncio
    async def test_parameter_type_conversion(self, temp_repo_dir, mock_context):
        """Test parameter type conversion and validation."""
        executor = PythonExecutor(repo_root=temp_repo_dir)
        # Executor is ready immediately after construction

        code = """
def test_types(str_param, int_param, float_param, bool_param, list_param, dict_param):
    return {
        "str_type": type(str_param).__name__,
        "int_type": type(int_param).__name__,
        "float_type": type(float_param).__name__,
        "bool_type": type(bool_param).__name__,
        "list_type": type(list_param).__name__,
        "dict_type": type(dict_param).__name__,
        "values": {
            "str_param": str_param,
            "int_param": int_param,
            "float_param": float_param,
            "bool_param": bool_param,
            "list_param": list_param,
            "dict_param": dict_param
        }
    }
"""

        params = {
            "str_param": "hello",
            "int_param": 42,
            "float_param": 3.14,
            "bool_param": True,
            "list_param": [1, 2, 3],
            "dict_param": {"key": "value"},
        }

        result = await executor.execute(code, params, mock_context)

        assert result["str_type"] == "str"
        assert result["int_type"] == "int"
        assert result["float_type"] == "float"
        assert result["bool_type"] == "bool"
        assert result["list_type"] == "list"
        assert result["dict_type"] == "dict"
        assert result["values"] == params


class TestPythonErrorHandling:
    """Test Python execution error handling."""

    @pytest.mark.asyncio
    async def test_syntax_error_handling(self, temp_repo_dir, mock_context):
        """Test handling of Python syntax errors."""
        executor = PythonExecutor(repo_root=temp_repo_dir)
        # Executor is ready immediately after construction

        code = """
def invalid_syntax(:
    return "should not work"
"""

        with pytest.raises(Exception):  # Should raise appropriate syntax error
            await executor.execute(code, {}, mock_context)

    @pytest.mark.asyncio
    async def test_runtime_error_handling(self, temp_repo_dir, mock_context):
        """Test handling of Python runtime errors."""
        executor = PythonExecutor(repo_root=temp_repo_dir)
        # Executor is ready immediately after construction

        code = """
def divide_by_zero():
    return 1 / 0
"""

        with pytest.raises(ZeroDivisionError):
            await executor.execute(code, {}, mock_context)

    @pytest.mark.asyncio
    async def test_custom_exception_handling(self, temp_repo_dir, mock_context):
        """Test handling of custom exceptions."""
        executor = PythonExecutor(repo_root=temp_repo_dir)
        # Executor is ready immediately after construction

        code = """
class CustomError(Exception):
    pass

def raise_custom_error(message):
    raise CustomError(message)
"""

        with pytest.raises(Exception) as exc_info:
            await executor.execute(code, {"message": "Test error"}, mock_context)

        assert "Test error" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_missing_function_error(self, temp_repo_dir, mock_context):
        """Test error when function is not found."""
        executor = PythonExecutor(repo_root=temp_repo_dir)
        # Executor is ready immediately after construction

        python_file = temp_repo_dir / "python" / "empty_module.py"
        python_file.write_text("# Empty module")

        with pytest.raises(AttributeError, match="Function.*not found"):
            await executor.execute("python/empty_module.py:nonexistent_function", {}, mock_context)

    @pytest.mark.asyncio
    async def test_file_not_found_error(self, temp_repo_dir, mock_context):
        """Test error when Python file is not found."""
        executor = PythonExecutor(repo_root=temp_repo_dir)
        # Executor is ready immediately after construction

        with pytest.raises(FileNotFoundError):
            await executor.execute("python/nonexistent.py:function", {}, mock_context)


class TestPythonModuleLoader:
    """Test Python module loading functionality."""

    def test_module_loading_and_caching(self, temp_repo_dir, mock_context):
        """Test module loading and caching behavior."""
        executor = PythonExecutor(repo_root=temp_repo_dir)
        # Executor is ready immediately after construction

        # Create Python module
        python_file = temp_repo_dir / "python" / "cacheable.py"
        python_file.write_text(
            """
import time
load_time = time.time()

def get_load_time():
    return load_time
"""
        )

        # Load module twice
        module1 = executor.loader.load_python_module(python_file)
        module2 = executor.loader.load_python_module(python_file)

        # Should be the same module (cached)
        assert module1 is module2

        # Should have same load time
        func1 = executor.loader.get_function(module1, "get_load_time")
        func2 = executor.loader.get_function(module2, "get_load_time")
        assert func1() == func2()

    def test_function_retrieval(self, temp_repo_dir, mock_context):
        """Test function retrieval from modules."""
        executor = PythonExecutor(repo_root=temp_repo_dir)
        # Executor is ready immediately after construction

        # Create Python module with multiple functions
        python_file = temp_repo_dir / "python" / "functions.py"
        python_file.write_text(
            """
def public_function():
    return "public"

def _private_function():
    return "private"

class TestClass:
    def method(self):
        return "method"

non_callable = "not a function"
"""
        )

        module = executor.loader.load_python_module(python_file)

        # Should be able to get public function
        func = executor.loader.get_function(module, "public_function")
        assert callable(func)
        assert func() == "public"

        # Should be able to get private function
        private_func = executor.loader.get_function(module, "_private_function")
        assert callable(private_func)
        assert private_func() == "private"

        # Should raise error for non-existent function
        with pytest.raises(AttributeError, match="Function.*not found"):
            executor.loader.get_function(module, "nonexistent")

        # Should raise error for non-callable
        with pytest.raises(AttributeError, match="not a callable function"):
            executor.loader.get_function(module, "non_callable")

    def test_module_path_handling(self, temp_repo_dir, mock_context):
        """Test handling of different module paths."""
        executor = PythonExecutor(repo_root=temp_repo_dir)
        # Executor is ready immediately after construction

        # Create nested directory structure
        (temp_repo_dir / "python" / "subpackage").mkdir()

        # Create module in subdirectory
        python_file = temp_repo_dir / "python" / "subpackage" / "nested.py"
        python_file.write_text(
            """
def nested_function():
    return "nested"
"""
        )

        # Should be able to load with relative path
        module1 = executor.loader.load_python_module(Path("python/subpackage/nested.py"))

        # Should be able to load with absolute path
        module2 = executor.loader.load_python_module(python_file)

        # Should be the same module
        assert module1 is module2

        func = executor.loader.get_function(module1, "nested_function")
        assert func() == "nested"


class TestPythonReturnTypes:
    """Test Python return type handling and serialization."""

    @pytest.mark.asyncio
    async def test_basic_return_types(self, temp_repo_dir, mock_context):
        """Test basic return type serialization."""
        executor = PythonExecutor(repo_root=temp_repo_dir)
        # Executor is ready immediately after construction

        code = """
from datetime import datetime, date, time
import json

def test_returns():
    return {
        "string": "hello",
        "integer": 42,
        "float": 3.14,
        "boolean": True,
        "none": None,
        "list": [1, 2, 3],
        "dict": {"nested": True},
        "datetime": datetime(2024, 1, 15, 10, 30, 0),
        "date": date(2024, 1, 15),
        "time": time(10, 30, 0)
    }
"""

        result = await executor.execute(code, {}, mock_context)

        # Basic types should remain unchanged
        assert result["string"] == "hello"
        assert result["integer"] == 42
        assert result["float"] == 3.14
        assert result["boolean"] is True
        assert result["none"] is None
        assert result["list"] == [1, 2, 3]
        assert result["dict"] == {"nested": True}

        # Date/time types should be returned as Python objects
        import datetime as dt

        assert isinstance(result["datetime"], dt.datetime)
        assert isinstance(result["date"], dt.date)
        assert isinstance(result["time"], dt.time)

    @pytest.mark.asyncio
    async def test_complex_return_structures(self, temp_repo_dir, mock_context):
        """Test complex nested return structures."""
        executor = PythonExecutor(repo_root=temp_repo_dir)
        # Executor is ready immediately after construction

        code = """
def complex_structure():
    return {
        "users": [
            {"id": 1, "name": "Alice", "active": True},
            {"id": 2, "name": "Bob", "active": False}
        ],
        "metadata": {
            "total": 2,
            "page": 1,
            "filters": ["active", "name"]
        },
        "nested": {
            "level1": {
                "level2": {
                    "value": "deep"
                }
            }
        }
    }
"""

        result = await executor.execute(code, {}, mock_context)

        assert len(result["users"]) == 2
        assert result["users"][0]["name"] == "Alice"
        assert result["metadata"]["total"] == 2
        assert result["nested"]["level1"]["level2"]["value"] == "deep"
