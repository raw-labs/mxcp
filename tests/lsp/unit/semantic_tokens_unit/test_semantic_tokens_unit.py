"""Unit tests for semantic tokens functionality."""

import pytest
from lsprotocol import types
from unittest.mock import Mock, MagicMock, patch

from mxcp.lsp.features.semantic_tokens.semantic_tokens_classifier import (
    TokenModifier,
    Token, 
    SemanticTokensParser,
    TokenExtractor
)
from mxcp.lsp.features.semantic_tokens.semantic_tokens_config import SemanticTokensConfig
from mxcp.lsp.features.semantic_tokens.token_processor import TokenProcessor
from mxcp.lsp.utils.duckdb_connector import DuckDBConnector


@pytest.fixture
def mock_duck_db_connector():
    """Create a mock DuckDB connector."""
    connector = Mock(spec=DuckDBConnector)
    return connector


@pytest.fixture
def parser(mock_duck_db_connector):
    """Create a SemanticTokensParser instance with mocked dependencies."""
    return SemanticTokensParser(mock_duck_db_connector)


@pytest.fixture
def token_extractor(mock_duck_db_connector):
    """Create a TokenExtractor instance with mocked dependencies."""
    return TokenExtractor(mock_duck_db_connector)


@pytest.fixture
def token_processor(mock_duck_db_connector):
    """Create a TokenProcessor instance with mocked dependencies."""
    return TokenProcessor(mock_duck_db_connector)


@pytest.fixture
def expected_tokens():
    """Sample tokens for testing."""
    return [
        Token(line=0, offset=0, text="SELECT ", tok_type="keyword"),
        Token(line=0, offset=7, text="* ", tok_type="operator"),
        Token(line=0, offset=9, text="FROM ", tok_type="keyword"),
        Token(line=0, offset=14, text="table", tok_type="identifier"),
    ]


@pytest.fixture
def sample_sql_code():
    """Sample SQL code for testing."""
    return "SELECT * FROM table"


@pytest.fixture
def sample_multiline_sql_code():
    """Sample multiline SQL code for testing."""
    return "SELECT *\nFROM table"


@pytest.fixture
def mock_tokens():
    """Mock token data as returned by DuckDB."""
    # Create mock objects that properly return the string names
    keyword_mock = Mock()
    keyword_mock.name = "keyword"
    
    operator_mock = Mock()
    operator_mock.name = "operator"
    
    identifier_mock = Mock()
    identifier_mock.name = "identifier"
    
    return [
        (0, keyword_mock),
        (7, operator_mock),
        (9, keyword_mock),
        (14, identifier_mock),
    ]


class TestTokenProcessor:
    """Test cases for TokenProcessor class."""

    def test_process_code_empty_code(self, token_processor):
        """Test processing empty code."""
        # Act
        tokens = token_processor.process_code("")

        # Assert
        assert tokens == []

    def test_process_code_no_duck_tokens(self, token_processor, sample_sql_code):
        """Test behavior when DuckDB returns no tokens."""
        # Arrange
        token_processor._duck_db_connector.get_tokens.return_value = []

        # Act
        tokens = token_processor.process_code(sample_sql_code)

        # Assert
        assert tokens == []

    def test_process_code_success(self, token_processor, sample_sql_code, mock_tokens):
        """Test successful token processing."""
        # Arrange
        token_processor._duck_db_connector.get_tokens.return_value = mock_tokens

        # Act
        tokens = token_processor.process_code(sample_sql_code)

        # Assert
        assert len(tokens) == 4
        assert tokens[0].line == 0
        assert tokens[0].offset == 0
        assert tokens[0].text == "SELECT "
        assert tokens[0].tok_type == "keyword"

    def test_process_code_with_cast_as_keyword(self, token_processor):
        """Test processing code with AS keyword inside CAST (should not treat as identifier)."""
        # Arrange
        code = "SELECT CAST(time AS BIGINT)"
        
        # Mock tokens: SELECT, CAST, (, time, AS, BIGINT, )
        select_mock = Mock()
        select_mock.name = "keyword"
        cast_mock = Mock()
        cast_mock.name = "keyword"
        paren_open_mock = Mock()
        paren_open_mock.name = "operator"
        time_mock = Mock()
        time_mock.name = "identifier"
        as_mock = Mock()
        as_mock.name = "keyword"
        bigint_mock = Mock()
        bigint_mock.name = "identifier"  # DuckDB might return this as identifier
        paren_close_mock = Mock()
        paren_close_mock.name = "operator"
        
        mock_tokens = [
            (0, select_mock),      # SELECT
            (7, cast_mock),        # CAST
            (11, paren_open_mock), # (
            (12, time_mock),       # time
            (17, as_mock),         # AS
            (20, bigint_mock),     # BIGINT
            (26, paren_close_mock),# )
        ]
        
        token_processor._duck_db_connector.get_tokens.return_value = mock_tokens

        # Act
        tokens = token_processor.process_code(code)

        # Assert
        assert len(tokens) == 7
        bigint_token = tokens[5]  # BIGINT token
        assert bigint_token.text == "BIGINT"
        # Should be "type" because it's a SQL data type, not "identifier" 
        # even though it comes after AS (because it's inside CAST)
        assert bigint_token.tok_type == "type"

    def test_process_code_with_as_keyword(self, token_processor):
        """Test processing code with AS keyword context (aliasing)."""
        # Arrange
        code = "SELECT column AS alias"
        
        # Mock tokens: SELECT, column, AS, alias
        select_mock = Mock()
        select_mock.name = "keyword"
        column_mock = Mock()  
        column_mock.name = "identifier"
        as_mock = Mock()
        as_mock.name = "keyword"
        alias_mock = Mock()
        alias_mock.name = "identifier"
        
        mock_tokens = [
            (0, select_mock),   # SELECT
            (7, column_mock),   # column
            (14, as_mock),      # AS
            (17, alias_mock),   # alias
        ]
        
        token_processor._duck_db_connector.get_tokens.return_value = mock_tokens

        # Act
        tokens = token_processor.process_code(code)

        # Assert
        assert len(tokens) == 4
        assert tokens[3].text == "alias"
        assert tokens[3].tok_type == "identifier"  # Should be identifier due to AS keyword (aliasing)

    def test_process_code_with_function_detection(self, token_processor):
        """Test processing code with function detection."""
        # Arrange
        code = "SELECT COUNT(*), MAX(price) FROM products"
        
        # Mock tokens: SELECT, COUNT, (, *, ), ,, MAX, (, price, ), FROM, products
        select_mock = Mock()
        select_mock.name = "keyword"
        count_mock = Mock()
        count_mock.name = "identifier"  # DuckDB returns as identifier
        paren_open_mock = Mock()
        paren_open_mock.name = "operator"
        star_mock = Mock()
        star_mock.name = "operator"
        paren_close_mock = Mock()
        paren_close_mock.name = "operator"
        comma_mock = Mock()
        comma_mock.name = "operator"
        max_mock = Mock()
        max_mock.name = "identifier"  # DuckDB returns as identifier
        price_mock = Mock()
        price_mock.name = "identifier"
        from_mock = Mock()
        from_mock.name = "keyword"
        products_mock = Mock()
        products_mock.name = "identifier"
        
        mock_tokens = [
            (0, select_mock),      # SELECT
            (7, count_mock),       # COUNT
            (12, paren_open_mock), # (
            (13, star_mock),       # *
            (14, paren_close_mock),# )
            (15, comma_mock),      # ,
            (17, max_mock),        # MAX
            (20, paren_open_mock), # (
            (21, price_mock),      # price
            (26, paren_close_mock),# )
            (28, from_mock),       # FROM
            (33, products_mock),   # products
        ]
        
        token_processor._duck_db_connector.get_tokens.return_value = mock_tokens

        # Act
        tokens = token_processor.process_code(code)

        # Assert
        assert len(tokens) == 12
        
        # COUNT should be detected as function (followed by '(')
        count_token = tokens[1]
        assert count_token.text == "COUNT"
        assert count_token.tok_type == "function"
        
        # MAX should be detected as function (followed by '(')
        max_token = tokens[6]
        assert max_token.text == "MAX"
        assert max_token.tok_type == "function"
        
        # price should remain as identifier (not followed by '(')
        price_token = tokens[8]
        assert price_token.text == "price"
        assert price_token.tok_type == "identifier"

    def test_process_code_as_not_function_in_cte(self, token_processor):
        """Test that AS keyword is not classified as function even when followed by '(' (CTE case)."""
        # Arrange
        code = "WITH raw AS ("
        
        # Mock tokens: WITH, raw, AS, (
        with_mock = Mock()
        with_mock.name = "keyword"
        raw_mock = Mock()
        raw_mock.name = "identifier"
        as_mock = Mock()
        as_mock.name = "keyword"
        paren_open_mock = Mock()
        paren_open_mock.name = "operator"
        
        mock_tokens = [
            (0, with_mock),        # WITH
            (5, raw_mock),         # raw
            (9, as_mock),          # AS
            (12, paren_open_mock), # (
        ]
        
        token_processor._duck_db_connector.get_tokens.return_value = mock_tokens

        # Act
        tokens = token_processor.process_code(code)

        # Assert
        assert len(tokens) == 4
        
        # AS should remain as keyword, not classified as function
        as_token = tokens[2]
        assert as_token.text == "AS "  # Include the trailing space
        assert as_token.tok_type == "keyword"  # Should stay as keyword, not become function

    def test_process_code_cast_parameter_as_identifier(self, token_processor):
        """Test that first parameter in CAST is treated as identifier, not type."""
        # Arrange
        code = "CAST(time AS BIGINT) AS time"
        
        # Mock tokens: CAST, (, time, AS, BIGINT, ), AS, time
        cast_mock = Mock()
        cast_mock.name = "keyword"  # CAST might come as keyword from DuckDB
        paren_open_mock = Mock()
        paren_open_mock.name = "operator"
        time_mock = Mock()
        time_mock.name = "identifier"  # DuckDB returns as identifier
        as_mock = Mock()
        as_mock.name = "keyword"
        bigint_mock = Mock()
        bigint_mock.name = "identifier"  # DuckDB might return this as identifier
        paren_close_mock = Mock()
        paren_close_mock.name = "operator"
        as_mock2 = Mock()
        as_mock2.name = "keyword"
        time_mock2 = Mock()
        time_mock2.name = "identifier"
        
        mock_tokens = [
            (0, cast_mock),        # CAST
            (4, paren_open_mock),  # (
            (5, time_mock),        # time (first parameter - should be identifier)
            (10, as_mock),         # AS
            (13, bigint_mock),     # BIGINT
            (19, paren_close_mock),# )
            (21, as_mock2),        # AS
            (24, time_mock2),      # time (alias)
        ]
        
        token_processor._duck_db_connector.get_tokens.return_value = mock_tokens

        # Act
        tokens = token_processor.process_code(code)

        # Assert
        assert len(tokens) == 8
        
        # CAST should be function
        cast_token = tokens[0]
        assert cast_token.text.strip() == "CAST"
        assert cast_token.tok_type == "function"
        
        # First 'time' (CAST parameter) should be identifier, not type
        first_time_token = tokens[2]
        assert first_time_token.text.strip() == "time"
        assert first_time_token.tok_type == "identifier"  # Should be identifier (column reference)
        
        # BIGINT should be type
        bigint_token = tokens[4]
        assert bigint_token.text.strip() == "BIGINT"
        assert bigint_token.tok_type == "type"
        
        # Second 'time' (alias) should be identifier
        second_time_token = tokens[7]
        assert second_time_token.text.strip() == "time"
        assert second_time_token.tok_type == "identifier"  # Should be identifier (alias)

    def test_get_token_type_index_sql_data_type(self, token_processor):
        """Test token type index resolution for SQL data types."""
        # Arrange
        token = Token(line=0, offset=0, text="INTEGER", tok_type="type")

        # Act
        index = token_processor.get_token_type_index(token)

        # Assert
        assert index == SemanticTokensConfig.TYPE_TOKEN_INDEX

    def test_get_token_type_index_known_type(self, token_processor):
        """Test token type index resolution for known types."""
        # Arrange
        token = Token(line=0, offset=0, text="SELECT", tok_type="keyword")

        # Act
        index = token_processor.get_token_type_index(token)

        # Assert
        assert index == SemanticTokensConfig.TOKEN_TYPE_INDICES["keyword"]

    def test_get_token_type_index_unknown_type(self, token_processor):
        """Test token type index resolution for unknown types."""
        # Arrange
        token = Token(line=0, offset=0, text="unknown", tok_type="unknown_type")

        # Act
        index = token_processor.get_token_type_index(token)

        # Assert
        assert index == SemanticTokensConfig.DEFAULT_TOKEN_INDEX


class TestTokenExtractor:
    """Test cases for TokenExtractor class."""

    def test_extract_tokens_empty_code(self, token_extractor):
        """Test extracting tokens from empty code."""
        # Act
        tokens = token_extractor.extract_tokens("")

        # Assert
        assert tokens == []

    def test_extract_tokens_success(self, token_extractor, sample_sql_code, mock_tokens):
        """Test successful token extraction using unified processor."""
        # Arrange
        token_extractor._duck_db_connector.get_tokens.return_value = mock_tokens

        # Act
        tokens = token_extractor.extract_tokens(sample_sql_code)

        # Assert
        assert len(tokens) == 4
        assert tokens[0].line == 0
        assert tokens[0].offset == 0
        assert tokens[0].text == "SELECT "
        assert tokens[0].tok_type == "keyword"


class TestSemanticTokensParser:
    """Test cases for SemanticTokensParser class."""

    def test_parse_success(self, parser, sample_sql_code, expected_tokens):
        """Test successful parsing."""
        # Arrange
        parser._token_extractor.extract_tokens = Mock(return_value=expected_tokens)

        # Act
        parser.parse(sample_sql_code, "test.uri")

        # Assert
        assert "test.uri" in parser.tokens
        assert len(parser.get_tokens_for_uri("test.uri")) == len(expected_tokens)

    def test_parse_empty_uri(self, parser, sample_sql_code):
        """Test parsing with empty URI."""
        # Act & Assert
        with pytest.raises(ValueError, match="URI cannot be empty or None"):
            parser.parse(sample_sql_code, "")

    def test_parse_none_uri(self, parser, sample_sql_code):
        """Test parsing with None URI."""
        # Act & Assert
        with pytest.raises(ValueError, match="URI cannot be empty or None"):
            parser.parse(sample_sql_code, None)

    def test_get_tokens_for_uri_existing(self, parser, expected_tokens):
        """Test getting tokens for existing URI."""
        # Arrange
        parser._tokens["test.uri"] = expected_tokens

        # Act
        tokens = parser.get_tokens_for_uri("test.uri")

        # Assert
        assert tokens == expected_tokens

    def test_get_tokens_for_uri_nonexistent(self, parser):
        """Test getting tokens for non-existent URI."""
        # Act
        tokens = parser.get_tokens_for_uri("nonexistent.uri")

        # Assert
        assert tokens == []

    def test_clear_tokens_for_uri(self, parser, expected_tokens):
        """Test clearing tokens for specific URI."""
        # Arrange
        parser._tokens["test.uri"] = expected_tokens

        # Act
        parser.clear_tokens_for_uri("test.uri")

        # Assert
        assert parser.get_tokens_for_uri("test.uri") == []

    def test_clear_all_tokens(self, parser, expected_tokens):
        """Test clearing all tokens."""
        # Arrange
        parser._tokens["test1.uri"] = expected_tokens
        parser._tokens["test2.uri"] = expected_tokens

        # Act
        parser.clear_all_tokens()

        # Assert
        assert len(parser.tokens) == 0

    def test_tokens_property_returns_copy(self, parser, expected_tokens):
        """Test that tokens property returns a copy."""
        # Arrange
        parser._tokens["test.uri"] = expected_tokens

        # Act
        tokens_copy = parser.tokens
        tokens_copy.clear()

        # Assert
        assert len(parser._tokens) == 1  # Original should be unchanged


class TestToken:
    """Test cases for Token class."""

    def test_token_creation_valid(self):
        """Test valid token creation."""
        # Act
        token = Token(line=1, offset=5, text="SELECT", tok_type="keyword")

        # Assert
        assert token.line == 1
        assert token.offset == 5
        assert token.text == "SELECT"
        assert token.tok_type == "keyword"

    def test_token_validation_negative_line(self):
        """Test token validation with negative line."""
        # Act & Assert
        with pytest.raises(ValueError, match="Token line must be non-negative"):
            Token(line=-1, offset=0, text="SELECT")

    def test_token_validation_negative_offset(self):
        """Test token validation with negative offset."""
        # Act & Assert
        with pytest.raises(ValueError, match="Token offset must be non-negative"):
            Token(line=0, offset=-1, text="SELECT")

    def test_token_validation_empty_text(self):
        """Test token validation with empty text."""
        # Act & Assert
        with pytest.raises(ValueError, match="Token text cannot be empty"):
            Token(line=0, offset=0, text="")