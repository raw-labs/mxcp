"""Types for DuckDB infrastructure.

This module re-exports the Pydantic models from models.py for public API.
"""

from .models import (
    DatabaseConfigModel,
    ExtensionDefinitionModel,
    PluginConfigModel,
    PluginDefinitionModel,
    SecretDefinitionModel,
)

__all__ = [
    "ExtensionDefinitionModel",
    "PluginDefinitionModel",
    "PluginConfigModel",
    "SecretDefinitionModel",
    "DatabaseConfigModel",
]
