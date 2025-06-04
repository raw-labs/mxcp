import pytest
from lsprotocol import types
from mxcp.lsp.features.diagnostics.diagnostics import DiagnosticsService
from mxcp.lsp.utils.coordinate_transformer import CoordinateTransformer


def test_should_provide_lsp_for_valid_yaml(yaml_manager_inlined):
    """Test that LSP should be provided for valid YAML with SQL code."""
    should_parse = yaml_manager_inlined.should_provide_lsp()
    assert should_parse is True, "Expected should_provide_lsp to be True for valid YAML"


def test_should_not_provide_lsp_for_empty_yaml(yaml_manager_empty):
    """Test that LSP should not be provided for empty YAML."""
    should_parse = yaml_manager_empty.should_provide_lsp()
    assert should_parse is False, "Expected should_provide_lsp to be False for empty YAML"


def test_parse_document_with_valid_sql(diagnostics_service, yaml_manager_inlined):
    """Test parsing a document with valid SQL code."""
    document_uri = "test://valid.yml"
    document_source = """
tool:
  description: "Test tool"
  source:
    code: |
      SELECT 1 as test_column
  parameters: []
mxcp: 1.0.0
"""
    
    diagnostics_service.parse_document(document_uri, document_source, 1)
    version, diagnostics = diagnostics_service.get_diagnostics(document_uri)
    
    assert version == 1, "Expected version to be 1"
    assert len(diagnostics) == 0, "Expected no diagnostics for valid SQL"


def test_parse_document_with_invalid_sql(diagnostics_service, yaml_manager_invalid_sql):
    """Test parsing a document with invalid SQL code."""
    document_uri = "test://invalid.yml"
    document_source = """
tool:
  description: "Test tool with invalid SQL"
  source:
    code: |
      SELECT * FROM invalid_table
      WHERE invalid_column =
  parameters: []
mxcp: 1.0.0
"""
    
    diagnostics_service.parse_document(document_uri, document_source, 1)
    version, diagnostics = diagnostics_service.get_diagnostics(document_uri)
    
    assert version == 1, "Expected version to be 1"
    assert len(diagnostics) > 0, "Expected diagnostics for invalid SQL"
    
    # Check the diagnostic properties
    diagnostic = diagnostics[0]
    assert isinstance(diagnostic, types.Diagnostic), "Expected diagnostic to be a Diagnostic object"
    assert diagnostic.severity in [types.DiagnosticSeverity.Error, types.DiagnosticSeverity.Warning], \
        "Expected diagnostic severity to be Error or Warning"
    assert diagnostic.source == "mxcp-lsp", "Expected diagnostic source to be 'mxcp-lsp'"
    assert len(diagnostic.message) > 0, "Expected diagnostic message to be non-empty"


def test_parse_document_with_no_sql_code(diagnostics_service):
    """Test parsing a document with no SQL code."""
    document_uri = "test://no_sql.yml"
    document_source = """
description: "Just a regular YAML file"
key: value
"""
    
    diagnostics_service.parse_document(document_uri, document_source, 1)
    version, diagnostics = diagnostics_service.get_diagnostics(document_uri)
    
    assert version == 1, "Expected version to be 1"
    assert len(diagnostics) == 0, "Expected no diagnostics for YAML without SQL"


def test_coordinate_transformer_sql_to_document():
    """Test the coordinate transformation from SQL coordinates to document coordinates."""
    # Mock code span - SQL starts at line 4, character 6 (typical YAML indentation)
    code_span = (types.Position(line=4, character=6), types.Position(line=6, character=10))
    
    # Test position on the first line of SQL
    sql_position = types.Position(line=0, character=5)
    adjusted = CoordinateTransformer.sql_to_document_position(sql_position, code_span)
    assert adjusted.line == 4, f"Expected adjusted line to be 4, got {adjusted.line}"
    assert adjusted.character == 11, f"Expected adjusted character to be 11, got {adjusted.character}"
    
    # Test position on a subsequent line of SQL - this is the key fix
    sql_position = types.Position(line=1, character=3)
    adjusted = CoordinateTransformer.sql_to_document_position(sql_position, code_span)
    assert adjusted.line == 5, f"Expected adjusted line to be 5, got {adjusted.line}"
    assert adjusted.character == 9, f"Expected adjusted character to be 9 (6 + 3), got {adjusted.character}"
    
    # Test position on a third line to ensure consistency
    sql_position = types.Position(line=2, character=0)
    adjusted = CoordinateTransformer.sql_to_document_position(sql_position, code_span)
    assert adjusted.line == 6, f"Expected adjusted line to be 6, got {adjusted.line}"
    assert adjusted.character == 6, f"Expected adjusted character to be 6 (6 + 0), got {adjusted.character}"


def test_get_diagnostics_for_nonexistent_document(diagnostics_service):
    """Test getting diagnostics for a document that hasn't been parsed."""
    version, diagnostics = diagnostics_service.get_diagnostics("test://nonexistent.yml")
    
    assert version == 0, "Expected version to be 0 for nonexistent document"
    assert len(diagnostics) == 0, "Expected no diagnostics for nonexistent document"


def test_multiple_document_parsing(diagnostics_service):
    """Test parsing multiple documents and ensuring they're handled separately."""
    # Parse first document (valid SQL)
    document_uri_1 = "test://valid1.yml"
    document_source_1 = """
tool:
  description: "Test tool 1"
  source:
    code: |
      SELECT 1 as test
  parameters: []
mxcp: 1.0.0
"""
    
    # Parse second document (invalid SQL)
    document_uri_2 = "test://invalid2.yml"
    document_source_2 = """
tool:
  description: "Test tool 2"
  source:
    code: |
      SELECT * FROM
  parameters: []
mxcp: 1.0.0
"""
    
    diagnostics_service.parse_document(document_uri_1, document_source_1, 1)
    diagnostics_service.parse_document(document_uri_2, document_source_2, 1)
    
    # Check first document (should have no diagnostics)
    version1, diagnostics1 = diagnostics_service.get_diagnostics(document_uri_1)
    assert len(diagnostics1) == 0, "Expected no diagnostics for valid SQL"
    
    # Check second document (should have diagnostics)
    version2, diagnostics2 = diagnostics_service.get_diagnostics(document_uri_2)
    assert len(diagnostics2) > 0, "Expected diagnostics for invalid SQL"


def test_yaml_indentation_in_diagnostics(diagnostics_service):
    """Test that diagnostics positions correctly account for YAML indentation."""
    document_uri = "test://yaml_indent.yml"
    document_source = """mxcp: 1.0.0
tool:
  description: "Test YAML indentation"
  source:
    code: |
      SELECT 1 as first_line
      SELECT * FROM invalid_table
      WHERE column_name =
  parameters: []
"""
    
    diagnostics_service.parse_document(document_uri, document_source, 1)
    version, diagnostics = diagnostics_service.get_diagnostics(document_uri)
    
    assert version == 1, "Expected version to be 1"
    assert len(diagnostics) > 0, "Expected diagnostics for invalid SQL"
    
    # Check that the diagnostic position includes YAML indentation
    diagnostic = diagnostics[0]
    assert diagnostic.range.start.line >= 5, f"Expected line >= 5 (SQL starts at line 5), got {diagnostic.range.start.line}"
    assert diagnostic.range.start.character >= 6, f"Expected character >= 6 (YAML indentation), got {diagnostic.range.start.character}" 