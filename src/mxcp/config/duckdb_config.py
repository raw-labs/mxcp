"""DuckDB configuration utilities for MXCP.

This module provides utilities to convert MXCP site and user configurations
into SDK-compatible DuckDB configuration objects.
"""

from typing import Any, cast

from mxcp.core.config._types import SiteConfig, UserConfig
from mxcp.sdk.executor.plugins.duckdb_plugin._types import (
    DatabaseConfig,
    ExtensionDefinition,
    PluginConfig,
    PluginDefinition,
    SecretDefinition,
)


def create_duckdb_session_config(
    site_config: SiteConfig, user_config: UserConfig, profile_name: str, readonly: bool = False
) -> tuple[DatabaseConfig, list[PluginDefinition], PluginConfig, list[SecretDefinition]]:
    """Convert MXCP configs to SDK session configuration objects.

    Args:
        site_config: MXCP site configuration
        user_config: MXCP user configuration
        profile_name: Profile name to use
        readonly: Whether to open database in readonly mode

    Returns:
        Tuple of (database_config, plugins, plugin_config, secrets)
    """
    # Get project name from site config
    project_name = site_config["project"]

    # Get database configuration from site config profiles section
    site_profiles = site_config.get("profiles") or {}
    site_profile_config = site_profiles.get(profile_name) or {}
    duckdb_config = site_profile_config.get("duckdb") or {}

    # Get database path from site config (with fallback)
    db_path = duckdb_config.get("path") if duckdb_config else None
    if not db_path:
        db_path = f"data/db-{profile_name}.duckdb"

    # Get extensions from site config (root level)
    extensions_config = site_config.get("extensions") or []
    extensions = []
    for ext in extensions_config:
        if isinstance(ext, str):
            # Simple string extension name
            extensions.append(ExtensionDefinition(name=ext))
        elif isinstance(ext, dict):
            # Extension with repo specification
            ext_name = ext.get("name")
            if ext_name:
                extensions.append(ExtensionDefinition(name=ext_name, repo=ext.get("repo")))

    database_config = DatabaseConfig(path=db_path, readonly=readonly, extensions=extensions)

    # Get plugins from site config plugin array
    plugins = []
    site_plugins = site_config.get("plugin") or []
    for plugin_def in site_plugins:
        plugin_name = plugin_def.get("name")
        plugin_module = plugin_def.get("module")
        if plugin_name and plugin_module:
            plugins.append(
                PluginDefinition(
                    name=plugin_name,
                    module=plugin_module,
                    config=plugin_def.get("config"),  # References config key in user config
                )
            )

    # Get plugin configuration from user config
    user_projects = user_config.get("projects") or {}
    user_project = cast(dict[str, Any], user_projects.get(project_name) or {})
    user_profiles = user_project.get("profiles") or {}
    user_profile = user_profiles.get(profile_name) or {}
    user_plugin_section = user_profile.get("plugin") or {}
    user_plugin_configs = user_plugin_section.get("config") or {}

    # Get plugins path from site config
    site_paths = site_config.get("paths") or {}
    plugins_path = site_paths.get("plugins") or "plugins"

    plugin_config = PluginConfig(plugins_path=plugins_path, config=user_plugin_configs)

    # Get secrets from user config profile
    secrets = []
    user_secrets = user_profile.get("secrets") or []
    for secret in user_secrets:
        secret_name = secret.get("name")
        secret_type = secret.get("type")
        secret_params = secret.get("parameters")
        if secret_name and secret_type and secret_params:
            secrets.append(
                SecretDefinition(name=secret_name, type=secret_type, parameters=secret_params)
            )

    return database_config, plugins, plugin_config, secrets
