"""Configuration parsers for MXCP.

This module contains utilities for parsing and transforming configuration
data into SDK-compatible formats.
"""

# Re-export the existing functions during migration
from mxcp.config.duckdb_config import create_duckdb_session_config
from mxcp.config.execution_context import execution_context_for_init_hooks

__all__ = [
    "create_duckdb_session_config",
    "execution_context_for_init_hooks",
]
