"""DuckDB executor plugin for SQL execution.

This plugin integrates with DuckDB to provide SQL execution with full plugin
support and lifecycle management. It creates and manages its own DuckDB session
and handles plugin loading internally.

Example usage:
    >>> from mxcp.sdk.executor import ExecutionEngine, ExecutionContext
    >>> from mxcp.sdk.executor.plugins import DuckDBExecutor
    >>>
    >>> # Create DuckDB executor (creates its own session)
    >>> executor = DuckDBExecutor()
    >>>
    >>> # Create engine and register executor
    >>> engine = ExecutionEngine()
    >>> engine.register_executor(executor)
    >>>
    >>> # Execute SQL with parameters
    >>> result = await engine.execute(
    ...     language="sql",
    ...     source_code="SELECT * FROM table WHERE id = $id",
    ...     params={"id": 123}
    ... )
    >>>
    >>> # Execute with validation
    >>> input_schema = [{"name": "limit", "type": "integer", "default": 10}]
    >>> output_schema = {"type": "array", "items": {"type": "object"}}
    >>> result = await engine.execute(
    ...     language="sql",
    ...     source_code="SELECT * FROM users LIMIT $limit",
    ...     params={"limit": 5},
    ...     input_schema=input_schema,
    ...     output_schema=output_schema
    ... )
"""

import hashlib
import logging
import threading
import time
from typing import TYPE_CHECKING, Any, Optional

import duckdb

from mxcp.sdk.telemetry import traced_operation

from ..context import ExecutionContext, reset_execution_context, set_execution_context
from ..interfaces import ExecutorPlugin

if TYPE_CHECKING:
    from .duckdb_plugin._types import (
        DatabaseConfig,
        PluginConfig,
        PluginDefinition,
        SecretDefinition,
    )
    from .duckdb_plugin.session import DuckDBSession

logger = logging.getLogger(__name__)


class DuckDBExecutor(ExecutorPlugin):
    """Executor plugin for DuckDB SQL execution.

    Creates and manages its own DuckDB session with the provided configuration.

    Example usage:
        >>> from mxcp.sdk.executor.plugins import DuckDBExecutor
        >>> from mxcp.sdk.executor.plugins.duckdb_plugin._types import (
        ...     DatabaseConfig, ExtensionDefinition, PluginDefinition,
        ...     PluginConfig, SecretDefinition
        ... )
        >>>
        >>> # Create database config
        >>> database_config = DatabaseConfig(
        ...     path="data/my_database.db",
        ...     readonly=False,
        ...     extensions=[ExtensionDefinition(name="json")]
        ... )
        >>>
        >>> # Create executor with specific config
        >>> executor = DuckDBExecutor(
        ...     database_config=database_config,
        ...     plugins=[],
        ...     plugin_config=PluginConfig(plugins_path="plugins", config={}),
        ...     secrets=[],
        ...     required_secrets=[]
        ... )
        >>>
        >>> # Execute SQL
        >>> result = await executor.execute(
        ...     "SELECT * FROM table WHERE id = $id",
        ...     {"id": 123},
        ...     context
        ... )
    """

    _session: Optional["DuckDBSession"] = None

    def __init__(
        self,
        database_config: "DatabaseConfig",
        plugins: list["PluginDefinition"],
        plugin_config: "PluginConfig",
        secrets: list["SecretDefinition"],
    ):
        """Initialize DuckDB executor.

        Creates a DuckDB session immediately with the provided configuration.

        Args:
            database_config: Database configuration including path, readonly, extensions
            plugins: List of plugin definitions to load
            plugin_config: Plugin configuration with path and config data
            secrets: List of secret definitions for injection
        """
        self.database_config = database_config
        self.plugins = plugins
        self.plugin_config = plugin_config
        self.secrets = secrets
        self._db_lock = threading.Lock()  # Internal locking for thread safety

        # Create session immediately in constructor
        try:
            from .duckdb_plugin.session import DuckDBSession

            self._session = DuckDBSession(
                database_config=self.database_config,
                plugins=self.plugins,
                plugin_config=self.plugin_config,
                secrets=self.secrets,
            )
            logger.info("DuckDB session created successfully")
        except Exception as e:
            logger.error(f"Failed to create DuckDB session: {e}")
            raise RuntimeError(f"Failed to create DuckDB session: {e}") from e

        # Log available plugins
        self._log_available_plugins()

        logger.info("DuckDB executor initialized")

    @property
    def language(self) -> str:
        """The language this executor handles."""
        return "sql"

    @property
    def session(self) -> "DuckDBSession":
        """Get the current DuckDB session."""
        if not self._session:
            raise RuntimeError("DuckDB session not initialized")
        return self._session

    def shutdown(self) -> None:
        """Clean up DuckDB executor resources."""
        logger.info("DuckDB executor shutting down")

        if self._session:
            try:
                # Shutdown DuckDB plugins first (plugins loaded into this session)
                if hasattr(self._session, "plugins") and self._session.plugins:
                    logger.info(f"Shutting down {len(self._session.plugins)} DuckDB plugins...")
                    for plugin_name, plugin in self._session.plugins.items():
                        try:
                            plugin.shutdown()
                            logger.info(f"Shut down DuckDB plugin: {plugin_name}")
                        except Exception as e:
                            logger.error(f"Error shutting down plugin {plugin_name}: {e}")

                # Now close the session
                self._session.close()
                logger.info("DuckDB session closed")
            except Exception as e:
                logger.error(f"Error closing DuckDB session: {e}")
            finally:
                self._session = None

    def validate_source(self, source_code: str) -> bool:
        """Validate SQL source code syntax.

        Args:
            source_code: SQL code to validate

        Returns:
            True if valid, False otherwise
        """
        try:
            # Try to prepare the statement to check syntax
            session = self.session
            if not session or not session.conn:
                return False

            with self._db_lock:
                conn = session.conn
                conn.execute(f"PREPARE stmt AS {source_code}")
                conn.execute("DEALLOCATE stmt")
            return True
        except Exception as e:
            logger.debug(f"SQL validation failed: {e}")
            return False

    def extract_parameters(self, source_code: str) -> list[str]:
        """Extract parameter names from SQL source code.

        Args:
            source_code: SQL code to analyze

        Returns:
            List of parameter names found in the SQL (e.g., ['id', 'name'] from "SELECT * FROM table WHERE id = $id AND name = $name")
        """
        try:
            # Use DuckDB's extract_statements to get parameter names
            statements = duckdb.extract_statements(source_code)
            if statements:
                return list(statements[0].named_parameters)
            return []
        except Exception as e:
            logger.debug(f"Parameter extraction failed: {e}")
            return []

    async def execute(
        self, source_code: str, params: dict[str, Any], context: ExecutionContext
    ) -> Any:
        """Execute SQL source code with parameters.

        Args:
            source_code: SQL query to execute
            params: Parameter values
            context: Execution context with user info for dynamic UDFs

        Returns:
            Query result as list of dictionaries
        """
        # Hash the query for privacy (similar to audit)
        query_hash = hashlib.sha256(source_code.encode()).hexdigest()[:16]

        # Extract operation type from SQL
        operation = "unknown"
        sql_lower = source_code.lower().strip()
        if sql_lower.startswith("select"):
            operation = "select"
        elif sql_lower.startswith("insert"):
            operation = "insert"
        elif sql_lower.startswith("update"):
            operation = "update"
        elif sql_lower.startswith("delete"):
            operation = "delete"
        elif sql_lower.startswith("create"):
            operation = "create"
        elif sql_lower.startswith("drop"):
            operation = "drop"

        with traced_operation(
            "mxcp.duckdb.execute",
            attributes={
                "db.system": "duckdb",
                "db.statement.hash": query_hash,
                "db.operation": operation,
                "db.parameters.count": len(params) if params else 0,
                "db.readonly": self.database_config.readonly,
            }
        ) as span:
            try:
                # Set execution context for UDFs to read dynamically
                # Set execution context for this execution
                context_token = set_execution_context(context)

                try:
                    with self._db_lock:
                        # Time the actual query execution
                        start_time = time.time()
                        result = self.session.execute_query_to_dict(source_code, params)
                        duration_ms = (time.time() - start_time) * 1000

                        # Add performance metrics to span
                        if span:
                            span.set_attribute("db.duration_ms", duration_ms)
                            if isinstance(result, list):
                                span.set_attribute("db.rows_affected", len(result))

                        return result
                finally:
                    # Always reset the context when done
                    reset_execution_context(context_token)

            except Exception as e:
                logger.error(f"SQL execution failed: {e}")
                raise RuntimeError(f"Failed to execute SQL: {e}") from e

    def _log_available_plugins(self) -> None:
        """Log information about available DuckDB plugins."""
        try:
            session = self.session
            if hasattr(session, "plugins") and session.plugins:
                plugin_names = list(session.plugins.keys())
                logger.info(f"DuckDB plugins available: {plugin_names}")
            else:
                logger.info("No DuckDB plugins available")
        except Exception as e:
            logger.warning(f"Failed to check available plugins: {e}")

    def execute_raw_sql(self, sql: str, params: dict[str, Any] | None = None) -> Any:
        """Execute raw SQL without parameter substitution.

        Args:
            sql: Raw SQL to execute
            params: Optional parameters (will be ignored)

        Returns:
            Raw query results
        """
        try:
            session = self.session
            if not session or not session.conn:
                raise RuntimeError("No DuckDB session available")

            with self._db_lock:
                # Use the same pattern as the old code: fetchdf().to_dict("records")
                # to return dictionaries instead of tuples
                from pandas import NaT

                result = session.conn.execute(sql, params)
                return result.fetchdf().replace({NaT: None}).to_dict("records")
        except Exception as e:
            logger.error(f"Raw SQL execution failed: {e}")
            raise
