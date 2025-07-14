"""MXCP Executor System.

This package provides a pluggable execution engine for MXCP that handles
execution of source code in different languages (SQL, Python, etc.) with
proper validation.

The executor system consists of:
- ExecutionEngine: Main orchestrator for validation and execution
- ExecutorPlugin: Base interface for language-specific executors
- ExecutionContext: Runtime context with user info for execution

Each executor creates and manages its own internal resources (database sessions,
plugins, locking, etc.) based on constructor configuration.

Example usage:
    >>> from mxcp.executor import ExecutionEngine
    >>> from mxcp.executor.plugins import DuckDBExecutor, PythonExecutor
    >>> from mxcp.core import ExecutionContext
    >>> 
    >>> # Create executors with configuration
    >>> database_config = DatabaseConfig(path=":memory:", readonly=False, extensions=[])
    >>> duckdb_executor = DuckDBExecutor(database_config, [], plugin_config, [])
    >>> python_executor = PythonExecutor(repo_root="/path/to/repo")
    >>> 
    >>> # Create and configure engine
    >>> engine = ExecutionEngine(strict=False)
    >>> engine.register_executor(duckdb_executor)
    >>> engine.register_executor(python_executor)
    >>> 
    >>> # Execute code with runtime context
    >>> context = ExecutionContext(username="user", provider="github")
    >>> result = await engine.execute("sql", "SELECT 1", {}, context)
"""

from .interfaces import ExecutorPlugin, ExecutionEngine

# Import executor implementations - these create the dependency on the plugins module
from .plugins import DuckDBExecutor, PythonExecutor

# Import from core for user convenience  
from mxcp.core import ExecutionContext

__all__ = [
    "ExecutorPlugin",
    "ExecutionEngine", 
    "ExecutionContext",
    "DuckDBExecutor",
    "PythonExecutor",
] 