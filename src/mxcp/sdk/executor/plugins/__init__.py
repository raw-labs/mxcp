"""MXCP SDK Executor Plugins.

This package provides concrete implementations of ExecutorPlugin for different
execution languages and environments.

Available plugins:
- DuckDBExecutor: Executes SQL code using DuckDB with full plugin support
- PythonExecutor: Executes Python code with lifecycle hooks and context management

``DuckDBExecutor`` (which transitively ``import duckdb``) is loaded lazily on
first access via :pep:`562`, so importing this package to get ``PythonExecutor``
does not pull in the duckdb native library.
"""

from typing import TYPE_CHECKING

from .python import PythonExecutor

if TYPE_CHECKING:
    from .duckdb import DuckDBExecutor


def __getattr__(name: str) -> object:
    """Lazily import the duckdb-backed executor on first access (PEP 562)."""
    if name == "DuckDBExecutor":
        from .duckdb import DuckDBExecutor

        return DuckDBExecutor
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "DuckDBExecutor",
    "PythonExecutor",
]
