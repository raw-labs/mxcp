import pytest
import tempfile
import os
from unittest.mock import Mock
from pathlib import Path
import duckdb
from mxcp.lsp.utils.yaml_parser import YamlParser
from mxcp.lsp.utils.duckdb_connector import DuckDBConnector

# Get the path to the e2e config directory with isolated test configuration
TEST_CONFIG_DIR = Path(__file__).parent.parent.parent / "fixtures" / "e2e-config"

@pytest.fixture
def yaml_manager_inlined():
    with open(TEST_CONFIG_DIR / "tool_with_inlined_code.yml") as f:
        yaml_text = f.read()
        yaml_parser = YamlParser(yaml_text)
    return yaml_parser


@pytest.fixture
def yaml_manager_file():
    with open(TEST_CONFIG_DIR / "tool_with_file_code.yml") as f:
        yaml_text = f.read()
        yaml_parser = YamlParser(yaml_text)
    return yaml_parser


@pytest.fixture
def yaml_manager_empty():
    yaml_parser = YamlParser("")
    return yaml_parser


@pytest.fixture
def duckdb_connector():
    """Create a mock session with a real DuckDB connection for testing."""
    # Create a temporary in-memory DuckDB connection
    connection = duckdb.connect(":memory:")
    
    # Create a mock session that behaves like DuckDBSession
    mock_session = Mock()
    mock_session.conn = connection
    
    try:
        # Create DuckDB connector with the mock session
        duckdb_connector = DuckDBConnector(session=mock_session)
        yield duckdb_connector
    finally:
        # Clean up: close the connection
        if connection:
            connection.close()
