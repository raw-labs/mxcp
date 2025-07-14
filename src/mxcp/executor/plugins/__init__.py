"""MXCP Executor Plugins.

This package provides concrete implementations of ExecutorPlugin for different
execution languages and environments.

Available plugins:
- DuckDBExecutor: Executes SQL code using DuckDB with full plugin support
- PythonExecutor: Executes Python code with lifecycle hooks and context management

Each plugin creates and manages its own internal resources (database sessions,
plugins, locking, etc.) based on the shared configuration context.

Example usage:
    >>> from mxcp.executor.plugins import DuckDBExecutor, PythonExecutor
    >>> from mxcp.executor import ExecutionEngine, ExecutionContext
    >>> from pathlib import Path
    >>> 
    >>> # Create DuckDB executor (creates its own session)
    >>> sql_executor = DuckDBExecutor()
    >>> 
    >>> # Create Python executor (manages its own module loading)
    >>> python_executor = PythonExecutor(repo_root=Path("/path/to/repo"))
    >>> 
    >>> # Create engine and register both executors
    >>> engine = ExecutionEngine(strict=False)
    >>> engine.register_executor(sql_executor)
    >>> engine.register_executor(python_executor)
    >>> 
    >>> # Initialize with context (executors create their own resources)
    >>> context = ExecutionContext(
    ...     user_config=user_config,
    ...     site_config=site_config,
    ...     user_context=user_context
    ... )
    >>> engine.startup(context)
    >>> 
    >>> # Execute SQL with validation
    >>> sql_result = await engine.execute(
    ...     language="sql",
    ...     source_code="SELECT COUNT(*) as count FROM users WHERE active = $active",
    ...     params={"active": True},
    ...     input_schema=[{"name": "active", "type": "boolean"}],
    ...     output_schema={"type": "array", "items": {"type": "object"}}
    ... )
    >>> 
    >>> # Execute Python code
    >>> python_result = await engine.execute(
    ...     language="python",
    ...     source_code="return [x * 2 for x in numbers]",
    ...     params={"numbers": [1, 2, 3, 4, 5]}
    ... )
    >>> 
    >>> # Execute Python file
    >>> file_result = await engine.execute(
    ...     language="python",
    ...     source_code="data_analysis.py",
    ...     params={"dataset": "sales_data", "period": "2024-Q1"}
    ... )
    >>> 
    >>> # Validate source code
    >>> valid_sql = sql_executor.validate_source("SELECT 1")
    >>> valid_python = python_executor.validate_source("return 42")
    >>> 
    >>> # Shutdown
    >>> engine.shutdown()
"""

from .duckdb import DuckDBExecutor
from .python import PythonExecutor

__all__ = ["DuckDBExecutor", "PythonExecutor"] 