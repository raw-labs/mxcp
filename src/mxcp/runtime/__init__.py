"""
MXCP Runtime module for Python endpoints.

This module provides access to runtime services for Python endpoints.
Uses the SDK executor context system for proper context access.
"""

import contextvars
import logging
from typing import Any, Callable, Dict, List, Optional

from mxcp.sdk.executor.context import (
    ExecutionContext,
    get_execution_context,
    reset_execution_context,
    set_execution_context,
)

logger = logging.getLogger(__name__)


class DatabaseProxy:
    """Proxy for database operations using the current execution context."""

    def execute(self, query: str, params: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
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
        return result.to_dict("records")

    @property
    def connection(self):
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

    def get_secret(self, name: str) -> Optional[Dict[str, Any]]:
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
                    return secret.get("parameters", {})

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
    def user_config(self) -> Optional[Dict[str, Any]]:
        """Access full user configuration."""
        context = get_execution_context()
        if not context:
            return None

        return context.get("user_config")

    @property
    def site_config(self) -> Optional[Dict[str, Any]]:
        """Access full site configuration."""
        context = get_execution_context()
        if not context:
            return None

        return context.get("site_config")


class PluginsProxy:
    """Proxy for plugin access using the current execution context."""

    def get(self, name: str):
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

    def list(self) -> List[str]:
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
_init_hooks: List[Callable] = []
_shutdown_hooks: List[Callable] = []


def on_init(func: Callable) -> Callable:
    """
    Register a function to be called on initialization.

    Example:
        @on_init
        def setup():
            print("Initializing my module")
    """
    _init_hooks.append(func)
    return func


def on_shutdown(func: Callable) -> Callable:
    """
    Register a function to be called on shutdown.

    Example:
        @on_shutdown
        def cleanup():
            print("Cleaning up resources")
    """
    _shutdown_hooks.append(func)
    return func


def run_init_hooks():
    """Run all registered init hooks."""
    for hook in _init_hooks:
        try:
            logger.info(f"Running init hook: {hook.__name__}")
            hook()
        except Exception as e:
            logger.error(f"Error in init hook {hook.__name__}: {e}")


def run_shutdown_hooks():
    """Run all registered shutdown hooks."""
    for hook in _shutdown_hooks:
        try:
            logger.info(f"Running shutdown hook: {hook.__name__}")
            hook()
        except Exception as e:
            logger.error(f"Error in shutdown hook {hook.__name__}: {e}")
