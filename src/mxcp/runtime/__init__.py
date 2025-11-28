"""
MXCP Runtime module for Python endpoints.

This module provides access to runtime services for Python endpoints.
Uses the SDK executor context system for proper context access.

Key APIs:
- db: Database proxy for executing SQL queries
- config: Configuration proxy for accessing secrets and settings
- plugins: Plugin proxy for accessing loaded plugins
- reload_duckdb(): Reload DuckDB connection

Internal APIs (not for user code):
- _set_global_runtime(): Set the global DuckDB runtime for init hooks
- _get_global_runtime(): Get the global DuckDB runtime
Runtime compatibility note:
    The public ``config.site_config`` and ``config.user_config`` accessors continue
    to expose plain ``dict`` objects for backward compatibility. Internally we
    convert those dictionaries to Pydantic models as needed, but user code can
    keep using the legacy dictionary-style access without changes.
"""

import logging
from collections.abc import Callable
from typing import Any, cast

from mxcp.sdk.executor.context import get_execution_context
from mxcp.sdk.mcp import MCPLogProxy, NullMCPProxy

logger = logging.getLogger(__name__)


class DatabaseProxy:
    """Proxy for database operations using the current execution context."""

    def execute(self, query: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """Execute a SQL query using the shared runtime."""
        context = get_execution_context()
        if not context:
            raise RuntimeError(
                "No execution context available - function not called from MXCP executor"
            )

        duckdb_runtime = context.get("duckdb_runtime")
        if not duckdb_runtime:
            raise RuntimeError(
                "No DuckDB runtime available. Database access is only available "
                "after runtime initialization."
            )

        with duckdb_runtime.get_connection() as session:
            result = session.execute_query_to_dict(query, params)
            # Cast to match expected return type (Hashable -> str for dict keys)
            return cast(list[dict[str, Any]], result)


class ConfigProxy:
    """Proxy for configuration access using the current execution context."""

    def get_secret(self, name: str) -> dict[str, Any] | None:
        """Get secret parameters by name."""
        context = get_execution_context()
        if not context:
            raise RuntimeError(
                "No execution context available - function not called from MXCP executor"
            )

        site_config = cast(dict[str, Any] | None, context.get("site_config"))
        user_config = cast(dict[str, Any] | None, context.get("user_config"))

        if not user_config or not site_config:
            return None

        project = site_config.get("project")
        profile = site_config.get("profile")

        if not project or not profile:
            return None

        projects = user_config.get("projects")
        if not isinstance(projects, dict):
            return None

        project_config = projects.get(project)
        if not isinstance(project_config, dict):
            return None

        profiles = project_config.get("profiles")
        if not isinstance(profiles, dict):
            return None

        profile_config = profiles.get(profile)
        if not isinstance(profile_config, dict):
            return None

        secrets = profile_config.get("secrets", [])
        if not isinstance(secrets, list):
            return None

        for secret in secrets:
            if not isinstance(secret, dict):
                continue
            if secret.get("name") == name:
                params = secret.get("parameters")
                return params if isinstance(params, dict) else {}
        return None

    def get_setting(self, key: str, default: Any = None) -> Any:
        """Get configuration setting from site config."""
        context = get_execution_context()
        if not context:
            raise RuntimeError(
                "No execution context available - function not called from MXCP executor"
            )

        site_config = cast(dict[str, Any] | None, context.get("site_config"))
        if not site_config:
            return default

        raw_config = site_config

        # Support nested key access (e.g., "dbt.enabled")
        if "." in key:
            keys = key.split(".")
            value: Any = raw_config
            for k in keys:
                if isinstance(value, dict) and k in value:
                    value = value[k]
                else:
                    return default
            return value
        else:
            return raw_config.get(key, default)

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

        duckdb_runtime = context.get("duckdb_runtime")
        if not duckdb_runtime:
            return None

        return duckdb_runtime.plugins.get(name)

    def list(self) -> list[str]:
        """Get list of available plugin names."""
        context = get_execution_context()
        if not context:
            raise RuntimeError(
                "No execution context available - function not called from MXCP executor"
            )

        duckdb_runtime = context.get("duckdb_runtime")
        if not duckdb_runtime:
            return []

        return list(duckdb_runtime.plugins.keys())


# ---------------------------------------------------------------------------
# MCP proxy
# ---------------------------------------------------------------------------

_DEFAULT_MCP_INTERFACE: MCPLogProxy = NullMCPProxy()


def _get_mcp_interface() -> MCPLogProxy:
    """Return the MCP interface stored in the execution context, if any."""
    context = get_execution_context()
    if context:
        interface = context.get("mcp")
        if interface:
            return cast(MCPLogProxy, interface)
    return _DEFAULT_MCP_INTERFACE


class _RuntimeMCPProxy:
    """Runtime helper that mirrors FastMCP logging/progress APIs."""

    async def debug(self, message: str, **extra: Any) -> None:
        await _get_mcp_interface().debug(message, **extra)

    async def info(self, message: str, **extra: Any) -> None:
        await _get_mcp_interface().info(message, **extra)

    async def warning(self, message: str, **extra: Any) -> None:
        await _get_mcp_interface().warning(message, **extra)

    async def error(self, message: str, **extra: Any) -> None:
        await _get_mcp_interface().error(message, **extra)

    async def progress(
        self, progress: float, total: float | None = None, message: str | None = None
    ) -> None:
        await _get_mcp_interface().progress(progress, total, message)


# Create singleton proxies
db = DatabaseProxy()
config = ConfigProxy()
plugins = PluginsProxy()
mcp = _RuntimeMCPProxy()

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


def reload_duckdb(payload_func: Callable[[], None] | None = None, description: str = "") -> None:
    """
    Request a system reload with an optional payload function.

    This triggers a full system reload where:
    1. Active requests are drained
    2. Runtime components (Python + DuckDB) are shut down
    3. Your payload function runs (if provided)
    4. Runtime components are restarted

    The payload function runs when the system is safely shut down, making it
    ideal for operations like replacing database files or updating configuration.

    Args:
        payload_func: Optional function to execute during reload
        description: Optional description of what the reload is doing

    Example:
        # Simple reload (just restarts everything)
        mxcp.runtime.reload_duckdb()

        # Reload with database replacement
        def replace_database():
            import shutil
            shutil.copy("updated_data.duckdb", "data.duckdb")

        mxcp.runtime.reload_duckdb(
            payload_func=replace_database,
            description="Replacing database with updated version"
        )

    Note:
        - The reload happens asynchronously after this function returns
        - The payload function runs with all connections closed
        - Safe to call from within a request
        - Active requests will complete before the reload

    Raises:
        RuntimeError: If called outside of MXCP execution context
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

    logger.info(f"Requesting DuckDB reload: {description or 'No description'}")

    # Use the server's reload manager to queue the reload
    server.reload_manager.request_reload(
        payload_func=payload_func, description=description or "DuckDB reload via runtime API"
    )
