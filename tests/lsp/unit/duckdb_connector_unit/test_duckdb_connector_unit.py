from utils.duckdb_connector import DuckDBConnector

def test_get_completions_with_none_values():
    """Test that get_completions handles None values in query results."""
    connector = DuckDBConnector()
    
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