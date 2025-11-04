"""
DuckDB runtime infrastructure.

This module provides the shared DuckDB runtime that manages connection pooling
and database lifecycle independently of executors.
"""

import logging
import os
import queue
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from .session import DuckDBSession
from .types import DatabaseConfig, PluginConfig, PluginDefinition, SecretDefinition

logger = logging.getLogger(__name__)


class DuckDBRuntime:
    """Shared DuckDB runtime infrastructure.

    This class manages a pool of DuckDB connections that can be shared across
    multiple components. It's designed to be created once at application startup
    and passed to executors and other components that need database access.

    Important: This does NOT support :memory: databases. Only file-based databases
    are supported to ensure consistency and proper resource management.
    """

    def __init__(
        self,
        database_config: DatabaseConfig,
        plugins: list[PluginDefinition],
        plugin_config: PluginConfig,
        secrets: list[SecretDefinition],
        pool_size: int | None = None,
    ):
        """Initialize the DuckDB runtime.

        Args:
            database_config: Database configuration
            plugins: Plugin definitions
            plugin_config: Plugin configuration
            secrets: Secret definitions
            pool_size: Number of connections in pool (defaults to 2 * CPU count)

        Raises:
            ValueError: If :memory: database is specified
        """
        # Forbid :memory: databases
        if database_config.path == ":memory:":
            raise ValueError(
                "In-memory databases (:memory:) are not supported. "
                "Please use a file-based database."
            )

        self.database_config = database_config
        self.plugins_list = plugins
        self.plugin_config = plugin_config
        self.secrets = secrets

        # Determine pool size
        if pool_size is None:
            cpu_count = os.cpu_count() or 5  # Default to 5 if cpu_count returns None
            pool_size = max(10, cpu_count * 2)
        self.pool_size = pool_size

        # Create the connection pool
        self._pool: queue.Queue[DuckDBSession] = queue.Queue(maxsize=pool_size)
        self._active_sessions: set[DuckDBSession] = set()
        self._shutdown = False
        self._lock = threading.Lock()

        # Pre-create all connections
        logger.debug(f"Creating DuckDB runtime with {pool_size} connections...")
        logger.debug(f"Database path: {database_config.path}")

        # Store first session to get plugin info
        first_session = None

        for i in range(pool_size):
            session = DuckDBSession(
                database_config=self.database_config,
                plugins=(
                    self.plugins_list if i == 0 else []
                ),  # Only first session registers plugin UDFs
                plugin_config=self.plugin_config,
                secrets=self.secrets,
            )
            if i == 0:
                first_session = session
            self._pool.put(session)
            logger.debug(f"Created connection {i+1}/{pool_size}")

        # Store plugins reference for easy access
        self._plugins: dict[str, Any] = {}
        if first_session and first_session.plugins:
            self._plugins = first_session.plugins
            plugin_names = list(first_session.plugins.keys())
            logger.info(f"DuckDB plugins available: {plugin_names}")
        else:
            logger.info("No DuckDB plugins available")

        logger.info("DuckDB runtime initialized")

    @property
    def plugins(self) -> dict[str, Any]:
        """Get the plugins dictionary."""
        return self._plugins or {}

    @contextmanager
    def get_connection(self) -> Iterator[DuckDBSession]:
        """Get a connection from the pool.

        This is a context manager that ensures the connection is
        always returned to the pool, even if an exception occurs.

        Yields:
            DuckDBSession: A database session from the pool

        Raises:
            RuntimeError: If runtime is shutting down
        """
        if self._shutdown:
            raise RuntimeError("DuckDB runtime is shutting down")

        # Get a connection from the pool (blocks if none available)
        session = self._pool.get()

        # Track active session
        with self._lock:
            self._active_sessions.add(session)

        try:
            yield session
        finally:
            # Return to pool and remove from active set
            with self._lock:
                self._active_sessions.discard(session)
            self._pool.put(session)

    def shutdown(self) -> None:
        """Shutdown all connections in the runtime.

        This method uses a two-phase approach to ensure thread safety:
        1. Set shutdown flag to prevent new connection requests
        2. Acquire all connections from the pool, which guarantees:
           - No thread is blocked waiting for a connection
           - No thread has an active connection
           - No thread can start new work
        """
        logger.info("Shutting down DuckDB runtime...")

        # Phase 1: Mark as shutting down to prevent new connections
        self._shutdown = True

        # Phase 2: Acquire all connections from the pool with timeout
        # This ensures no thread can be using a connection or blocked waiting for one
        timeout = 5.0  # 5 second timeout
        start_time = time.time()
        acquired_sessions: list[DuckDBSession] = []

        logger.debug(f"Acquiring all {self.pool_size} connections from pool...")

        for i in range(self.pool_size):
            try:
                # Try to get a connection with timeout
                remaining = timeout - (time.time() - start_time)
                if remaining <= 0:
                    logger.warning(
                        f"Timeout acquiring connection {i+1}/{self.pool_size}. "
                        f"Got {len(acquired_sessions)} connections, "
                        f"{len(self._active_sessions)} still active."
                    )
                    break

                session = self._pool.get(timeout=remaining)
                acquired_sessions.append(session)
                logger.debug(f"Acquired connection {i+1}/{self.pool_size}")

            except queue.Empty:
                logger.warning(
                    f"Could not acquire connection {i+1}/{self.pool_size} - pool empty. "
                    f"Got {len(acquired_sessions)} connections."
                )
                break

        # At this point, we have all available connections
        # Any connections not acquired are still in use despite timeout
        logger.info(f"Acquired {len(acquired_sessions)}/{self.pool_size} connections")

        # Shutdown plugins first (only need to do this once)
        if self._plugins:
            for plugin_name, plugin in self._plugins.items():
                try:
                    plugin.shutdown()
                    logger.info(f"Shut down DuckDB plugin: {plugin_name}")
                except Exception as e:
                    logger.error(f"Error shutting down plugin {plugin_name}: {e}")

        # Close all acquired sessions
        closed_count = 0
        for session in acquired_sessions:
            try:
                session.close()
                closed_count += 1
                logger.debug(f"Closed DuckDB connection {closed_count}")
            except Exception as e:
                logger.error(f"Error closing DuckDB session: {e}")

        logger.info(f"DuckDB runtime shutdown complete (closed {closed_count} connections)")

    @property
    def is_shutdown(self) -> bool:
        """Check if the runtime is shut down."""
        return self._shutdown
