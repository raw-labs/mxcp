"""
Shared DuckDB infrastructure for MXCP.

This module provides a shared DuckDB runtime that can be accessed by multiple
components, including executors and init hooks. This design allows database
access during initialization, which is required for some use cases.

The infrastructure is created at the SDK level and passed to executors,
rather than being owned by any specific executor.
"""

from .runtime import DuckDBRuntime
from .session import DuckDBSession, execute_query_to_dict
from .types import (
    DatabaseConfig,
    ExtensionDefinition,
    PluginConfig,
    PluginDefinition,
    SecretDefinition,
)

__all__ = [
    "DuckDBRuntime",
    "DuckDBSession",
    "execute_query_to_dict",
    "DatabaseConfig",
    "ExtensionDefinition",
    "PluginConfig",
    "PluginDefinition",
    "SecretDefinition",
]
