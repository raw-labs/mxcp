"""
Data models and validation classes for MXCP LSP.

This module defines the core data structures used throughout the LSP implementation,
including parameter definitions and SQL validation results.
"""

from typing import Any, Optional
from dataclasses import dataclass
from lsprotocol import types
from bisect import bisect_right
from lsprotocol import types
from pygls.workspace import TextDocument


@dataclass
class Parameter:
    """
    Represents a tool parameter definition from MXCP YAML files.
    
    Parameters are extracted from the tool definition and used for:
    - Code completion suggestions
    - Parameter validation
    - Documentation generation
    
    Attributes:
        name: Parameter name (e.g., "user_id")
        type: Parameter type (e.g., "string", "integer") 
        description: Optional human-readable description
        default: Optional default value
    """
    name: str
    type: str
    description: Optional[str] = None
    default: Optional[Any] = None


class SQLErrorType:
    """
    Constants for SQL validation error types returned by DuckDB.
    
    These error types help determine the appropriate diagnostic severity
    and provide context for error handling.
    """
    
    # Syntax errors - Code cannot be parsed
    SYNTAX_ERROR = "SYNTAX_ERROR"
    PARSER_ERROR = "PARSER_ERROR"
    
    # Semantic errors - Code is syntactically valid but semantically incorrect
    SEMANTIC_ERROR = "SEMANTIC_ERROR"
    
    # Validation errors - General validation failures
    VALIDATION_ERROR = "VALIDATION_ERROR"
    
    # Unknown errors - Fallback for unrecognized error types
    UNKNOWN = "UNKNOWN"
    
    @classmethod
    def is_syntax_error(cls, error_type: str) -> bool:
        """Check if the error type is a syntax-related error."""
        return error_type in (cls.SYNTAX_ERROR, cls.PARSER_ERROR)
    
    @classmethod
    def is_semantic_error(cls, error_type: str) -> bool:
        """Check if the error type is a semantic error."""
        return error_type == cls.SEMANTIC_ERROR
    
    @classmethod
    def get_severity(cls, error_type: str) -> types.DiagnosticSeverity:
        """
        Get the appropriate diagnostic severity for an error type.
        
        Args:
            error_type: The SQL error type
            
        Returns:
            Appropriate LSP diagnostic severity
        """
        if cls.is_syntax_error(error_type):
            return types.DiagnosticSeverity.Error
        elif cls.is_semantic_error(error_type):
            return types.DiagnosticSeverity.Warning
        else:
            return types.DiagnosticSeverity.Error


class SQLValidation:
    """
    Represents the result of SQL validation performed by DuckDB.
    
    This class processes validation results from DuckDB's json_serialize_sql function
    and provides a clean interface for error handling and position tracking.
    
    The validation result contains:
    - Error status and type information
    - Error messages with precise positioning
    - Character offset to LSP position conversion
    
    Validation Workflow:
    1. SQL code is passed to DuckDB's json_serialize_sql
    2. Result is parsed into a SQLValidation object
    3. Position information is converted to LSP coordinates
    4. Error information is made available for diagnostics
    """

    def __init__(self, validation_result: dict, code: str):
        """
        Initialize SQL validation result from DuckDB output.
        
        Args:
            validation_result: Dictionary result from DuckDB's json_serialize_sql
            code: The original SQL code that was validated
            
        Expected validation_result structure:
        {
            "error": bool,
            "error_type": str,       # See SQLErrorType constants
            "error_message": str,
            "error_subtype": str,
            "position": int          # Character offset in SQL code
        }
        """
        self.code = code
        self.error = validation_result.get("error", False)
        
        if self.error:
            self.error_type = validation_result.get("error_type", SQLErrorType.UNKNOWN)
            self.error_message = validation_result.get("error_message", "Unknown SQL error")
            self.error_subtype = validation_result.get("error_subtype", "")
            self.position = int(validation_result.get("position", 0))
            
            # Convert character offset to LSP position
            self.error_position = self._offset_to_position(code, self.position)
        else:
            self.error_type = None
            self.error_message = None
            self.error_subtype = None
            self.position = 0
            self.error_position = types.Position(line=0, character=0)

    def _offset_to_position(self, code: str, offset: int) -> types.Position:
        """
        Convert a character offset to an LSP Position.
        
        This method efficiently converts a 0-based character offset into
        line and character coordinates using binary search for O(log n) performance.
        
        Args:
            code: The SQL code string
            offset: 0-based character offset into the code
            
        Returns:
            LSP Position with 0-based line and character coordinates
            
        Raises:
            ValueError: If offset is outside the valid range
            
        Example:
            For code "SELECT *\nFROM table", offset 10 points to 'F' 
            and returns Position(line=1, character=0)
        """
        if offset < 0 or offset > len(code):
            raise ValueError(f"Offset {offset} is outside code range [0, {len(code)}]")

        # Split code into lines and calculate line start positions
        lines = code.split('\n')
        line_starts = [0]
        for line in lines[:-1]:
            # +1 accounts for the newline character
            line_starts.append(line_starts[-1] + len(line) + 1)

        # Use binary search to find the line containing the offset
        line = bisect_right(line_starts, offset) - 1
        character = offset - line_starts[line]
        
        return types.Position(line=line, character=character)

    def is_error(self) -> bool:
        """Check if the validation found an error."""
        return self.error
    
    def get_diagnostic_severity(self) -> types.DiagnosticSeverity:
        """Get the appropriate diagnostic severity for this validation result."""
        if not self.is_error():
            return types.DiagnosticSeverity.Hint
        
        return SQLErrorType.get_severity(self.error_type)
    
    def __str__(self) -> str:
        """String representation for debugging."""
        if not self.is_error():
            return "SQLValidation(valid)"
        
        return (f"SQLValidation(error_type={self.error_type}, "
                f"message='{self.error_message}', "
                f"position={self.error_position})")

    def get_user_friendly_message(self) -> str:
        """
        Get a user-friendly error message for display to users.
        
        Returns:
            Human-readable error message
        """
        if not self.is_error():
            return "SQL is valid"
        
        # Map technical error types to user-friendly messages
        if SQLErrorType.is_syntax_error(self.error_type):
            return f"SQL syntax error: {self.error_message}"
        elif SQLErrorType.is_semantic_error(self.error_type):
            return f"SQL semantic error: {self.error_message}"
        else:
            return f"SQL validation error: {self.error_message}"
    
    def get_diagnostic_message(self) -> str:
        """
        Get a diagnostic message optimized for IDE display.
        
        Returns:
            Formatted diagnostic message
        """
        if not self.is_error():
            return "Valid SQL"
        
        # Create a more informative diagnostic message
        base_msg = self.error_message or "Unknown error"
        
        # Add context based on error type
        if self.error_type == SQLErrorType.SYNTAX_ERROR:
            return f"Syntax Error: {base_msg}"
        elif self.error_type == SQLErrorType.PARSER_ERROR:
            return f"Parse Error: {base_msg}"
        elif self.error_type == SQLErrorType.SEMANTIC_ERROR:
            return f"Semantic Error: {base_msg}"
        elif self.error_type == SQLErrorType.VALIDATION_ERROR:
            return f"Validation Error: {base_msg}"
        else:
            return f"SQL Error: {base_msg}" 