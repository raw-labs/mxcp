"""MXCP SDK Executor Plugins.

This package provides concrete implementations of ExecutorPlugin for different
execution languages and environments.

Available plugins:
- DuckDBExecutor: Executes SQL code using DuckDB with full plugin support
- PythonExecutor: Executes Python code with lifecycle hooks and context management
"""

from typing import Any

__all__ = [
    "DuckDBExecutor",
    "PythonExecutor",
]


def __getattr__(name: str) -> Any:
    if name == "DuckDBExecutor":
        from .duckdb import DuckDBExecutor

        return DuckDBExecutor
    if name == "PythonExecutor":
        from .python import PythonExecutor

        return PythonExecutor
    raise AttributeError(name)
