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
    >>> # Initialize with context (executor creates session from config)
    >>> context = ExecutionContext(
    ...     user_config=user_config,
    ...     site_config=site_config,
    ...     user_context=user_context
    ... )
    >>> engine.startup(context)
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

import logging
import duckdb
import threading
from typing import Dict, Any, Optional, List, TYPE_CHECKING

from ..interfaces import ExecutorPlugin
from ..context import ExecutionContext

if TYPE_CHECKING:
    from .duckdb_plugin.session import DuckDBSession
    from .duckdb_plugin.types import (
        DatabaseConfig, PluginDefinition, PluginConfig, SecretDefinition
    )

logger = logging.getLogger(__name__)


class DuckDBExecutor(ExecutorPlugin):
    """Executor plugin for DuckDB SQL execution.
    
    Creates and manages its own DuckDB session with the provided configuration.
    
    Example usage:
        >>> from mxcp.sdk.executor.plugins import DuckDBExecutor
        >>> from mxcp.sdk.executor.plugins.duckdb_plugin.types import (
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
    
    def __init__(
        self,
        database_config: 'DatabaseConfig',
        plugins: List['PluginDefinition'],
        plugin_config: 'PluginConfig', 
        secrets: List['SecretDefinition']
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
                secrets=self.secrets
            )
            logger.info("DuckDB session created successfully")
        except Exception as e:
            logger.error(f"Failed to create DuckDB session: {e}")
            raise RuntimeError(f"Failed to create DuckDB session: {e}")
        
        # Log available plugins
        self._log_available_plugins()
        
        logger.info("DuckDB executor initialized")

    @property
    def language(self) -> str:
        """The language this executor handles."""
        return "sql"
    
    @property
    def session(self) -> 'DuckDBSession':
        """Get the current DuckDB session."""
        if not self._session:
            raise RuntimeError("DuckDB session not initialized")
        return self._session

    def shutdown(self) -> None:
        """Clean up DuckDB executor resources."""
        logger.info("DuckDB executor shutting down")
        
        if self._session:
            try:
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
    
    async def execute(
        self,
        source_code: str,
        params: Dict[str, Any],
        context: ExecutionContext
    ) -> Any:
        """Execute SQL source code with parameters.
        
        Args:
            source_code: SQL query to execute
            params: Parameter values
            context: Execution context with user info for dynamic UDFs
            
        Returns:
            Query result as list of dictionaries
        """
        try:
            # Set execution context for UDFs to read dynamically
            from ..context import set_execution_context, reset_execution_context
            
            # Set execution context for this execution
            context_token = set_execution_context(context)
            
            try:
                with self._db_lock:
                    # Execute the query - UDFs will read from context dynamically
                    return self.session.execute_query_to_dict(source_code, params)
            finally:
                # Always reset the context when done
                reset_execution_context(context_token)
                    
        except Exception as e:
            logger.error(f"SQL execution failed: {e}")
            raise RuntimeError(f"Failed to execute SQL: {e}")
    
    def _log_available_plugins(self) -> None:
        """Log information about available DuckDB plugins."""
        try:
            session = self.session
            if hasattr(session, 'plugins') and session.plugins:
                plugin_names = list(session.plugins.keys())
                logger.info(f"DuckDB plugins available: {plugin_names}")
            else:
                logger.info("No DuckDB plugins available")
        except Exception as e:
            logger.warning(f"Failed to check available plugins: {e}")
    
    def execute_raw_sql(self, sql: str, params: Optional[Dict[str, Any]] = None) -> Any:
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