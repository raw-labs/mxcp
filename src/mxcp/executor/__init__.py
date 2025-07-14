"""MXCP Executor System.

This package provides a pluggable execution engine for MXCP that handles
execution of source code in different languages (SQL, Python, etc.) with
proper validation and lifecycle management.

The executor system consists of:
- ExecutionEngine: Main orchestrator for validation and execution
- ExecutorPlugin: Base interface for language-specific executors
- ExecutionContext: Runtime context with shared configuration and user info
- LifecycleManager: Manages startup/shutdown/reload of multiple engines

Each executor creates and manages its own internal resources (database sessions,
plugins, locking, etc.) based on the shared configuration context.

Example usage:
    >>> from mxcp.executor import (
    ...     ExecutionEngine, ExecutionContext, LifecycleManager,
    ...     create_execution_context
    ... )
    >>> from mxcp.executor.plugins import DuckDBExecutor, PythonExecutor
    >>> 
    >>> # Create and configure engines
    >>> sql_engine = ExecutionEngine(strict=False)
    >>> sql_engine.register_executor(DuckDBExecutor())
    >>> 
    >>> python_engine = ExecutionEngine(strict=True)
    >>> python_engine.register_executor(PythonExecutor())
    >>> 
    >>> # Create lifecycle manager
    >>> manager = LifecycleManager()
    >>> manager.register_engine("sql", sql_engine)
    >>> manager.register_engine("python", python_engine)
    >>> 
    >>> # Create context and start up (executors create their own resources)
    >>> context = create_execution_context(
    ...     user_config=user_config,
    ...     site_config=site_config,
    ...     user_context=user_context
    ... )
    >>> manager.startup(context)
    >>> 
    >>> # Execute with per-query validation
    >>> sql_engine = manager.get_engine("sql")
    >>> input_schema = [{"name": "limit", "type": "integer", "default": 10}]
    >>> output_schema = {"type": "array", "items": {"type": "object"}}
    >>> 
    >>> result = await sql_engine.execute(
    ...     language="sql",
    ...     source_code="SELECT * FROM users LIMIT $limit",
    ...     params={"limit": 5},
    ...     input_schema=input_schema,
    ...     output_schema=output_schema
    ... )
    >>> 
    >>> # Execute Python without validation
    >>> python_engine = manager.get_engine("python")
    >>> result = await python_engine.execute(
    ...     language="python",
    ...     source_code="return sum(data)",
    ...     params={"data": [1, 2, 3, 4, 5]}
    ... )
"""

from .interfaces import ExecutionEngine, ExecutionContext, ExecutorPlugin
from .lifecycle import LifecycleManager, create_execution_context

__all__ = [
    "ExecutionEngine",
    "ExecutionContext", 
    "ExecutorPlugin",
    "LifecycleManager",
    "create_execution_context",
] 