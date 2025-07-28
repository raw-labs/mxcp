"""MXCP SDK Executor module.

This module provides the core execution framework for MXCP, including:
- ExecutionContext: Runtime context for execution state (sessions, configs, plugins)
- ExecutorPlugin: Base interface for execution plugins
- ExecutionEngine: Main engine for executing code across different languages

The executor system supports multiple languages through a plugin architecture,
with built-in support for SQL (via DuckDB) and Python execution.
"""

from .context import (
    ExecutionContext,
    get_execution_context,
    set_execution_context,
    reset_execution_context
)
from .interfaces import ExecutorPlugin, ExecutionEngine

__all__ = [
    # Context
    "ExecutionContext",
    "get_execution_context",
    "set_execution_context",
    "reset_execution_context",
    
    # Interfaces
    "ExecutorPlugin",
    "ExecutionEngine",
] 