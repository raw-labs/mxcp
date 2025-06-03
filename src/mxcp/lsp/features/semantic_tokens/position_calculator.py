"""Position calculation utilities for semantic tokens."""

import operator
from functools import reduce
from typing import List, Tuple, Optional

from lsprotocol.types import Position
from .semantic_tokens_classifier import Token
from mxcp.lsp.utils.duckdb_connector import DuckDBConnector


class PositionCalculator:
    """Calculates relative positions for semantic tokens."""
    
    def __init__(self, duck_db_connector: DuckDBConnector):
        """Initialize with DuckDB connector for token processing."""
        self._duck_db_connector = duck_db_connector

    def calculate_relative_positions(
        self, 
        tokens: List[Token], 
        code_span: Optional[Tuple[Position, Position]]
    ) -> List[int]:
        """
        Calculate relative positions for tokens in LSP semantic tokens format.
        
        Args:
            tokens: List of tokens to process
            code_span: Optional span indicating the code section position in the file
            
        Returns:
            List of integers in LSP semantic tokens format:
            [line, offset, length, token_type, token_modifiers, ...]
        """
        if not tokens:
            return []
        
        if code_span is None:
            return []
        
        code_start_line = code_span[0].line
        code_start_col = code_span[0].character
        
        data = []
        prev_line = 0
        prev_offset = 0
        
        for token in tokens:
            # Calculate absolute line and offset - exactly as in original
            abs_line = token.line + code_start_line
            abs_offset = token.offset + (code_start_col if token.line == 0 else 0)

            # Calculate relative line - exactly as in original
            rel_line = abs_line - prev_line

            if rel_line == 0:
                rel_offset = abs_offset - prev_offset
            else:
                rel_offset = code_start_col + token.offset  # Original logic

            # Update tracking variables
            prev_line = abs_line
            prev_offset = abs_offset
            
            token_data = self._create_token_data(token, rel_line, rel_offset)
            data.extend(token_data)
        
        return data
    
    def _create_token_data(self, token: Token, rel_line: int, rel_offset: int) -> List[int]:
        """Create the 5-element data array for a token."""
        # Import here to avoid circular imports
        from .token_processor import TokenProcessor
        
        processor = TokenProcessor(self._duck_db_connector)
        token_type_idx = processor.get_token_type_index(token)
        token_modifiers = reduce(operator.or_, token.tok_modifiers, 0)
        
        return [
            rel_line,
            rel_offset,
            len(token.text.strip()),
            token_type_idx,
            token_modifiers,
        ] 