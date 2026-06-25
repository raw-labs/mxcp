"""Shared DuckDB infrastructure for MXCP.

This module provides a shared DuckDB runtime that can be accessed by multiple
components, including executors and init hooks. This design allows database
access during initialization, which is required for some use cases.

The infrastructure is created at the SDK level and passed to executors,
rather than being owned by any specific executor.

The runtime/session symbols (which transitively ``import duckdb``) are loaded
lazily on first access via :pep:`562`. Importing this package therefore does
*not* pull in the duckdb native library — only the lightweight config models
are imported eagerly. This lets the server avoid the DuckDB memory footprint
entirely when DuckDB is disabled (``duckdb.enabled: false``).
"""

from typing import TYPE_CHECKING

from .models import (
    DatabaseConfigModel,
    ExtensionDefinitionModel,
    PluginConfigModel,
    PluginDefinitionModel,
    SecretDefinitionModel,
)

if TYPE_CHECKING:
    from .runtime import DuckDBRuntime
    from .session import DuckDBSession, execute_query_to_dict

# Map lazily-loaded attribute names to the submodule that defines them.
_LAZY_ATTRS = {
    "DuckDBRuntime": ".runtime",
    "DuckDBSession": ".session",
    "execute_query_to_dict": ".session",
}


def __getattr__(name: str) -> object:
    """Lazily import heavy (duckdb-backed) symbols on first access (PEP 562)."""
    module_name = _LAZY_ATTRS.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    import importlib

    module = importlib.import_module(module_name, __name__)
    return getattr(module, name)


__all__ = [
    "DuckDBRuntime",
    "DuckDBSession",
    "execute_query_to_dict",
    "DatabaseConfigModel",
    "ExtensionDefinitionModel",
    "PluginConfigModel",
    "PluginDefinitionModel",
    "SecretDefinitionModel",
]
