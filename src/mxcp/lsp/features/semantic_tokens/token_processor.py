"""Unified token processing logic for semantic tokens."""

import logging
from typing import List, Tuple, Any

from .semantic_tokens_classifier import Token
from .semantic_tokens_config import SemanticTokensConfig
from mxcp.lsp.utils.duckdb_connector import DuckDBConnector


logger = logging.getLogger(__name__)


class TokenProcessor:
    """Unified token processing - extraction, type resolution, and enhancement."""

    def __init__(
        self, duck_db_connector: DuckDBConnector, config: SemanticTokensConfig = None
    ):
        """Initialize with DuckDB connector and optional configuration."""
        self._duck_db_connector = duck_db_connector
        self._config = config or SemanticTokensConfig()

    def process_code(self, code: str) -> List[Token]:
        """
        Process code and return fully-resolved tokens.

        Args:
            code: The source code to process

        Returns:
            List of processed tokens with resolved types
        """
        if not code:
            logger.debug("Empty code provided, returning empty token list")
            return []

        try:
            # Extract raw tokens from DuckDB
            duck_tokens = self._duck_db_connector.get_tokens(code)
            if not duck_tokens:
                logger.debug("No tokens returned from DuckDB")
                return []

            # Convert to Token objects with enhanced type resolution
            return self._process_duck_tokens(duck_tokens, code)

        except Exception as e:
            logger.error(f"Error processing code: {e}")
            return []

    def _process_duck_tokens(
        self, duck_tokens: List[Tuple[int, Any]], code: str
    ) -> List[Token]:
        """Process DuckDB tokens into enhanced Token objects."""
        result: List[Token] = []
        total_len = len(code)

        for idx, (start, tok_enum) in enumerate(duck_tokens):
            try:
                # Extract basic token information
                end = self._get_token_end_position(duck_tokens, idx, total_len)
                lexeme = code[start:end]
                line, offset = self._calculate_position(code, start)
                base_tok_type = self._get_base_token_type(tok_enum)

                # Apply enhanced type resolution
                final_tok_type = self._resolve_enhanced_token_type(
                    duck_tokens, idx, code, total_len, base_tok_type, lexeme
                )

                token = Token(
                    line=line,
                    offset=offset,
                    text=lexeme,
                    tok_type=final_tok_type,
                )
                result.append(token)

            except Exception as e:
                logger.warning(f"Error processing token at position {start}: {e}")
                continue

        return result

    def _resolve_enhanced_token_type(
        self,
        duck_tokens: List[Tuple[int, Any]],
        idx: int,
        code: str,
        total_len: int,
        base_tok_type: str,
        lexeme: str,
    ) -> str:
        """
        Apply enhanced token type resolution rules.

        This includes:
        - Function detection (token followed by '(')
        - CAST function parameter handling (first parameter is identifier)
        - SQL data type detection
        - Context-aware type resolution (e.g., AS keyword handling)
        - Special keyword detection
        """
        # Check if this token is followed by '(' (function call)
        if self._is_token_followed_by_parenthesis(duck_tokens, idx, code, total_len):
            return "function"

        # Check if this token is the first parameter in a CAST function
        if self._is_first_parameter_in_cast(duck_tokens, idx, code, total_len):
            return "identifier"

        # Special handling for tokens after "AS" keyword
        if self._is_token_after_as_keyword(
            duck_tokens, idx, code, total_len, base_tok_type
        ):
            return "identifier"

        # Check if it's a SQL data type
        if self._is_sql_data_type(lexeme):
            return "type"

        # Return the base type from DuckDB
        return base_tok_type

    def _is_sql_data_type(self, text: str) -> bool:
        """Check if token text is a SQL data type."""
        return text.lower().strip() in self._config.SQL_DATA_TYPES

    def _is_token_after_as_keyword(
        self,
        duck_tokens: List[Tuple[int, Any]],
        idx: int,
        code: str,
        total_len: int,
        base_tok_type: str,
    ) -> bool:
        """Check if current token comes after an 'AS' keyword (but not in CAST expressions)."""
        if idx == 0 or base_tok_type == "operator":
            return False

        try:
            # Get the previous token's text
            prev_start = duck_tokens[idx - 1][0]
            prev_end = self._get_token_end_position(duck_tokens, idx - 1, total_len)
            prev_text = code[prev_start:prev_end].strip().lower()

            if prev_text != "as":
                return False
            
            # Check if this AS is inside a CAST function
            if self._is_as_inside_cast(code, prev_start):
                return False
            
            return True

        except (IndexError, ValueError):
            return False
    
    def _is_as_inside_cast(self, code: str, as_position: int) -> bool:
        """Check if the AS keyword at the given position is inside a CAST function."""
        # Look backwards from the AS position to find if we're inside CAST(...)
        text_before_as = code[:as_position].lower()
        
        # Find the last occurrence of 'cast' before this position
        cast_pos = text_before_as.rfind('cast')
        if cast_pos == -1:
            return False
        
        # Check if there's an opening parenthesis after 'cast'
        remaining_text = text_before_as[cast_pos + 4:].strip()
        if not remaining_text.startswith('('):
            return False
        
        # Count parentheses to see if we're still inside the CAST function
        # We need to make sure the AS is inside the CAST parentheses
        paren_count = 0
        for char in remaining_text:
            if char == '(':
                paren_count += 1
            elif char == ')':
                paren_count -= 1
                if paren_count == 0:
                    # We've closed the CAST function before reaching AS
                    return False
        
        # If we get here and paren_count > 0, we're still inside the CAST
        return paren_count > 0

    def _is_token_followed_by_parenthesis(
        self,
        duck_tokens: List[Tuple[int, Any]],
        idx: int,
        code: str,
        total_len: int,
    ) -> bool:
        """Check if the current token is followed by '(' (function call)."""
        if idx + 1 >= len(duck_tokens):
            return False
        
        try:
            # Get current token text
            current_start = duck_tokens[idx][0]
            current_end = self._get_token_end_position(duck_tokens, idx, total_len)
            current_text = code[current_start:current_end].strip().lower()
            
            # AS keyword should not be considered a function even if followed by '('
            if current_text == 'as':
                return False
            
            next_start = duck_tokens[idx + 1][0]
            next_end = self._get_token_end_position(duck_tokens, idx + 1, total_len)
            next_text = code[next_start:next_end].strip()
            return next_text == "("
        except (IndexError, ValueError):
            return False

    def get_token_type_index(self, token: Token) -> int:
        """
        Get the LSP token type index for a given token.

        Args:
            token: The token to resolve the type for

        Returns:
            The token type index for LSP
        """
        # Handle special type mappings
        if token.tok_type == "type":
            return self._config.TYPE_TOKEN_INDEX

        # Use configured mappings
        return self._config.TOKEN_TYPE_INDICES.get(
            token.tok_type, self._config.DEFAULT_TOKEN_INDEX
        )

    def _get_token_end_position(
        self, duck_tokens: List[Tuple[int, Any]], current_idx: int, total_len: int
    ) -> int:
        """Get the end position of the current token."""
        if current_idx + 1 < len(duck_tokens):
            return duck_tokens[current_idx + 1][0]
        return total_len

    def _calculate_position(self, code: str, start: int) -> Tuple[int, int]:
        """Calculate line and offset for a given position in code."""
        line = code.count("\n", 0, start)
        last_nl = code.rfind("\n", 0, start)
        offset = start - (last_nl + 1 if last_nl != -1 else 0)
        return line, offset

    def _get_base_token_type(self, tok_enum: Any) -> str:
        """Get base token type string from DuckDB enum."""
        return tok_enum.name if hasattr(tok_enum, "name") else str(tok_enum)

    def _is_first_parameter_in_cast(
        self,
        duck_tokens: List[Tuple[int, Any]],
        idx: int,
        code: str,
        total_len: int,
    ) -> bool:
        """Check if the current token is the first parameter in a CAST function."""
        if idx < 2:  # Need at least CAST( before current token
            return False

        try:
            # Check if we have CAST( pattern before this token
            # Pattern: [..., CAST, (, current_token]
            
            # Get the token two positions back (should be CAST)
            cast_start = duck_tokens[idx - 2][0]
            cast_end = self._get_token_end_position(duck_tokens, idx - 2, total_len)
            cast_text = code[cast_start:cast_end].strip().lower()
            
            # Get the token one position back (should be opening parenthesis)
            paren_start = duck_tokens[idx - 1][0]
            paren_end = self._get_token_end_position(duck_tokens, idx - 1, total_len)
            paren_text = code[paren_start:paren_end].strip()
            
            # Check if we have CAST( pattern
            return cast_text == "cast" and paren_text == "("

        except (IndexError, ValueError):
            return False 