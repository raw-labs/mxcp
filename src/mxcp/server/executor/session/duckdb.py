"""Utility for creating SDK DuckDB sessions from MXCP configuration.

This module provides utilities to convert MXCP site and user configurations
into SDK-compatible session objects, centralizing the logic for creating
SDK DuckDB sessions across the codebase.
"""

from mxcp.sdk.executor.plugins.duckdb_plugin.session import DuckDBSession
from mxcp.server.core.config._types import SiteConfig, UserConfig
from mxcp.server.core.config.parsers import create_duckdb_session_config


def create_duckdb_session(
    site_config: SiteConfig,
    user_config: UserConfig,
    profile: str | None = None,
    readonly: bool = False,
) -> DuckDBSession:
    """Create an SDK DuckDB session from MXCP configurations.

    Args:
        site_config: MXCP site configuration
        user_config: MXCP user configuration
        profile: Profile name (defaults to site_config profile)
        readonly: Whether to open database in readonly mode

    Returns:
        Configured SDK DuckDB session
    """
    profile_name = profile or site_config["profile"]

    # Create SDK session configuration
    database_config, plugins, plugin_config, secrets = create_duckdb_session_config(
        site_config, user_config, profile_name, readonly=readonly
    )

    # Create and return SDK DuckDB session
    return DuckDBSession(database_config, plugins, plugin_config, secrets)
