import os
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
import duckdb
import pandas as pd
from pandas import NaT
from mxcp.server.mcp import RAWMCP
from mxcp.config.user_config import load_user_config
from mxcp.config.site_config import load_site_config
from mxcp.engine.duckdb_session import execute_query_to_dict


@pytest.fixture(scope="function")
def set_test_config_env():
    """Set up test environment with proper config path."""
    original_config = os.environ.get("MXCP_CONFIG")
    os.environ["MXCP_CONFIG"] = str(Path(__file__).parent / "fixtures" / "mcp" / "mxcp-config.yml")
    yield
    if original_config:
        os.environ["MXCP_CONFIG"] = original_config
    elif "MXCP_CONFIG" in os.environ:
        del os.environ["MXCP_CONFIG"]


@pytest.fixture
def mcp_repo_path():
    """Get path to test repository."""
    return Path(__file__).parent / "fixtures" / "mcp"


@pytest.fixture(autouse=True)
def change_to_mcp_repo(mcp_repo_path):
    """Change to test repository directory."""
    original_dir = os.getcwd()
    os.chdir(mcp_repo_path)
    try:
        yield
    finally:
        os.chdir(original_dir)


@pytest.fixture
def test_user_config(mcp_repo_path, set_test_config_env):
    """Load test user configuration."""
    site_config = load_site_config()
    return load_user_config(site_config)


@pytest.fixture
def test_site_config(mcp_repo_path, set_test_config_env):
    """Load test site configuration."""
    return load_site_config()


@pytest.fixture
def mcp_server_with_sql(test_user_config, test_site_config):
    """Create a RAWMCP instance with SQL tools enabled."""
    return RAWMCP(
        user_config=test_user_config,
        site_config=test_site_config,
        enable_sql_tools=True
    )


def test_execute_query_to_dict_original_bug_reproduction():
    """
    Test that reproduces the original bug where execute_sql_query returns empty results.
    
    This test creates conditions that cause the pandas .replace({NaT: None}) operation
    to interfere with normal query results, causing them to appear empty.
    """
    # Create a test database with data
    conn = duckdb.connect(":memory:")
    conn.execute("CREATE TABLE test_minimal (id INTEGER, name VARCHAR)")
    conn.execute("INSERT INTO test_minimal VALUES (1, 'Alice'), (2, 'Bob')")
    
    # Verify data exists with direct query
    direct_result = conn.execute("SELECT * FROM test_minimal").fetchall()
    assert len(direct_result) == 2
    assert direct_result == [(1, 'Alice'), (2, 'Bob')]
    
    # Test the problematic execute_query_to_dict function
    # This should work but may fail under certain conditions
    result = execute_query_to_dict(conn, "SELECT * FROM test_minimal")
    
    print(f"Direct query result: {direct_result}")
    print(f"execute_query_to_dict result: {result}")
    print(f"Result length: {len(result)}")
    
    # This assertion might FAIL if the bug is present
    assert len(result) > 0, f"execute_query_to_dict returned empty results: {result}"
    assert result == [{'id': 1, 'name': 'Alice'}, {'id': 2, 'name': 'Bob'}]
    
    conn.close()


def test_execute_query_to_dict_with_mocked_pandas_replace_bug():
    """
    Test that simulates the pandas replace operation causing empty results.
    
    This test mocks the pandas DataFrame.replace method to demonstrate
    how the bug could manifest.
    """
    # Create a test database with data
    conn = duckdb.connect(":memory:")
    conn.execute("CREATE TABLE test_minimal (id INTEGER, name VARCHAR)")
    conn.execute("INSERT INTO test_minimal VALUES (1, 'Alice'), (2, 'Bob')")
    
    # Mock the pandas DataFrame.replace method to simulate the bug
    original_replace = pd.DataFrame.replace
    
    def buggy_replace(self, to_replace=None, value=None, **kwargs):
        """Simulated buggy replace method that corrupts the DataFrame."""
        if to_replace == {NaT: None}:
            # Simulate the bug by returning an empty DataFrame or corrupted data
            # This represents what might happen in certain pandas versions or conditions
            return pd.DataFrame(columns=self.columns)  # Empty DataFrame with same columns
        return original_replace(self, to_replace, value, **kwargs)
    
    with patch.object(pd.DataFrame, 'replace', buggy_replace):
        # This should now reproduce the bug
        result = execute_query_to_dict(conn, "SELECT * FROM test_minimal")
        
        print(f"Buggy result: {result}")
        print(f"Result length: {len(result)}")
        
        # With the fix in place, this should now return correct results even with buggy pandas
        # The fix bypasses the problematic .replace() operation
        assert len(result) == 2, f"Fix should return correct results even with buggy pandas, got: {result}"
        assert result == [{'id': 1, 'name': 'Alice'}, {'id': 2, 'name': 'Bob'}]
    
    # Verify that without the mock, it works normally
    result_normal = execute_query_to_dict(conn, "SELECT * FROM test_minimal")
    assert len(result_normal) == 2
    assert result_normal == [{'id': 1, 'name': 'Alice'}, {'id': 2, 'name': 'Bob'}]
    
    conn.close()


def test_execute_query_to_dict_with_problematic_dataframe():
    """
    Test with a DataFrame that might cause issues with the replace operation.
    
    This test creates specific conditions that could trigger the bug.
    """
    # Create a test database with data
    conn = duckdb.connect(":memory:")
    conn.execute("CREATE TABLE test_minimal (id INTEGER, name VARCHAR)")
    conn.execute("INSERT INTO test_minimal VALUES (1, 'Alice'), (2, 'Bob')")
    
    # Test the function with normal data - this should work with the fix
    result = execute_query_to_dict(conn, "SELECT * FROM test_minimal")
    
    print(f"Problematic DataFrame result: {result}")
    print(f"Result length: {len(result)}")
    
    # With the fix, this should always work correctly
    assert len(result) == 2
    assert result == [{'id': 1, 'name': 'Alice'}, {'id': 2, 'name': 'Bob'}]
        
    conn.close()


@pytest.mark.asyncio
async def test_mcp_server_execute_sql_query_bug(mcp_server_with_sql):
    """
    Test the actual MCP server execute_sql_query tool to reproduce the bug.
    
    This test sets up a full MCP server and attempts to reproduce the issue
    where execute_sql_query returns empty results.
    """
    # Set up test data in the database
    with mcp_server_with_sql.db_lock:
        # Use unique table name to avoid conflicts
        table_name = "test_minimal_mcp"
        mcp_server_with_sql.db_session.conn.execute(f"DROP TABLE IF EXISTS {table_name}")
        mcp_server_with_sql.db_session.conn.execute(f"CREATE TABLE {table_name} (id INTEGER, name VARCHAR)")
        mcp_server_with_sql.db_session.conn.execute(f"INSERT INTO {table_name} VALUES (1, 'Alice'), (2, 'Bob')")
        
        # Verify data exists with direct query
        direct_result = mcp_server_with_sql.db_session.conn.execute(f"SELECT * FROM {table_name}").fetchall()
        assert len(direct_result) == 2
        
        # Test the execute_query_to_dict method (this is what execute_sql_query uses internally)
        dict_result = mcp_server_with_sql.db_session.execute_query_to_dict(f"SELECT * FROM {table_name}")
        
        print(f"Direct MCP result: {direct_result}")
        print(f"MCP execute_query_to_dict result: {dict_result}")
        print(f"Result length: {len(dict_result)}")
        
        # This assertion might FAIL if the bug is present
        assert len(dict_result) > 0, f"MCP execute_query_to_dict returned empty results: {dict_result}"
        assert dict_result == [{'id': 1, 'name': 'Alice'}, {'id': 2, 'name': 'Bob'}]