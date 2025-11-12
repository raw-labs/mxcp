"""
DuckDB session for MXCP.

This module handles DuckDB connection management and query execution.
"""

import contextlib
import logging
from collections.abc import Hashable
from pathlib import Path
from typing import Any

import duckdb
from pandas import NaT

from .extension_loader import load_extensions
from .secret_injection import inject_secrets
from .types import DatabaseConfig, SecretDefinition

logger = logging.getLogger(__name__)


def execute_query_to_dict(
    conn: duckdb.DuckDBPyConnection, query: str, params: dict[str, Any] | None = None
) -> list[dict[Hashable, Any]]:
    """
    Execute a query with parameters and return the result as a list of dictionaries.
    Replaces NaT values with None for JSON serialization.

    Args:
        conn: DuckDB connection to use
        query: SQL query to execute
        params: Query parameters (optional)

    Returns:
        List of dictionaries representing query results
    """
    return conn.execute(query, params).fetchdf().replace({NaT: None}).to_dict("records")


class DuckDBSession:
    def __init__(
        self,
        database_config: DatabaseConfig,
        secrets: list[SecretDefinition],
    ):
        self.conn: duckdb.DuckDBPyConnection | None = None
        self.database_config = database_config
        self.secrets = secrets
        self._initialized = False  # Track whether session has been fully initialized

        # Connect automatically on construction
        self._connect()

    def __enter__(self) -> "DuckDBSession":
        """Context manager entry"""
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Context manager exit - ensure connection is closed"""
        self.close()

    def __del__(self) -> None:
        """Destructor - ensure connection is closed if object is garbage collected"""
        with contextlib.suppress(Exception):
            self.close()

    def _connect(self) -> None:
        """Connect to DuckDB database"""
        db_path = self.database_config.path

        logger.debug(f"Connecting to DuckDB at: {db_path}")

        # Ensure parent directory exists for database file
        db_file = Path(db_path)
        db_dir = db_file.parent
        if not db_dir.exists():
            logger.info(f"Creating directory {db_dir} for database file")
            db_dir.mkdir(parents=True, exist_ok=True)

        # Handle read-only mode when database file doesn't exist
        if self.database_config.readonly and not db_file.exists():
            logger.info(
                f"Database file {db_path} doesn't exist. Creating it first before opening in read-only mode."
            )
            # Create the database file first
            temp_conn = duckdb.connect(str(db_path))
            temp_conn.close()
            logger.info(f"Created database file {db_path}")

        # Open connection with readonly flag if specified
        if self.database_config.readonly:
            self.conn = duckdb.connect(str(db_path), read_only=True)
            logger.info("Opened DuckDB connection in read-only mode")
        else:
            self.conn = duckdb.connect(str(db_path))

        # Load DuckDB extensions from config
        load_extensions(self.conn, self.database_config.extensions)

        # Inject secrets
        inject_secrets(self.conn, self.secrets)

        # Create user token UDFs that call get_user_context() dynamically
        self._create_user_token_udfs()

        # Mark as initialized
        self._initialized = True

    def _create_user_token_udfs(self) -> None:
        """Create UDFs for accessing user tokens that dynamically read from context."""
        logger.info("Creating user token UDFs")

        def get_user_external_token() -> str:
            """Return the current user's OAuth provider token (e.g., GitHub token)."""
            # Get the execution context dynamically when the function is called
            from mxcp.sdk.executor.context import get_execution_context

            context = get_execution_context()
            if context and context.external_token:
                return context.external_token
            return ""

        def get_username() -> str:
            """Return the current user's username."""
            # Get the execution context dynamically when the function is called
            from mxcp.sdk.executor.context import get_execution_context

            context = get_execution_context()
            if context and context.username:
                return context.username
            return ""

        def get_user_provider() -> str:
            """Return the current user's OAuth provider (e.g., 'github', 'atlassian')."""
            # Get the execution context dynamically when the function is called
            from mxcp.sdk.executor.context import get_execution_context

            context = get_execution_context()
            if context and context.provider:
                return context.provider
            return ""

        def get_user_email() -> str:
            """Return the current user's email address."""
            # Get the execution context dynamically when the function is called
            from mxcp.sdk.executor.context import get_execution_context

            context = get_execution_context()
            if context and context.email:
                return context.email
            return ""

        # Register the UDFs with DuckDB
        if self.conn:
            # Try to create each UDF, ignore if already exists
            # UDFs are per database, so another connection may have already created them
            udfs = [
                ("get_user_external_token", get_user_external_token),
                ("get_username", get_username),
                ("get_user_provider", get_user_provider),
                ("get_user_email", get_user_email),
            ]

            created_udfs = []
            for name, func in udfs:
                try:
                    self.conn.create_function(name, func, [], None)
                    created_udfs.append(name)
                except duckdb.CatalogException as e:
                    if "already exists" in str(e):
                        logger.debug(f"UDF {name} already exists, skipping creation")
                    else:
                        raise

            if created_udfs:
                logger.info(f"Created user token UDFs: {', '.join(created_udfs)}")
            else:
                logger.debug("All user token UDFs already exist")

    def close(self) -> None:
        """Close the DuckDB connection"""
        if self.conn:
            try:
                self.conn.close()
                logger.debug("DuckDB connection closed")
            except Exception as e:
                logger.error(f"Error closing DuckDB connection: {e}")
            finally:
                self.conn = None

    def execute_query_to_dict(
        self, query: str, params: dict[str, Any] | None = None
    ) -> list[dict[Hashable, Any]]:
        """Execute a query and return results as a list of dictionaries.

        Args:
            query: SQL query to execute
            params: Optional parameters for the query

        Returns:
            List of result rows as dictionaries
        """
        if not self.conn:
            raise RuntimeError("Database connection not initialized")

        return execute_query_to_dict(self.conn, query, params)
