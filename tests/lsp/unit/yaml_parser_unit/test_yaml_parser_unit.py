from utils.yaml_parser import YamlParser
import pytest

def test_get_parameters_with_missing_tool():
    """Test get_parameters when the tool key is missing."""
    yaml_string = """
mxcp: 1.0.0
parameters:
  - name: param1
    type: string
"""
    yaml_parser = YamlParser(yaml_string)
    assert yaml_parser.get_parameters() is None

def test_get_parameters_with_missing_parameters():
    """Test get_parameters when parameters key is missing."""
    yaml_string = """
mxcp: 1.0.0
tool:
  name: test_tool
  source:
    code: SELECT 1
"""
    yaml_parser = YamlParser(yaml_string)
    assert yaml_parser.get_parameters() is None

def test_get_code_span_with_invalid_yaml():
    """Test get_code_span with YAML that doesn't have the expected structure."""
    yaml_string = """
mxcp: 1.0.0
tool:
  name: test_tool
  description: "Tool without code section"
  parameters: []
"""
    yaml_parser = YamlParser(yaml_string)
    
    # Should handle missing code section gracefully
    assert yaml_parser.code_span is None

def test_get_code_span_with_missing_code():
    """Test get_code_span when the code key is missing."""
    yaml_string = """
mxcp: 1.0.0
tool:
  name: test_tool
  source:
    other_field: value
"""
    yaml_parser = YamlParser(yaml_string)
    assert yaml_parser.code_span is None

def test_get_code_span_with_different_scalar_styles():
    """Test get_code_span with different YAML scalar styles."""
    # Literal scalar style (|)
    yaml_string_literal = """
mxcp: 1.0.0
tool:
  source:
    code: |
      SELECT 1
      FROM table
"""
    yaml_parser = YamlParser(yaml_string_literal)
    assert yaml_parser.code_span is not None
    
    # Folded scalar style (>)
    yaml_string_folded = """
mxcp: 1.0.0
tool:
  source:
    code: >
      SELECT 1
      FROM table
"""
    yaml_parser = YamlParser(yaml_string_folded)
    assert yaml_parser.code_span is not None
    
    # Plain scalar style
    yaml_string_plain = """
mxcp: 1.0.0
tool:
  source:
    code: SELECT 1 FROM table
"""
    yaml_parser = YamlParser(yaml_string_plain)
    assert yaml_parser.code_span is not None 