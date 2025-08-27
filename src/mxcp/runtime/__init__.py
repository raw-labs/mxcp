"""
MXCP Runtime module for Python endpoints.

This module provides access to runtime services for Python endpoints.
Uses the SDK executor context system for proper context access.
"""

import logging
from collections.abc import Callable
from typing import Any, cast

from mxcp.sdk.executor.context import get_execution_context

logger = logging.getLogger(__name__)


class DatabaseProxy:
    """Proxy for database operations using the current execution context."""

    def execute(self, query: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """Execute a SQL query using the current execution context."""
        context = get_execution_context()
        if not context:
            raise RuntimeError(
                "No execution context available - function not called from MXCP executor"
            )

        session = context.get("duckdb_session")
        if not session:
            raise RuntimeError("No DuckDB session available in execution context")

        if params:
            result = session.conn.execute(query, params).fetchdf()
        else:
            result = session.conn.execute(query).fetchdf()

        # Convert DataFrame to list of dicts
        return cast(list[dict[str, Any]], result.to_dict("records"))

    @property
    def connection(self) -> Any:
        """Get the raw DuckDB connection (use with caution)."""
        context = get_execution_context()
        if not context:
            raise RuntimeError(
                "No execution context available - function not called from MXCP executor"
            )

        session = context.get("duckdb_session")
        if not session:
            raise RuntimeError("No DuckDB session available in execution context")

        return session.conn


class ConfigProxy:
    """Proxy for configuration access using the current execution context."""

    def get_secret(self, name: str) -> dict[str, Any] | None:
        """Get secret parameters by name."""
        context = get_execution_context()
        if not context:
            raise RuntimeError(
                "No execution context available - function not called from MXCP executor"
            )

        site_config = context.get("site_config")
        user_config = context.get("user_config")

        if not user_config or not site_config:
            return None

        # Get project and profile from site config
        project = site_config.get("project")
        profile = site_config.get("profile")

        if not project or not profile:
            return None

        try:
            # Navigate to the secrets in user config: projects -> project -> profiles -> profile -> secrets
            project_config = user_config["projects"][project]
            profile_config = project_config["profiles"][profile]
            secrets = profile_config.get("secrets", [])

            # Find secret by name and return its parameters
            for secret in secrets:
                if secret.get("name") == name:
                    return cast(dict[str, Any], secret.get("parameters", {}))

            return None
        except (KeyError, TypeError):
            return None

    def get_setting(self, key: str, default: Any = None) -> Any:
        """Get configuration setting from site config."""
        context = get_execution_context()
        if not context:
            raise RuntimeError(
                "No execution context available - function not called from MXCP executor"
            )

        site_config = context.get("site_config")
        if not site_config:
            return default

        # Support nested key access (e.g., "dbt.enabled")
        if "." in key:
            keys = key.split(".")
            value = site_config
            for k in keys:
                if isinstance(value, dict) and k in value:
                    value = value[k]
                else:
                    return default
            return value
        else:
            return site_config.get(key, default)

    @property
    def user_config(self) -> dict[str, Any] | None:
        """Access full user configuration."""
        context = get_execution_context()
        if not context:
            return None

        return cast(dict[str, Any] | None, context.get("user_config"))

    @property
    def site_config(self) -> dict[str, Any] | None:
        """Access full site configuration."""
        context = get_execution_context()
        if not context:
            return None

        return cast(dict[str, Any] | None, context.get("site_config"))


class PluginsProxy:
    """Proxy for plugin access using the current execution context."""

    def get(self, name: str) -> Any:
        """Get plugin by name."""
        context = get_execution_context()
        if not context:
            raise RuntimeError(
                "No execution context available - function not called from MXCP executor"
            )

        plugins = context.get("plugins")
        if not plugins:
            return None

        return plugins.get(name)

    def list(self) -> list[str]:
        """Get list of available plugin names."""
        context = get_execution_context()
        if not context:
            raise RuntimeError(
                "No execution context available - function not called from MXCP executor"
            )

        plugins = context.get("plugins")
        if not plugins:
            return []

        return list(plugins.keys())


# Create singleton proxies
db = DatabaseProxy()
config = ConfigProxy()
plugins = PluginsProxy()

# Lifecycle hooks
_init_hooks: list[Callable[[], None]] = []
_shutdown_hooks: list[Callable[[], None]] = []


def on_init(func: Callable[[], None]) -> Callable[[], None]:
    """
    Register a function to be called on initialization.

    Example:
        @on_init
        def setup():
            print("Initializing my module")
    """
    _init_hooks.append(func)
    return func


def on_shutdown(func: Callable[[], None]) -> Callable[[], None]:
    """
    Register a function to be called on shutdown.

    Example:
        @on_shutdown
        def cleanup():
            print("Cleaning up resources")
    """
    _shutdown_hooks.append(func)
    return func


def run_init_hooks() -> None:
    """Run all registered init hooks."""
    for hook in _init_hooks:
        try:
            logger.info(f"Running init hook: {hook.__name__}")
            hook()
        except Exception as e:
            logger.error(f"Error in init hook {hook.__name__}: {e}")


def run_shutdown_hooks() -> None:
    """Run all registered shutdown hooks."""
    for hook in _shutdown_hooks:
        try:
            logger.info(f"Running shutdown hook: {hook.__name__}")
            hook()
        except Exception as e:
            logger.error(f"Error in shutdown hook {hook.__name__}: {e}")


def request_reload(rebuild_func: Callable[[], None] | None = None) -> None:
    """
    Request a configuration reload with optional custom rebuild logic.

    This function will:
    1. Drain all active requests
    2. Shut down the execution engine (closing DuckDB)
    3. Run custom rebuild function (if provided)
    4. Reload configuration and recreate engine

    Args:
        rebuild_func: Optional function to run during reload.
                     Called with no active DuckDB connections.
                     This is where you can:
                     - Run dbt to rebuild models
                     - Copy new database files
                     - Run incremental updates
                     - Any custom data pipeline logic

    Example:
        def rebuild():
            import subprocess
            # Run dbt
            subprocess.run(["dbt", "run"], check=True)
            # Or copy new data
            import shutil
            shutil.copy("new_data.duckdb", "data.duckdb")
        mxcp.runtime.request_reload(rebuild)

    Note:
        This function blocks until the reload is complete.
        Requests made during reload will wait up to 30 seconds before timing out.
    """
    context = get_execution_context()
    if not context:
        raise RuntimeError(
            "No execution context available - function not called from MXCP executor"
        )

    # Get server reference from context
    server = context.get("_mxcp_server")
    if not server:
        raise RuntimeError(
            "Server reference not available in context. "
            "This function can only be called from within MXCP server endpoints."
        )

    # Perform reload
    if rebuild_func is not None:
        logger.info("Requesting custom reload with provided rebuild function")
        server.reload_with_custom_logic(rebuild_func)
    else:
        logger.info("Requesting standard configuration reload")
        server.reload_configuration()
