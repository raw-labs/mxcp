"""ExecutionEngine creation utilities for MXCP.

This module provides utilities for creating properly configured ExecutionEngine
instances with DuckDB and Python executors based on user and site configuration.

The ExecutionEngine provides a unified interface for executing SQL and Python code
through the SDK executor system, with full plugin support and validation.

Example usage:
    >>> from mxcp.config.execution_engine import create_execution_engine
    >>> from mxcp.config.user_config import load_user_config
    >>> from mxcp.config.site_config import load_site_config
    >>> from mxcp.sdk.executor import ExecutionContext
    >>> from mxcp.sdk.auth import UserContext
    >>>
    >>> # Load configurations
    >>> site_config = load_site_config()
    >>> user_config = load_user_config(site_config)
    >>>
    >>> # Create execution engine
    >>> engine = create_execution_engine(user_config, site_config, profile="development")
    >>>
    >>> # Create execution context
    >>> user_context = UserContext(provider="github", user_id="user123", username="user")
    >>> exec_context = ExecutionContext(user_context=user_context)
    >>>
    >>> # Execute SQL
    >>> result = await engine.execute(
    ...     language="sql",
    ...     source_code="SELECT * FROM users WHERE active = $active",
    ...     params={"active": True},
    ...     context=exec_context
    ... )
    >>>
    >>> # Execute Python
    >>> result = await engine.execute(
    ...     language="python",
    ...     source_code="return sum(numbers)",
    ...     params={"numbers": [1, 2, 3, 4, 5]},
    ...     context=exec_context
    ... )
"""

import logging
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Optional

from mxcp.config.site_config import SiteConfig
from mxcp.config.user_config import UserConfig
from mxcp.sdk.executor import (
    ExecutionContext,
    ExecutionEngine,
    reset_execution_context,
    set_execution_context,
)
from mxcp.sdk.executor.plugins import DuckDBExecutor, PythonExecutor

logger = logging.getLogger(__name__)


@contextmanager
def execution_context_for_init_hooks(
    user_config: Optional[UserConfig] = None,
    site_config: Optional[SiteConfig] = None,
    duckdb_session=None,
    plugins: Optional[Dict] = None,
):
    """
    Context manager for setting up ExecutionContext for init hooks.

    This helper function creates an ExecutionContext with the provided
    runtime data, sets it as the current context, and automatically
    cleans it up when done.

    Args:
        user_config: UserConfig object containing user configuration for runtime context
        site_config: SiteConfig object containing site configuration for runtime context
        duckdb_session: DuckDB session for runtime context
        plugins: Plugins dict for runtime context

    Yields:
        The ExecutionContext that was created and set

    Example:
        >>> with execution_context_for_init_hooks(user_config, site_config, session) as context:
        ...     run_init_hooks()  # init hooks have access to context
    """
    context = None
    token = None

    try:
        if user_config and site_config and duckdb_session:
            context = ExecutionContext()
            context.set("user_config", user_config)
            context.set("site_config", site_config)
            context.set("duckdb_session", duckdb_session)
            if plugins:
                context.set("plugins", plugins)
            token = set_execution_context(context)
            logger.info("Set up ExecutionContext for init hooks")

        yield context

    finally:
        if token:
            reset_execution_context(token)
            logger.info("Cleaned up ExecutionContext after init hooks")


def create_execution_engine(
    user_config: UserConfig,
    site_config: SiteConfig,
    profile: Optional[str] = None,
    repo_root: Optional[Path] = None,
    readonly: Optional[bool] = None,
) -> ExecutionEngine:
    """Create an ExecutionEngine with DuckDB and Python executors.

    This function creates a fully configured ExecutionEngine with:
    - DuckDB executor for SQL execution with plugins, extensions, and secrets
    - Python executor for Python code execution with automatic lifecycle hooks

    The engine is fully initialized and ready for execution. The Python executor
    automatically handles module preloading and init hook execution during its
    initialization. Shutdown hooks are run automatically when the engine is shut down.

    Args:
        user_config: User configuration containing secrets and plugin configs by profile
        site_config: Site configuration containing database paths, extensions, and plugin definitions
        profile: Optional profile name (defaults to site_config profile)
        repo_root: Optional repository root for Python executor (defaults to current directory)
        readonly: Optional override for database readonly setting (overrides site config)

    Returns:
        Configured ExecutionEngine ready for use

    Raises:
        RuntimeError: If ExecutionEngine creation fails
        ValueError: If profile is not found in configurations

    Example:
        >>> from mxcp.config.execution_engine import create_execution_engine
        >>> from mxcp.config.user_config import load_user_config
        >>> from mxcp.config.site_config import load_site_config
        >>>
        >>> site_config = load_site_config()
        >>> user_config = load_user_config(site_config)
        >>> engine = create_execution_engine(user_config, site_config)
        >>>
        >>> # Engine is ready to use with both SQL and Python execution
        >>> # Python init hooks have already run during PythonExecutor creation
        >>> # Call engine.shutdown() when done to run shutdown hooks automatically
    """
    try:
        from mxcp.sdk.executor.plugins.duckdb_plugin._types import (
            DatabaseConfig,
            ExtensionDefinition,
            PluginConfig,
            PluginDefinition,
            SecretDefinition,
        )

        # Create ExecutionEngine
        engine = ExecutionEngine(strict=False)

        # Get the profile name to use
        profile_name = profile or site_config["profile"]
        project_name = site_config["project"]

        # Get database configuration from site config profiles section
        site_profiles = site_config.get("profiles", {})
        site_profile_config = site_profiles.get(profile_name, {})
        duckdb_config = site_profile_config.get("duckdb", {})

        # Get database path and readonly setting from site config
        db_path = duckdb_config.get("path") if duckdb_config else None
        if not db_path:
            db_path = f"data/db-{profile_name}.duckdb"
        db_readonly_from_config = duckdb_config.get("readonly") if duckdb_config else False
        db_readonly = readonly if readonly is not None else (db_readonly_from_config or False)

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

        database_config = DatabaseConfig(
            path=db_path, readonly=bool(db_readonly), extensions=extensions
        )

        # Get plugins from site config plugin array
        plugins_list = []
        site_plugins = site_config.get("plugin") or []
        for plugin_def in site_plugins:
            plugin_name = plugin_def.get("name")
            plugin_module = plugin_def.get("module")
            if plugin_name and plugin_module:
                plugins_list.append(
                    PluginDefinition(
                        name=plugin_name,
                        module=plugin_module,
                        config=plugin_def.get("config"),  # References config key in user config
                    )
                )

        # Get plugin configuration from user config
        user_projects = user_config.get("projects") or {}
        user_project = user_projects.get(project_name) or {}
        user_profiles = user_project.get("profiles") or {}
        user_profile = user_profiles.get(profile_name) or {}
        user_plugin_section = user_profile.get("plugin") or {}
        user_plugin_configs = user_plugin_section.get("config") or {}

        # Get plugins path from site config
        site_paths = site_config.get("paths") or {}
        plugins_path = site_paths.get("plugins") or "plugins"

        plugin_config = PluginConfig(plugins_path=plugins_path, config=user_plugin_configs)

        # Get secrets from user config profile
        secrets_list = []
        user_secrets = user_profile.get("secrets") or []
        for secret in user_secrets:
            secret_name = secret.get("name")
            secret_type = secret.get("type")
            secret_params = secret.get("parameters")
            if secret_name and secret_type and secret_params:
                secrets_list.append(
                    SecretDefinition(name=secret_name, type=secret_type, parameters=secret_params)
                )

        # Create and register DuckDB executor
        duckdb_executor = DuckDBExecutor(
            database_config=database_config,
            plugins=plugins_list,
            plugin_config=plugin_config,
            secrets=secrets_list,
        )
        engine.register_executor(duckdb_executor)
        logger.info("Registered DuckDB executor")

        # Create and register Python executor
        if repo_root is None:
            repo_root = find_repo_root()

        # Create Python executor with runtime context for init hooks
        # This ensures init hooks have access to config, db, and plugins
        with execution_context_for_init_hooks(
            user_config=user_config,
            site_config=site_config,
            duckdb_session=duckdb_executor.session,
            plugins=duckdb_executor.session.plugins,
        ):
            python_executor = PythonExecutor(repo_root=repo_root)
        engine.register_executor(python_executor)
        logger.info("Registered Python executor")

        logger.info("ExecutionEngine created successfully with DuckDB and Python executors")
        return engine

    except Exception as e:
        logger.error(f"Failed to create ExecutionEngine: {e}")
        raise RuntimeError(f"Failed to create ExecutionEngine: {e}")


def find_repo_root() -> Path:
    """Find the repository root directory.

    This function attempts to find the root of the current repository by looking
    for common repository markers (.git, pyproject.toml, etc.).

    Returns:
        Path to the repository root, or current working directory if not found
    """
    current = Path.cwd()

    # Look for common repository markers
    markers = [".git", "pyproject.toml", "setup.py", "Cargo.toml", "package.json", "mxcp-site.yml"]

    # Walk up the directory tree
    for parent in [current] + list(current.parents):
        if any((parent / marker).exists() for marker in markers):
            return parent

    # Fall back to current directory
    return current
