"""ExecutionEngine creation utilities for MXCP.

This module provides utilities for creating properly configured ExecutionEngine
instances with DuckDB and Python executors based on user and site configuration.

The ExecutionEngine provides a unified interface for executing SQL and Python code
through the SDK executor system, with full plugin support and validation.

Example usage:
    >>> from mxcp.server.executor.engine import create_execution_engine
    >>> from mxcp.server.core.config.user_config import load_user_config
    >>> from mxcp.server.core.config.site_config import load_site_config
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
from pathlib import Path

from mxcp.sdk.executor import ExecutionEngine
from mxcp.sdk.executor.plugins import DuckDBExecutor, PythonExecutor
from mxcp.server.core.config._types import SiteConfig, UserConfig
from mxcp.server.core.config.parsers import (
    create_duckdb_session_config,
    execution_context_for_init_hooks,
)
from mxcp.server.core.config.site_config import find_repo_root

logger = logging.getLogger(__name__)


def create_execution_engine(
    user_config: UserConfig,
    site_config: SiteConfig,
    profile: str | None = None,
    repo_root: Path | None = None,
    readonly: bool | None = None,
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
        >>> from mxcp.server.executor.engine import create_execution_engine
        >>> from mxcp.server.core.config.user_config import load_user_config
        >>> from mxcp.server.core.config.site_config import load_site_config
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

        # Create ExecutionEngine
        engine = ExecutionEngine(strict=False)

        # Get the profile name to use
        profile_name = profile or site_config["profile"]

        # Handle readonly override
        db_readonly_from_config = False
        if "profiles" in site_config:
            site_profiles = site_config.get("profiles", {})
            site_profile_config = site_profiles.get(profile_name, {})
            duckdb_config = site_profile_config.get("duckdb", {})
            db_readonly_from_config = (
                bool(duckdb_config.get("readonly", False)) if duckdb_config else False
            )
        db_readonly = readonly if readonly is not None else db_readonly_from_config

        # Create SDK session configuration using the shared function
        database_config, plugins_list, plugin_config, secrets_list = create_duckdb_session_config(
            site_config, user_config, profile_name, readonly=db_readonly
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
        raise RuntimeError(f"Failed to create ExecutionEngine: {e}") from e
