import duckdb
import json
import logging
from typing import Optional, List
from lsprotocol import types
from .models import Parameter, SQLValidation
from mxcp.engine.duckdb_session import DuckDBSession

logger = logging.getLogger(__name__)


class DuckDBConnector:
    """DuckDB connector adapted for MXCP LSP that uses existing DuckDBSession."""
    
    def __init__(self, session: Optional[DuckDBSession] = None, db_path: str = ":memory:"):
        """
        Initialize DuckDB connector.
        
        Args:
            session: Existing MXCP DuckDBSession to use, or None to create new connection
            db_path: Database path for fallback connection if session is None
        """
        self.session = session
        self.__fallback_connection = None
        
        if not session:
            logger.info(f"Creating fallback DuckDB connection to {db_path}")
            self.__fallback_connection = duckdb.connect(database=db_path)
    
    @property
    def connection(self):
        """Get the active DuckDB connection."""
        if self.session and self.session.conn:
            return self.session.conn
        elif self.__fallback_connection:
            return self.__fallback_connection
        else:
            raise RuntimeError("No DuckDB connection available")

    def execute_query(self, query: str):
        """Execute a query and return results."""
        try:
            return self.connection.execute(query).fetchall()
        except Exception as e:
            logger.error(f"Error executing query: {e}")
            return []

    def get_completions(self, code: str, parameters: Optional[List[Parameter]] = None) -> types.CompletionList:
        """Get SQL completions for the given code."""
        try:
            # Use DuckDB's sql_auto_complete function
            result = self.execute_query(f'SELECT * FROM sql_auto_complete("{code}");')
            
            if result:
                query_result_items = [
                    types.CompletionItem(
                        label=row[0], 
                        kind=types.CompletionItemKind.Variable
                    )
                    for row in result
                    if row[0] is not None
                ]
            else:
                query_result_items = []

            # Add parameters as completion items if provided
            parameter_items = []
            if parameters:
                parameter_items = [
                    types.CompletionItem(
                        label=param.name,
                        kind=types.CompletionItemKind.Variable,
                        detail=param.description or "",
                    )
                    for param in parameters
                ]
            
            items = query_result_items + parameter_items
            return types.CompletionList(items=items, is_incomplete=False)
            
        except Exception as e:
            logger.error(f"Error getting completions: {e}")
            return types.CompletionList(items=[], is_incomplete=False)

    def get_tokens(self, code: str):
        """Get tokens for the given SQL code."""
        try:
            return duckdb.tokenize(code)
        except Exception as e:
            logger.error(f"Error tokenizing code: {e}")
            return []
    
    def validate_sql(self, code: str) -> SQLValidation:
        """Validate SQL code and return validation result."""
        try:
            # Escape single quotes in the code
            escaped_code = code.replace("'", "''")
            result_json = self.connection.execute(
                f"SELECT json_serialize_sql('{escaped_code}')"
            ).fetchone()[0]
            result = json.loads(result_json)
            return SQLValidation(result, code)
        except Exception as e:
            logger.error(f"Error validating SQL: {e}")
            # Return a validation result indicating error
            error_result = {
                "error": True,
                "error_type": "VALIDATION_ERROR",
                "error_message": str(e),
                "error_subtype": "UNKNOWN",
                "position": 0
            }
            return SQLValidation(error_result, code)

    def close(self):
        """Close the DuckDB connection."""
        if self.__fallback_connection:
            self.__fallback_connection.close()
            logger.info("Closed fallback DuckDB connection")
        # Don't close the session connection as it's managed by MXCP 