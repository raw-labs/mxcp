"""MXCP Executor Plugins - backward compatibility wrapper.

This module re-exports plugins from mxcp.sdk.executor.plugins to maintain
backward compatibility. New code should import from mxcp.sdk.executor.plugins directly.
"""

# Re-export everything from SDK for backward compatibility
from mxcp.sdk.executor.plugins import DuckDBExecutor, PythonExecutor

__all__ = [
    "DuckDBExecutor",
    "PythonExecutor",
] 