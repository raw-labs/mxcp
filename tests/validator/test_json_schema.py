"""Tests for JSON schema-based validation."""

import json
from pathlib import Path

import pytest

from mxcp.validator.loaders import validate_schema_structure


class TestJSONSchemaValidation:
    """Test JSON schema validation functionality."""

    def test_json_schema_exists(self):
        """Test that the JSON schema file exists."""
        schema_path = (
            Path(__file__).parent.parent.parent
            / "src"
            / "mxcp"
            / "validator"
            / "schemas"
            / "validation-schema-1.json"
        )
        assert schema_path.exists(), f"JSON schema not found at {schema_path}"

        # Verify it's valid JSON
        with open(schema_path) as f:
            schema = json.load(f)

        # Verify it has expected structure
        assert "$schema" in schema
        assert "definitions" in schema
        assert "parameterSchema" in schema["definitions"]
        assert "typeSchema" in schema["definitions"]

    def test_validate_with_json_schema(self):
        """Test that validation uses JSON schema when available."""
        # Valid schema
        valid_schema = {
            "input": {"parameters": [{"name": "x", "type": "string", "minLength": 1}]},
            "output": {"type": "object", "properties": {"result": {"type": "number"}}},
        }

        # Should not raise
        validate_schema_structure(valid_schema)

        # Invalid type value
        with pytest.raises(ValueError, match="is not one of"):
            validate_schema_structure(
                {"input": {"parameters": [{"name": "x", "type": "invalid_type"}]}}  # Not in enum
            )

        # Invalid format value
        with pytest.raises(ValueError, match="is not one of"):
            validate_schema_structure(
                {
                    "input": {
                        "parameters": [{"name": "x", "type": "string", "format": "invalid_format"}]
                    }
                }
            )

    def test_complex_schema_validation(self):
        """Test validation of complex schemas."""
        complex_schema = {
            "input": {
                "parameters": [
                    {
                        "name": "config",
                        "type": "object",
                        "properties": {
                            "items": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "id": {"type": "integer"},
                                        "name": {"type": "string"},
                                    },
                                    "required": ["id", "name"],
                                },
                            }
                        },
                        "required": ["items"],
                    }
                ]
            },
            "output": {"type": "array", "items": {"type": "string"}},
        }

        # Should validate successfully
        validate_schema_structure(complex_schema)

    def test_schema_with_all_constraints(self):
        """Test schema with all supported constraints."""
        full_schema = {
            "input": {
                "parameters": [
                    {
                        "name": "text",
                        "type": "string",
                        "minLength": 5,
                        "maxLength": 100,
                        "format": "email",
                    },
                    {
                        "name": "count",
                        "type": "integer",
                        "minimum": 0,
                        "maximum": 1000,
                        "multipleOf": 5,
                    },
                    {
                        "name": "tags",
                        "type": "array",
                        "items": {"type": "string"},
                        "minItems": 1,
                        "maxItems": 10,
                        "uniqueItems": True,
                    },
                    {"name": "status", "type": "string", "enum": ["active", "inactive", "pending"]},
                ]
            }
        }

        # Should validate successfully
        validate_schema_structure(full_schema)
