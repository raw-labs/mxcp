"""Tests for schema validation using Pydantic models."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from mxcp.sdk.validator.models import ValidationSchemaModel


class TestSchemaValidation:
    """Test schema validation using Pydantic models."""

    def test_validate_valid_schema(self):
        """Test that valid schemas are accepted."""
        valid_schema = {
            "input": {"parameters": [{"name": "x", "type": "string", "minLength": 1}]},
            "output": {"type": "object", "properties": {"result": {"type": "number"}}},
        }

        # Should not raise
        schema = ValidationSchemaModel.model_validate(valid_schema)
        assert schema.input_parameters is not None
        assert len(schema.input_parameters) == 1
        assert schema.input_parameters[0].name == "x"

    def test_type_field_is_required(self):
        """Test that type field is required in parameters."""
        with pytest.raises(ValidationError):
            ValidationSchemaModel.model_validate(
                {"input": {"parameters": [{"name": "x"}]}}  # Missing type
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
        schema = ValidationSchemaModel.model_validate(complex_schema)
        assert schema.input_parameters is not None
        assert schema.output_schema is not None

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
        schema = ValidationSchemaModel.model_validate(full_schema)
        assert schema.input_parameters is not None
        assert len(schema.input_parameters) == 4
