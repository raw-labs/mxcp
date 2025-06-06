"""
DuckDB connector for MXCP LSP with enhanced resource management.

This module provides a safe interface to DuckDB operations for the LSP server,
including SQL completions, validation, and tokenization with proper resource management.
"""

import duckdb
import json
import logging
from typing import Optional, List, Any, Generator
from contextlib import contextmanager
from lsprotocol import types
from .models import Parameter, SQLValidation, SQLErrorType
from mxcp.engine.duckdb_session import DuckDBSession

logger = logging.getLogger(__name__)


class DuckDBConnectionError(Exception):
    """Raised when DuckDB connection operations fail."""
    pass


class DuckDBConnector:
    """
    DuckDB connector for MXCP LSP that provides SQL operations and completions.
    
    This connector provides a safe interface to DuckDB operations with:
    - Context managers for resource safety
    - Comprehensive error handling
    - Connection validation
    - Resource cleanup on errors
    """
    
    def __init__(self, session: DuckDBSession):
        """
        Initialize DuckDB connector with a required session.
        
        Args:
            session: MXCP DuckDBSession to use (required)
            
        Raises:
            ValueError: If session is None or invalid
            DuckDBConnectionError: If session connection is invalid
        """
        if not session:
            raise ValueError("DuckDBSession is required - no fallback available")
        
        if not hasattr(session, 'conn'):
            raise ValueError("DuckDBSession must have a 'conn' attribute")
            
        if not session.conn:
            raise DuckDBConnectionError("DuckDBSession must have a valid connection")
        
        self.session = session
        self._connection_validated = False
        self._validate_connection()
        logger.info("DuckDB connector initialized with session")
    
    def _validate_connection(self) -> None:
        """
        Validate the DuckDB connection is working.
        
        Raises:
            DuckDBConnectionError: If connection validation fails
        """
        try:
            # Test connection with a simple query
            with self._get_connection() as conn:
                conn.execute("SELECT 1").fetchone()
            self._connection_validated = True
            logger.debug("DuckDB connection validated successfully")
            
        except Exception as e:
            raise DuckDBConnectionError(f"DuckDB connection validation failed: {e}")

    @contextmanager
    def _get_connection(self) -> Generator[Any, None, None]:
        """
        Get a DuckDB connection with proper resource management.
        
        This context manager ensures that any connection issues are properly
        handled and logged, and provides a safe way to execute operations.
        
        Yields:
            DuckDB connection object
            
        Raises:
            DuckDBConnectionError: If connection is not available
        """
        if not self.session or not self.session.conn:
            raise DuckDBConnectionError("No active DuckDB session connection available")
        
        try:
            yield self.session.conn
        except Exception as e:
            logger.error(f"Error during DuckDB operation: {e}")
            raise

    @property
    def connection(self):
        """
        Get the active DuckDB connection.
        
        Returns:
            DuckDB connection object
            
        Raises:
            DuckDBConnectionError: If connection is not available
        """
        if not self.session or not self.session.conn:
            raise DuckDBConnectionError("No active DuckDB session connection available")
        return self.session.conn

    def execute_query(self, query: str, parameters: Optional[List] = None) -> List[Any]:
        """
        Execute a query and return results with proper error handling.
        
        Args:
            query: SQL query to execute
            parameters: Optional query parameters
            
        Returns:
            List of result rows, empty list on error
        """
        if not query or not isinstance(query, str):
            logger.warning("Invalid query provided to execute_query")
            return []
            
        try:
            with self._get_connection() as conn:
                if parameters:
                    result = conn.execute(query, parameters)
                else:
                    result = conn.execute(query)
                return result.fetchall()
                
        except duckdb.Error as e:
            logger.error(f"DuckDB error executing query '{query[:50]}...': {e}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error executing query '{query[:50]}...': {e}")
            return []

    def get_completions(self, code: str, parameters: Optional[List[Parameter]] = None) -> types.CompletionList:
        """
        Get SQL completions for the given code with enhanced error handling.
        
        Args:
            code: SQL code to get completions for
            parameters: Optional parameters to include in completions
            
        Returns:
            CompletionList with available completions
        """
        if not code or not isinstance(code, str):
            logger.warning("Invalid code provided for completions")
            return types.CompletionList(items=[], is_incomplete=False)
            
        try:
            # Sanitize the code for the completion query
            # Escape double quotes to prevent SQL injection
            escaped_code = code.replace('"', '""')
            
            # Use DuckDB's sql_auto_complete function with proper escaping
            completion_query = f'SELECT * FROM sql_auto_complete("{escaped_code}");'
            result = self.execute_query(completion_query)
            
            query_result_items = []
            if result:
                query_result_items = [
                    types.CompletionItem(
                        label=str(row[0]), 
                        kind=types.CompletionItemKind.Variable,
                        detail="SQL completion"
                    )
                    for row in result
                    if row and row[0] is not None and str(row[0]).strip()
                ]

            # Add parameters as completion items if provided
            parameter_items = []
            if parameters:
                parameter_items = [
                    types.CompletionItem(
                        label=param.name,
                        kind=types.CompletionItemKind.Variable,
                        detail=param.description or f"Parameter ({param.type})",
                        documentation=f"Type: {param.type}"
                    )
                    for param in parameters
                    if param.name and isinstance(param.name, str)
                ]
            
            all_items = query_result_items + parameter_items
            logger.debug(f"Generated {len(all_items)} completion items")
            
            return types.CompletionList(items=all_items, is_incomplete=False)
            
        except Exception as e:
            logger.error(f"Error getting completions for code '{code[:50]}...': {e}")
            return types.CompletionList(items=[], is_incomplete=False)

    def get_tokens(self, code: str) -> List[Any]:
        """
        Get tokens for the given SQL code with proper error handling.
        
        Args:
            code: SQL code to tokenize
            
        Returns:
            List of tokens, empty list on error
        """
        if not code or not isinstance(code, str):
            logger.warning("Invalid code provided for tokenization")
            return []
            
        try:
            # Use DuckDB's tokenize function
            tokens = duckdb.tokenize(code)
            logger.debug(f"Tokenized code into {len(tokens)} tokens")
            return tokens
            
        except duckdb.Error as e:
            logger.error(f"DuckDB error tokenizing code '{code[:50]}...': {e}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error tokenizing code '{code[:50]}...': {e}")
            return []
    
    def validate_sql(self, code: str) -> SQLValidation:
        """
        Validate SQL code and return validation result with enhanced error handling.
        
        Args:
            code: SQL code to validate
            
        Returns:
            SQLValidation object with results
        """
        if not code or not isinstance(code, str):
            logger.warning("Invalid code provided for validation")
            return self._create_error_validation("Invalid input", code)
            
        try:
            with self._get_connection() as conn:
                # Escape single quotes properly for SQL string literal
                escaped_code = code.replace("'", "''")
                
                # Use DuckDB's json_serialize_sql function
                validation_query = f"SELECT json_serialize_sql('{escaped_code}')"
                result = conn.execute(validation_query).fetchone()
                
                if not result or not result[0]:
                    return self._create_error_validation("No validation result", code)
                
                validation_data = json.loads(result[0])
                return SQLValidation(validation_data, code)
                
        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error during SQL validation: {e}")
            return self._create_error_validation(f"Validation result parsing error: {e}", code)
            
        except duckdb.Error as e:
            logger.error(f"DuckDB error validating SQL '{code[:50]}...': {e}")
            return self._create_error_validation(f"SQL validation error: {e}", code)
            
        except Exception as e:
            logger.error(f"Unexpected error validating SQL '{code[:50]}...': {e}")
            return self._create_error_validation(f"Validation error: {e}", code)

    def _create_error_validation(self, error_message: str, code: str) -> SQLValidation:
        """
        Create an error validation result.
        
        Args:
            error_message: Error message to include
            code: Original code that failed validation
            
        Returns:
            SQLValidation object indicating error
        """
        error_result = {
            "error": True,
            "error_type": SQLErrorType.VALIDATION_ERROR,
            "error_message": error_message,
            "error_subtype": "CONNECTOR_ERROR",
            "position": 0
        }
        return SQLValidation(error_result, code)

    def test_connection(self) -> bool:
        """
        Test if the DuckDB connection is working.
        
        Returns:
            True if connection is working, False otherwise
        """
        try:
            with self._get_connection() as conn:
                conn.execute("SELECT 1").fetchone()
            return True
        except Exception as e:
            logger.error(f"Connection test failed: {e}")
            return False

    def get_connection_info(self) -> dict:
        """
        Get information about the current connection.
        
        Returns:
            Dictionary with connection information
        """
        info = {
            "has_session": self.session is not None,
            "has_connection": False,
            "connection_validated": self._connection_validated,
            "connection_working": False
        }
        
        if self.session and hasattr(self.session, 'conn') and self.session.conn:
            info["has_connection"] = True
            info["connection_working"] = self.test_connection()
        
        return info

    def close(self):
        """
        Close the connector and clean up resources.
        
        Note: The actual DuckDB connection is managed by the MXCP session
        and should not be closed here.
        """
        logger.debug("DuckDB connector close requested - managed by MXCP session")
        self._connection_validated = False 