"""ExecutionEngine creation utilities for MXCP.

This module provides utilities for creating properly configured ExecutionEngine
instances with DuckDB and Python executors based on user and site configuration.

The ExecutionEngine provides a unified interface for executing SQL and Python code
through the SDK executor system, with full plugin support and validation.

Example usage:
    >>> from mxcp.server.executor.engine import create_runtime_environment
    >>> from mxcp.server.core.config.user_config import load_user_config
    >>> from mxcp.server.core.config.site_config import load_site_config
    >>> from mxcp.sdk.executor import ExecutionContext
    >>> from mxcp.sdk.auth import UserContext
    >>>
    >>> # Load configurations
    >>> site_config = load_site_config()
    >>> user_config = load_user_config(site_config)
    >>>
    >>> # Create runtime environment
    >>> runtime_env = create_runtime_environment(user_config, site_config, profile="development")
    >>>
    >>> # Create execution context
    >>> user_context = UserContext(provider="github", user_id="user123", username="user")
    >>> exec_context = ExecutionContext(user_context=user_context)
    >>>
    >>> # Execute SQL
    >>> result = await runtime_env.execution_engine.execute(
    ...     language="sql",
    ...     source_code="SELECT * FROM users WHERE active = $active",
    ...     params={"active": True},
    ...     context=exec_context
    ... )
    >>>
    >>> # Execute Python
    >>> result = await runtime_env.execution_engine.execute(
    ...     language="python",
    ...     source_code="return sum(numbers)",
    ...     params={"numbers": [1, 2, 3, 4, 5]},
    ...     context=exec_context
    ... )
    >>>
    >>> # Shutdown everything properly
    >>> runtime_env.shutdown()
"""

import logging
from dataclasses import dataclass
from pathlib import Path

from mxcp.sdk.duckdb import DuckDBRuntime
from mxcp.sdk.executor import ExecutionEngine
from mxcp.sdk.executor.plugins import DuckDBExecutor, PythonExecutor
from mxcp.server.core.config._types import UserConfig
from mxcp.server.core.config.models import SiteConfigModel
from mxcp.server.core.config.parsers import (
    create_duckdb_session_config,
    execution_context_for_init_hooks,
)
from mxcp.server.core.config.site_config import find_repo_root

logger = logging.getLogger(__name__)


@dataclass
class RuntimeEnvironment:
    """Container for all runtime components.

    This class manages the lifecycle of both the ExecutionEngine and
    the shared DuckDB runtime, ensuring proper shutdown order.
    """

    execution_engine: ExecutionEngine
    duckdb_runtime: DuckDBRuntime

    def shutdown(self) -> None:
        """Shutdown all components in the correct order.

        First shuts down the ExecutionEngine (which shuts down executors),
        then shuts down shared resources like the DuckDB runtime.
        """
        logger.info("Shutting down runtime environment...")

        # First shutdown engine (which shuts down executors)
        logger.info("Shutting down execution engine...")
        self.execution_engine.shutdown()

        # Then shutdown shared resources
        logger.info("Shutting down shared DuckDB runtime...")
        self.duckdb_runtime.shutdown()

        logger.info("Runtime environment shutdown complete")


def create_runtime_environment(
    user_config: UserConfig,
    site_config: SiteConfigModel,
    profile: str | None = None,
    repo_root: Path | None = None,
    readonly: bool | None = None,
) -> RuntimeEnvironment:
    """Create a RuntimeEnvironment with DuckDB and Python executors.

    This function creates a fully configured RuntimeEnvironment with:
    - An ExecutionEngine containing DuckDB and Python executors
    - A shared DuckDB runtime for connection pooling and lifecycle management

    The environment is fully initialized and ready for execution. The Python executor
    automatically handles module preloading and init hook execution during its
    initialization. Shutdown hooks are run automatically when the environment is shut down.

    Args:
        user_config: User configuration containing secrets and plugin configs by profile
        site_config: Site configuration containing database paths, extensions, and plugin definitions
        profile: Optional profile name (defaults to site_config profile)
        repo_root: Optional repository root for Python executor (defaults to current directory)
        readonly: Optional override for database readonly setting (overrides site config)

    Returns:
        RuntimeEnvironment containing ExecutionEngine and shared resources

    Raises:
        RuntimeError: If RuntimeEnvironment creation fails
        ValueError: If profile is not found in configurations

    Example:
        >>> from mxcp.server.executor.engine import create_runtime_environment
        >>> from mxcp.server.core.config.user_config import load_user_config
        >>> from mxcp.server.core.config.site_config import load_site_config
        >>>
        >>> site_config = load_site_config()
        >>> user_config = load_user_config(site_config)
        >>> runtime_env = create_runtime_environment(user_config, site_config)
        >>> engine = runtime_env.execution_engine
        >>>
        >>> # Engine is ready to use with both SQL and Python execution
        >>> # Python init hooks have already run during PythonExecutor creation
        >>> # Call runtime_env.shutdown() when done to clean up all resources
    """
    try:
        # Create ExecutionEngine
        engine = ExecutionEngine(strict=False)

        # Get the profile name to use
        profile_name = profile or site_config.profile

        # Handle readonly override
        db_readonly_from_config = False
        site_profile_config = site_config.profiles.get(profile_name)
        if site_profile_config:
            db_readonly_from_config = bool(site_profile_config.duckdb.readonly)
        else:
            db_readonly_from_config = False
        db_readonly = readonly if readonly is not None else db_readonly_from_config

        # Create SDK session configuration using the shared function
        database_config, plugins_list, plugin_config, secrets_list = create_duckdb_session_config(
            site_config, user_config, profile_name, readonly=db_readonly
        )

        # Create shared DuckDB runtime first
        duckdb_runtime = DuckDBRuntime(
            database_config=database_config,
            plugins=plugins_list,
            plugin_config=plugin_config,
            secrets=secrets_list,
        )

        # Create and register DuckDB executor with shared runtime
        duckdb_executor = DuckDBExecutor(duckdb_runtime)
        engine.register_executor(duckdb_executor)
        logger.info("Registered DuckDB executor")

        # Create and register Python executor
        if repo_root is None:
            repo_root = find_repo_root()

        # Create Python executor with execution context for init hooks
        # Init hooks need access to config and secrets
        with execution_context_for_init_hooks(
            user_config=user_config,
            site_config=site_config,
            duckdb_runtime=duckdb_runtime,
        ):
            python_executor = PythonExecutor(repo_root=repo_root)
            engine.register_executor(python_executor)
            logger.info("Registered Python executor")

        # Create RuntimeEnvironment with all components
        runtime_env = RuntimeEnvironment(execution_engine=engine, duckdb_runtime=duckdb_runtime)

        logger.info("RuntimeEnvironment created successfully with DuckDB and Python executors")
        return runtime_env

    except Exception as e:
        logger.error(f"Failed to create RuntimeEnvironment: {e}")
        raise RuntimeError(f"Failed to create RuntimeEnvironment: {e}") from e
