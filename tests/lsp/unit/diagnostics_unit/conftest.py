import pytest
import tempfile
import os
from unittest.mock import Mock
import duckdb
from mxcp.lsp.utils.yaml_parser import YamlParser
from mxcp.lsp.utils.duckdb_connector import DuckDBConnector
from mxcp.lsp.features.diagnostics.diagnostics import DiagnosticsService


@pytest.fixture
def yaml_manager_inlined():
    with open("./tests/lsp/fixtures/e2e-config/tool_with_inlined_code.yml") as f:
        yaml_text = f.read()
        yaml_parser = YamlParser(yaml_text)
    return yaml_parser


@pytest.fixture
def yaml_manager_invalid_sql(duckdb_connector):
    """Fixture for YamlParser with invalid SQL code."""
    yaml_string = """
mxcp: 1.0.0
tool:
  description: "Tool with invalid SQL"
  source:
    code: |
      SELECT * FROM non_existent_table
      WHERE invalid_syntax =
  parameters: []
"""
    return YamlParser(yaml_string)


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


@pytest.fixture
def diagnostics_service(duckdb_connector):
    return DiagnosticsService(duckdb_connector) 