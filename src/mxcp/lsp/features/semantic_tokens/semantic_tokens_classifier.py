"""Semantic token classification and parsing."""

import enum
import logging
from typing import Dict, List, Optional

import attrs

from mxcp.lsp.utils.duckdb_connector import DuckDBConnector


logger = logging.getLogger(__name__)


class TokenModifier(enum.IntFlag):
    """Token modifiers as defined by LSP specification."""

    deprecated = enum.auto()
    readonly = enum.auto()
    defaultLibrary = enum.auto()
    definition = enum.auto()


def _validate_non_negative(instance, attribute, value):
    """Validator for non-negative integer values."""
    if value < 0:
        raise ValueError(f"Token {attribute.name} must be non-negative")


def _validate_non_empty_text(instance, attribute, value):
    """Validator for non-empty text values."""
    if not value:
        raise ValueError("Token text cannot be empty")


@attrs.define
class Token:
    """Represents a semantic token with position and type information."""

    line: int = attrs.field(validator=_validate_non_negative)
    offset: int = attrs.field(validator=_validate_non_negative)
    text: str = attrs.field(validator=_validate_non_empty_text)
    tok_type: str = ""
    tok_modifiers: List[TokenModifier] = attrs.field(factory=list)


class TokenExtractor:
    """Extracts and processes tokens from code using unified processor."""

    def __init__(self, duck_db_connector: DuckDBConnector):
        """Initialize with DuckDB connector."""
        self._duck_db_connector = duck_db_connector

    def extract_tokens(self, code: str) -> List[Token]:
        """
        Extract tokens from the given code using unified processing.

        Args:
            code: The source code to tokenize

        Returns:
            List of fully processed tokens
        """
        # Import here to avoid circular imports
        from .token_processor import TokenProcessor

        processor = TokenProcessor(self._duck_db_connector)
        return processor.process_code(code)


class SemanticTokensParser:
    """Parses documents and manages semantic tokens."""

    def __init__(self, duck_db_connector: DuckDBConnector):
        """Initialize with DuckDB connector."""
        self._tokens: Dict[str, List[Token]] = {}
        self._token_extractor = TokenExtractor(duck_db_connector)

    @property
    def tokens(self) -> Dict[str, List[Token]]:
        """Get the parsed tokens dictionary."""
        return self._tokens.copy()  # Return copy to prevent external modification

    def parse(self, code: str, uri: str) -> None:
        """
        Parse code and store tokens for the given URI.

        Args:
            code: The source code to parse
            uri: The document URI

        Raises:
            ValueError: If URI is empty or None
        """
        if not uri:
            raise ValueError("URI cannot be empty or None")

        try:
            tokens = self._token_extractor.extract_tokens(code)
            self._tokens[uri] = tokens
            logger.debug(f"Parsed {len(tokens)} tokens for URI: {uri}")

        except Exception as e:
            logger.error(f"Error parsing tokens for URI {uri}: {e}")
            self._tokens[uri] = []  # Store empty list on error

    def get_tokens_for_uri(self, uri: str) -> List[Token]:
        """
        Get tokens for a specific URI.

        Args:
            uri: The document URI

        Returns:
            List of tokens for the URI, empty list if not found
        """
        return self._tokens.get(uri, [])

    def clear_tokens_for_uri(self, uri: str) -> None:
        """Clear tokens for a specific URI."""
        self._tokens.pop(uri, None)
        logger.debug(f"Cleared tokens for URI: {uri}")

    def clear_all_tokens(self) -> None:
        """Clear all stored tokens."""
        self._tokens.clear()
        logger.debug("Cleared all tokens")


# duckdb token examples for the following code:
#   WITH raw AS (
#     SELECT * FROM read_json_auto('https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/all_day.geojson')
#   ),
#   features AS (
#     SELECT
#       feature
#     FROM raw,
#         UNNEST(features) AS feature
#   ),
#   quakes AS (
#     SELECT
#       feature -> 'unnest' -> 'properties' -> 'mag' AS magnitude,
#       feature -> 'unnest' -> 'properties' -> 'place' AS location,
#       feature -> 'unnest' -> 'properties' -> 'time' AS time,
#       feature -> 'unnest' -> 'geometry' -> 'coordinates' AS coords
#     FROM features
#   )
#   SELECT
#     CAST(magnitude AS DOUBLE) AS magnitude,
#     location,
#     CAST(time AS BIGINT) AS time,
#     coords
#   FROM quakes
#   WHERE CAST(magnitude AS DOUBLE) >= $min_magnitude
#   ORDER BY magnitude DESC; 