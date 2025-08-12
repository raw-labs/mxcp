"""MXCP SDK Executor Plugins.

This package provides concrete implementations of ExecutorPlugin for different
execution languages and environments.

Available plugins:
- DuckDBExecutor: Executes SQL code using DuckDB with full plugin support
- PythonExecutor: Executes Python code with lifecycle hooks and context management
"""

from .duckdb import DuckDBExecutor
from .python import PythonExecutor

__all__ = [
    "DuckDBExecutor",
    "PythonExecutor",
]
