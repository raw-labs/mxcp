"""Core MXCP modules and shared components.

This package contains the core functionality that is shared across all MXCP
components including execution context, configuration, and common utilities.
"""

from .context import ExecutionContext

__all__ = [
    "ExecutionContext",
] 