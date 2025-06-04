import duckdb
import json
import logging
from typing import Optional, List
from lsprotocol import types
from .models import Parameter, SQLValidation
from mxcp.engine.duckdb_session import DuckDBSession

logger = logging.getLogger(__name__)


class DuckDBConnector:
    """DuckDB connector for MXCP LSP that provides SQL operations and completions."""
    
    def __init__(self, session: DuckDBSession):
        """
        Initialize DuckDB connector with a required session.
        
        Args:
            session: MXCP DuckDBSession to use (required)
            
        Raises:
            ValueError: If session is None or invalid
        """
        if not session:
            raise ValueError("DuckDBSession is required - no fallback available")
        
        if not hasattr(session, 'conn') or not session.conn:
            raise ValueError("DuckDBSession must have a valid connection")
        
        self.session = session
        logger.info("DuckDB connector initialized with session")
    
    @property
    def connection(self):
        """Get the active DuckDB connection."""
        if not self.session or not self.session.conn:
            raise RuntimeError("No active DuckDB session connection available")
        return self.session.conn

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
            
            query_result_items = []
            if result:
                query_result_items = [
                    types.CompletionItem(
                        label=row[0], 
                        kind=types.CompletionItemKind.Variable
                    )
                    for row in result
                    if row[0] is not None
                ]

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
        """Close managed by MXCP session - no action needed."""
        logger.debug("DuckDB connector close requested - managed by MXCP session") 