"""DuckDB executor plugin for SQL execution.

This plugin integrates with DuckDB to provide SQL execution with full plugin
support and lifecycle management. It creates and manages its own DuckDB session
and handles plugin loading internally.

Example usage:
    >>> from mxcp.executor import ExecutionEngine, ExecutionContext
    >>> from mxcp.executor.plugins import DuckDBExecutor
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
from typing import Dict, Any, Optional, TYPE_CHECKING

from ..interfaces import ExecutorPlugin, ExecutionContext

if TYPE_CHECKING:
    from .duckdb_plugin.session import DuckDBSession

logger = logging.getLogger(__name__)


class DuckDBExecutor(ExecutorPlugin):
    """Executor plugin for DuckDB SQL execution.
    
    Creates and manages its own DuckDB session and handles plugin loading
    internally based on the provided configuration context.
    
    Example usage:
        >>> from mxcp.executor.plugins import DuckDBExecutor
        >>> from mxcp.executor import ExecutionContext
        >>> 
        >>> # Create executor
        >>> executor = DuckDBExecutor()
        >>> 
        >>> # Initialize with context (creates session from config)
        >>> context = ExecutionContext(
        ...     user_config=user_config,
        ...     site_config=site_config,
        ...     user_context=user_context
        ... )
        >>> executor.startup(context)
        >>> 
        >>> # Execute SQL
        >>> result = await executor.execute(
        ...     "SELECT * FROM table WHERE id = $id",
        ...     {"id": 123},
        ...     context
        ... )
        >>> 
        >>> # Execute raw SQL (bypasses parameter substitution)
        >>> result = executor.execute_raw_sql("SHOW TABLES")
        >>> 
        >>> # Validate SQL syntax
        >>> is_valid = executor.validate_source("SELECT 1")
    """
    
    def __init__(self, profile: Optional[str] = None, readonly: Optional[bool] = None):
        """Initialize DuckDB executor.
        
        Args:
            profile: Optional profile name override
            readonly: Optional readonly mode override
        """
        self.profile = profile
        self.readonly = readonly
        self._session: Optional['DuckDBSession'] = None
        self._context: Optional[ExecutionContext] = None
        self._db_lock = threading.Lock()  # Internal locking for thread safety
    
    @property
    def language(self) -> str:
        """The language this executor handles."""
        return "sql"
    
    @property
    def session(self) -> 'DuckDBSession':
        """Get the current DuckDB session."""
        if not self._session:
            raise RuntimeError("DuckDB session not initialized - call startup() first")
        return self._session
    
    def startup(self, context: ExecutionContext) -> None:
        """Initialize the DuckDB executor.
        
        Creates a DuckDB session using the provided configuration context
        and loads plugins.
        
        Args:
            context: Runtime context with configuration
        """
        self._context = context
        
        if not context.user_config or not context.site_config:
            raise RuntimeError("DuckDB executor requires user_config and site_config")
        
        # Create DuckDB session using config
        try:
            from .duckdb_plugin.session import DuckDBSession
            self._session = DuckDBSession(
                user_config=context.user_config,
                site_config=context.site_config,
                profile=self.profile,
                readonly=self.readonly
            )
            logger.info("DuckDB session created successfully")
        except Exception as e:
            logger.error(f"Failed to create DuckDB session: {e}")
            raise RuntimeError(f"Failed to create DuckDB session: {e}")
        
        # Log available plugins
        self._log_available_plugins()
        
        logger.info("DuckDB executor initialized")
    
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
        
        self._context = None
    
    def reload(self, context: ExecutionContext) -> None:
        """Reload DuckDB executor with new context.
        
        Args:
            context: New runtime context
        """
        logger.info("Reloading DuckDB executor")
        
        # Shutdown existing session
        self.shutdown()
        
        # Startup with new context
        self.startup(context)
        
        logger.info("DuckDB executor reloaded")
    
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
            source_code: SQL code to execute
            params: Parameter values for SQL placeholders
            context: Runtime context
            
        Returns:
            Query results as list of dictionaries
        """
        try:
            # Execute using the session's execute_query_to_dict method with locking
            with self._db_lock:
                result = self.session.execute_query_to_dict(source_code, params)
            return result
                
        except Exception as e:
            logger.error(f"DuckDB execution failed: {e}")
            raise
    
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
                result = session.conn.execute(sql)
                if hasattr(result, 'fetchall'):
                    return result.fetchall()
                return result
        except Exception as e:
            logger.error(f"Raw SQL execution failed: {e}")
            raise 