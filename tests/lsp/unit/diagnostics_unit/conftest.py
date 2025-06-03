import pytest
import tempfile
import os
from utils.yaml_parser import YamlParser
from utils.duckdb_connector import DuckDBConnector
from features.diagnostics.diagnostics import DiagnosticsService


@pytest.fixture
def yaml_manager_inlined():
    with open("./tests/lsp/fixtures/tool_with_inlined_code.yml") as f:
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
    """Create a temporary DuckDB database for each test to ensure isolation."""
    # Create a temporary file path for the database (don't create the file yet)
    # Use NamedTemporaryFile to get a unique path, but delete it immediately
    # so DuckDB can create a fresh database file
    with tempfile.NamedTemporaryFile(suffix='.duckdb', prefix='test_diagnostics_', delete=False) as temp_file:
        db_path = temp_file.name
    
    # Remove the empty file that was created, so DuckDB can create a fresh database
    os.unlink(db_path)
    
    try:
        # Create DuckDB connector with the temporary database path
        duckdb_connector = DuckDBConnector(db_path)
        yield duckdb_connector
    finally:
        # Clean up: close connection and remove the temporary database file
        if 'duckdb_connector' in locals():
            duckdb_connector.close()
        if os.path.exists(db_path):
            os.unlink(db_path)


@pytest.fixture
def diagnostics_service(duckdb_connector):
    return DiagnosticsService(duckdb_connector) 