"""Configuration parsers and utilities for MXCP.

This module provides utilities to:
1. Convert MXCP site and user configurations into SDK-compatible DuckDB configuration objects
2. Manage ExecutionContext during initialization and configuration phases
"""

import logging
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from mxcp.sdk.duckdb import (
    DatabaseConfig,
    ExtensionDefinition,
    PluginConfig,
    PluginDefinition,
    SecretDefinition,
)
from mxcp.sdk.executor import (
    ExecutionContext,
    reset_execution_context,
    set_execution_context,
)
from mxcp.server.core.config.models import SiteConfigModel, UserConfigModel

logger = logging.getLogger(__name__)


def create_duckdb_session_config(
    site_config: SiteConfigModel,
    user_config: UserConfigModel,
    profile_name: str,
    readonly: bool = False,
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
    project_name = site_config.project

    # Get database configuration from site config profiles section
    site_profile_config = site_config.profiles.get(profile_name)
    duckdb_config = site_profile_config.duckdb if site_profile_config else None

    # Get database path from site config (with fallback)
    db_path = duckdb_config.path if duckdb_config and duckdb_config.path else None
    if not db_path:
        db_path = str(Path(site_config.paths.data) / f"db-{profile_name}.duckdb")

    # Get extensions from site config (root level)
    extensions = [
        ExtensionDefinition(name=ext.name, repo=ext.repo) for ext in site_config.extensions
    ]

    database_config = DatabaseConfig(path=db_path, readonly=readonly, extensions=extensions)

    # Get plugins from site config plugin array
    plugins = [
        PluginDefinition(name=plugin_def.name, module=plugin_def.module, config=plugin_def.config)
        for plugin_def in site_config.plugin
    ]

    # Get plugin configuration from user config
    user_project = user_config.projects.get(project_name)
    user_profile = user_project.profiles.get(profile_name) if user_project else None
    user_plugin_configs = user_profile.plugin.config if user_profile else {}

    # Get plugins path from site config
    plugins_path = site_config.paths.plugins

    plugin_config = PluginConfig(plugins_path=plugins_path, config=user_plugin_configs)

    # Get secrets from user config profile
    secrets = []
    user_secrets = user_profile.secrets if user_profile else []
    for secret in user_secrets:
        if secret.parameters:
            secrets.append(
                SecretDefinition(
                    name=secret.name,
                    type=secret.type,
                    parameters=secret.parameters,
                )
            )

    return database_config, plugins, plugin_config, secrets


@contextmanager
def execution_context_for_init_hooks(
    user_config: UserConfigModel | None = None,
    site_config: SiteConfigModel | None = None,
    duckdb_runtime: Any | None = None,
) -> Generator[ExecutionContext | None, None, None]:
    """
    Context manager for setting up ExecutionContext for init hooks.

    This helper function creates an ExecutionContext with the provided
    runtime data, sets it as the current context, and automatically
    cleans it up when done.

    Args:
        user_config: UserConfigModel instance containing runtime configuration
        site_config: SiteConfigModel instance containing site configuration
        duckdb_runtime: DuckDB runtime instance for database access

    Yields:
        The ExecutionContext that was created and set

    Example:
        >>> with execution_context_for_init_hooks(user_config, site_config, duckdb_runtime) as context:
        ...     run_init_hooks()  # init hooks have access to context
    """
    context = None
    token = None

    try:
        if user_config and site_config:
            context = ExecutionContext()
            context.set("user_config", user_config.model_dump(mode="python", exclude_unset=True))
            context.set("site_config", site_config.model_dump(mode="python", exclude_unset=True))
            if duckdb_runtime:
                context.set("duckdb_runtime", duckdb_runtime)
            token = set_execution_context(context)
            logger.info("Set up ExecutionContext for init hooks")

        yield context

    finally:
        if token:
            reset_execution_context(token)
            logger.info("Cleaned up ExecutionContext after init hooks")
