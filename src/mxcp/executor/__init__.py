"""MXCP Executor module - backward compatibility wrapper.

This module re-exports everything from mxcp.sdk.executor to maintain
backward compatibility with existing code. New code should import from
mxcp.sdk.executor directly.

Key exports:
- ExecutionEngine: Main orchestrator for code execution
- ExecutorPlugin: Base interface for language executors
- ExecutionContext: Runtime context with user info for execution

Example usage:
    >>> from mxcp.executor import ExecutionEngine
    >>> from mxcp.executor.plugins import DuckDBExecutor, PythonExecutor
    >>> from mxcp.sdk.executor import ExecutionContext
    >>> from mxcp.sdk.auth import UserContext
    >>> 
    >>> # Create user context
    >>> user_context = UserContext(username="user", provider="github")
    >>> 
    >>> # Create execution context
    >>> context = ExecutionContext(user_context=user_context)
    >>> 
    >>> # Create engine with executors
    >>> engine = ExecutionEngine()
    >>> engine.register_executor(DuckDBExecutor())
    >>> engine.register_executor(PythonExecutor())
"""

# Re-export everything from SDK for backward compatibility
from mxcp.sdk.executor import (
    ExecutionContext,
    get_execution_context,
    set_execution_context,
    reset_execution_context,
    ExecutorPlugin,
    ExecutionEngine,
)

# Re-export plugins submodule for backward compatibility
from mxcp.sdk.executor import plugins

__all__ = [
    "ExecutionContext",
    "get_execution_context",
    "set_execution_context",
    "reset_execution_context",
    "ExecutorPlugin",
    "ExecutionEngine",
    "plugins",
] 