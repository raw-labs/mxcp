"""
Coordinate transformation utilities for MXCP LSP.

This module handles the conversion of positions between SQL code positions
and YAML document positions, accounting for indentation and YAML structure.
"""

from typing import Tuple
from lsprotocol import types


class CoordinateTransformer:
    """Utility class for transforming coordinates between SQL and YAML contexts."""
    
    @staticmethod
    def sql_to_document_position(
        sql_position: types.Position,
        code_span: Tuple[types.Position, types.Position]
    ) -> types.Position:
        """
        Transform a position from SQL code coordinates to YAML document coordinates.
        
        This method handles the coordinate transformation for SQL code embedded
        in YAML block scalars (like `code: |`), accounting for proper indentation.
        
        Args:
            sql_position: Position within the SQL code (0-based)
            code_span: Start and end positions of the SQL code block in the document
            
        Returns:
            Position adjusted to document coordinates
        """
        if not code_span:
            return sql_position
        
        # Calculate the adjusted line position
        adjusted_line = code_span[0].line + sql_position.line
        
        # Calculate the adjusted character position
        # For block scalars, all lines maintain the same base indentation
        adjusted_character = code_span[0].character + sql_position.character
        
        return types.Position(line=adjusted_line, character=adjusted_character)
    
    @staticmethod
    def document_to_sql_position(
        document_position: types.Position,
        code_span: Tuple[types.Position, types.Position]
    ) -> types.Position:
        """
        Transform a position from YAML document coordinates to SQL code coordinates.
        
        This is the inverse operation of sql_to_document_position.
        
        Args:
            document_position: Position within the YAML document (0-based)
            code_span: Start and end positions of the SQL code block in the document
            
        Returns:
            Position adjusted to SQL code coordinates
        """
        if not code_span:
            return document_position
        
        # Calculate the SQL-relative line position
        sql_line = document_position.line - code_span[0].line
        
        # Calculate the SQL-relative character position
        sql_character = document_position.character - code_span[0].character
        
        return types.Position(line=max(0, sql_line), character=max(0, sql_character))
    
    @staticmethod
    def is_position_in_code_span(
        position: types.Position,
        code_span: Tuple[types.Position, types.Position]
    ) -> bool:
        """
        Check if a position falls within the given code span.
        
        Args:
            position: Position to check
            code_span: Start and end positions of the code span
            
        Returns:
            True if position is within the span, False otherwise
        """
        if not code_span:
            return False
        
        start_pos, end_pos = code_span
        
        # Check if position is within the line range
        if position.line < start_pos.line or position.line > end_pos.line:
            return False
        
        # For single-line spans, check character position
        if start_pos.line == end_pos.line:
            return start_pos.character <= position.character <= end_pos.character
        
        # For multi-line spans
        if position.line == start_pos.line:
            return position.character >= start_pos.character
        elif position.line == end_pos.line:
            return position.character <= end_pos.character
        else:
            return True  # Position is on a middle line 