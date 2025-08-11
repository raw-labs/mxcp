"""DuckDB executor plugin package."""

from ._types import (
    DatabaseConfig,
    ExtensionDefinition,
    PluginConfig,
    PluginDefinition,
    SecretDefinition,
)
from .session import DuckDBSession, execute_query_to_dict

__all__ = [
    "DuckDBSession",
    "execute_query_to_dict",
    "DatabaseConfig",
    "ExtensionDefinition",
    "PluginDefinition",
    "PluginConfig",
    "SecretDefinition",
]
