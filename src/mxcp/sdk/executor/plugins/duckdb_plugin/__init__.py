"""DuckDB executor plugin package."""

from .session import DuckDBSession, execute_query_to_dict
from .types import (
    DatabaseConfig, ExtensionDefinition, PluginDefinition, 
    PluginConfig, SecretDefinition
)

__all__ = [
    "DuckDBSession", 
    "execute_query_to_dict",
    "DatabaseConfig",
    "ExtensionDefinition", 
    "PluginDefinition",
    "PluginConfig",
    "SecretDefinition"
] 