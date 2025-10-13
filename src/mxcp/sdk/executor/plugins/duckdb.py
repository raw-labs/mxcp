"""DuckDB executor plugin for SQL execution.

This plugin integrates with DuckDB to provide SQL execution with full plugin
support and lifecycle management. It uses a shared DuckDB runtime for connection
management.

Example usage:
    >>> from mxcp.sdk.executor import ExecutionEngine, ExecutionContext
    >>> from mxcp.sdk.executor.plugins import DuckDBExecutor
    >>> from mxcp.sdk.duckdb import DuckDBRuntime
    >>>
    >>> # Create shared runtime
    >>> runtime = DuckDBRuntime(database_config, plugins, plugin_config, secrets)
    >>>
    >>> # Create DuckDB executor with shared runtime
    >>> executor = DuckDBExecutor(runtime)
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
from typing import TYPE_CHECKING, Any

import duckdb

from mxcp.sdk.telemetry import (
    decrement_gauge,
    get_current_span,
    increment_gauge,
    record_counter,
    traced_operation,
)

from ..context import (
    ExecutionContext,
    reset_execution_context,
    set_execution_context,
)
from ..interfaces import ExecutorPlugin, ValidationResult

if TYPE_CHECKING:
    from mxcp.sdk.duckdb import DuckDBRuntime

logger = logging.getLogger(__name__)


class DuckDBExecutor(ExecutorPlugin):
    """Executor plugin for DuckDB SQL execution.

    Uses a shared DuckDB runtime for connection management.
    """

    def __init__(self, runtime: "DuckDBRuntime"):
        """Initialize the DuckDB executor with shared runtime.

        Args:
            runtime: Shared DuckDB runtime for connection management
        """
        self._runtime = runtime

        # Log available plugins
        self._log_available_plugins()

        logger.info("DuckDB executor initialized")

    @property
    def language(self) -> str:
        """The language this executor handles."""
        return "sql"

    def prepare_context(self, context: ExecutionContext) -> None:
        """Prepare the execution context with DuckDB runtime.

        This stores the runtime in the context so that runtime
        modules can access the database and plugins.
        """
        logger.debug("Preparing execution context with DuckDB runtime")
        context.set("duckdb_runtime", self._runtime)

    def shutdown(self) -> None:
        """Clean up DuckDB executor resources."""
        # Runtime is managed externally, so we don't shut it down here
        pass

    def validate_source(self, source_code: str) -> ValidationResult:
        """Validate SQL source code syntax.

        Args:
            source_code: SQL code to validate

        Returns:
            ValidationResult with is_valid flag and optional error message
        """
        try:
            # Get a connection from the pool to validate
            with self._runtime.get_connection() as session:
                #### TODO do we need that really?
                if not session.conn:
                    return ValidationResult(is_valid=False, error_message="No DuckDB session available")
                conn = session.conn
                if conn is None:
                    logger.error("No database connection available")
                    return False
                conn.execute(f"PREPARE stmt AS {source_code}")
                conn.execute("DEALLOCATE stmt")
            return ValidationResult(is_valid=True)
        except Exception as e:
            error_message = str(e)
            logger.debug(f"SQL validation failed: {error_message}")
            return ValidationResult(is_valid=False, error_message=error_message)

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

        # Track concurrent executions
        increment_gauge(
            "mxcp.duckdb.concurrent_executions",
            attributes={"operation": operation},
            description="Currently running DuckDB queries",
        )

        try:
            with traced_operation(
                "mxcp.duckdb.execute",
                attributes={
                    "db.system": "duckdb",
                    "db.statement.hash": query_hash,
                    "db.operation": operation,
                    "db.parameters.count": len(params) if params else 0,
                    "db.readonly": self._runtime.database_config.readonly,
                },
            ):
                try:
                    # Get a connection from the pool
                    with self._runtime.get_connection() as session:
                        # Set execution context for this execution, which is used for dynamic UDFs
                        context_token = set_execution_context(context)

                        try:
                            result = session.execute_query_to_dict(source_code, params)

                            # Add result metrics to current span
                            span = get_current_span()
                            if span and isinstance(result, list):
                                span.set_attribute("db.rows_affected", len(result))

                            # Record metrics
                            record_counter(
                                "mxcp.duckdb.queries_total",
                                attributes={"operation": operation, "status": "success"},
                                description="Total DuckDB queries executed",
                            )

                            return result
                        finally:
                            # Always reset the context when done
                            reset_execution_context(context_token)

                except Exception as e:
                    logger.error(f"SQL execution failed: {e}")
                    # Record failure metrics
                    record_counter(
                        "mxcp.duckdb.queries_total",
                        attributes={"operation": operation, "status": "error"},
                        description="Total DuckDB queries executed",
                    )
                    raise RuntimeError(f"Failed to execute SQL: {e}") from e
        finally:
            # Always decrement concurrent executions
            decrement_gauge(
                "mxcp.duckdb.concurrent_executions",
                attributes={"operation": operation},
                description="Currently running DuckDB queries",
            )

    def _log_available_plugins(self) -> None:
        """Log information about available DuckDB plugins."""
        try:
            if self._runtime.plugins:
                plugin_names = list(self._runtime.plugins.keys())
                logger.info(f"DuckDB plugins available: {plugin_names}")
            else:
                logger.info("No DuckDB plugins available")
        except Exception as e:
            logger.warning(f"Failed to check available plugins: {e}")
