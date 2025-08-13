"""ExecutionContext utilities for MXCP configuration.

This module provides utilities for managing ExecutionContext during
initialization and configuration phases, particularly for init hooks.
"""

import logging
from collections.abc import Generator
from contextlib import contextmanager
from typing import Any

from mxcp.core.config._types import SiteConfig, UserConfig
from mxcp.sdk.executor import (
    ExecutionContext,
    reset_execution_context,
    set_execution_context,
)
from mxcp.sdk.executor.plugins.duckdb_plugin.session import DuckDBSession

logger = logging.getLogger(__name__)


@contextmanager
def execution_context_for_init_hooks(
    user_config: UserConfig | None = None,
    site_config: SiteConfig | None = None,
    duckdb_session: DuckDBSession | None = None,
    plugins: dict[str, Any] | None = None,
) -> Generator[ExecutionContext | None, None, None]:
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
