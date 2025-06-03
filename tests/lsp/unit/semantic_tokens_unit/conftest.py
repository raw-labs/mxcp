import pytest
from unittest.mock import Mock
from mxcp.lsp.utils.duckdb_connector import DuckDBConnector
from mxcp.lsp.features.semantic_tokens.semantic_tokens_classifier import (
    TokenModifier,
    SemanticTokensParser,
    Token
)


@pytest.fixture
def mock_duck_db_connector():
    return Mock(spec=DuckDBConnector)


@pytest.fixture
def parser(mock_duck_db_connector):
    return SemanticTokensParser(mock_duck_db_connector)


@pytest.fixture
def sample_sql_code():
    return "SELECT * FROM table"


@pytest.fixture
def sample_multiline_sql_code():
    return "SELECT *\nFROM table"


@pytest.fixture
def mock_tokens():
    return [(0, "keyword"), (7, "operator"), (9, "keyword"), (14, "identifier")]


@pytest.fixture
def expected_tokens():
    return [
        Token(line=0, offset=0, text="SELECT ", tok_type="keyword"),
        Token(line=0, offset=7, text="* ", tok_type="operator"),
        Token(line=0, offset=9, text="FROM ", tok_type="keyword"),
        Token(line=0, offset=14, text="table", tok_type="identifier")
    ] 