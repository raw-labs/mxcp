from mxcp.lsp.utils.duckdb_connector import DuckDBConnector
import pytest
from unittest.mock import Mock, MagicMock

def test_get_completions_with_none_values():
    """Test that get_completions handles None values in query results."""
    # Create a mock session with a connection
    mock_session = Mock()
    mock_connection = Mock()
    mock_session.conn = mock_connection
    
    connector = DuckDBConnector(session=mock_session)
    
    # Mock the execute_query to return a result with None values
    def mock_execute_query(query):
        return [(None,), ("valid",), (None,)]
    
    connector.execute_query = mock_execute_query
    
    # Get completions
    result = connector.get_completions("SELECT * FROM test")
    
    # Should only include non-None values
    assert len(result.items) == 1
    assert result.items[0].label == "valid"
    assert not result.is_incomplete 