"""Tests for mxcp.sdk.validator.core module."""

from datetime import date, datetime, time

import pandas as pd
import pytest

from mxcp.sdk.validator import TypeValidator, ValidationError


class TestTypeValidator:
    """Test the TypeValidator class."""

    def test_simple_input_validation(self):
        """Test basic input parameter validation."""
        schema = {
            "input": {
                "parameters": [{"name": "x", "type": "integer"}, {"name": "y", "type": "string"}]
            }
        }

        validator = TypeValidator.from_dict(schema)

        # Valid input
        result = validator.validate_input({"x": 42, "y": "hello"})
        assert result == {"x": 42, "y": "hello"}

        # Type coercion
        result = validator.validate_input({"x": "42", "y": "hello"})
        assert result == {"x": 42, "y": "hello"}

        # Missing required parameter
        with pytest.raises(ValidationError, match="Required parameter missing: x"):
            validator.validate_input({"y": "hello"})

    def test_default_values(self):
        """Test default value application."""
        schema = {
            "input": {
                "parameters": [
                    {"name": "x", "type": "integer"},
                    {"name": "y", "type": "string", "default": "world"},
                ]
            }
        }

        validator = TypeValidator.from_dict(schema)

        # Default applied
        result = validator.validate_input({"x": 42})
        assert result == {"x": 42, "y": "world"}

        # Default overridden
        result = validator.validate_input({"x": 42, "y": "hello"})
        assert result == {"x": 42, "y": "hello"}

    def test_string_formats(self):
        """Test string format validation and conversion."""
        schema = {
            "input": {
                "parameters": [
                    {"name": "email", "type": "string", "format": "email"},
                    {"name": "uri", "type": "string", "format": "uri"},
                    {"name": "dt", "type": "string", "format": "date-time"},
                    {"name": "d", "type": "string", "format": "date"},
                    {"name": "t", "type": "string", "format": "time"},
                ]
            }
        }

        validator = TypeValidator.from_dict(schema)

        # Valid formats
        result = validator.validate_input(
            {
                "email": "test@example.com",
                "uri": "https://example.com",
                "dt": "2023-01-01T12:00:00Z",
                "d": "2023-01-01",
                "t": "12:00:00",
            }
        )

        assert result["email"] == "test@example.com"
        assert result["uri"] == "https://example.com"
        assert isinstance(result["dt"], datetime)
        assert isinstance(result["d"], date)
        assert isinstance(result["t"], time)

        # Invalid email
        with pytest.raises(ValidationError, match="Invalid email format"):
            validator.validate_input(
                {
                    "email": "not-an-email",
                    "uri": "https://example.com",
                    "dt": "2023-01-01T12:00:00Z",
                    "d": "2023-01-01",
                    "t": "12:00:00",
                }
            )

    def test_numeric_constraints(self):
        """Test numeric constraint validation."""
        schema = {
            "input": {
                "parameters": [
                    {"name": "age", "type": "integer", "minimum": 0, "maximum": 120},
                    {
                        "name": "score",
                        "type": "number",
                        "minimum": 0.0,
                        "maximum": 100.0,
                        "multipleOf": 0.5,
                    },
                ]
            }
        }

        validator = TypeValidator.from_dict(schema)

        # Valid values
        result = validator.validate_input({"age": 25, "score": 85.5})
        assert result == {"age": 25, "score": 85.5}

        # Invalid age (too high)
        with pytest.raises(ValidationError, match="Value must be <= 120"):
            validator.validate_input({"age": 150, "score": 85.5})

        # Invalid score (not multiple of 0.5)
        with pytest.raises(ValidationError, match="Value must be multiple of 0.5"):
            validator.validate_input({"age": 25, "score": 85.3})

    def test_array_validation(self):
        """Test array parameter validation."""
        schema = {
            "input": {
                "parameters": [
                    {
                        "name": "tags",
                        "type": "array",
                        "items": {"type": "string"},
                        "minItems": 1,
                        "maxItems": 5,
                    }
                ]
            }
        }

        validator = TypeValidator.from_dict(schema)

        # Valid array
        result = validator.validate_input({"tags": ["python", "mxcp"]})
        assert result == {"tags": ["python", "mxcp"]}

        # Too many items
        with pytest.raises(ValidationError, match="Array must have at most 5 items"):
            validator.validate_input({"tags": ["a", "b", "c", "d", "e", "f"]})

        # Empty array
        with pytest.raises(ValidationError, match="Array must have at least 1 items"):
            validator.validate_input({"tags": []})

    def test_object_validation(self):
        """Test object parameter validation."""
        schema = {
            "input": {
                "parameters": [
                    {
                        "name": "config",
                        "type": "object",
                        "properties": {
                            "host": {"type": "string"},
                            "port": {"type": "integer", "minimum": 1, "maximum": 65535},
                        },
                        "required": ["host"],
                        "additionalProperties": False,
                    }
                ]
            }
        }

        validator = TypeValidator.from_dict(schema)

        # Valid object
        result = validator.validate_input({"config": {"host": "localhost", "port": 8080}})
        assert result == {"config": {"host": "localhost", "port": 8080}}

        # Missing required property
        with pytest.raises(ValidationError, match="Missing required properties: host"):
            validator.validate_input({"config": {"port": 8080}})

        # Unexpected property
        with pytest.raises(ValidationError, match="Unexpected property: extra"):
            validator.validate_input(
                {"config": {"host": "localhost", "port": 8080, "extra": "value"}}
            )

    def test_enum_validation(self):
        """Test enum constraint validation."""
        schema = {
            "input": {
                "parameters": [
                    {"name": "status", "type": "string", "enum": ["active", "inactive", "pending"]}
                ]
            }
        }

        validator = TypeValidator.from_dict(schema)

        # Valid enum value
        result = validator.validate_input({"status": "active"})
        assert result == {"status": "active"}

        # Invalid enum value
        with pytest.raises(ValidationError, match="Must be one of"):
            validator.validate_input({"status": "invalid"})

    def test_output_validation(self):
        """Test output validation."""
        schema = {
            "output": {
                "type": "object",
                "properties": {"id": {"type": "integer"}, "name": {"type": "string"}},
                "required": ["id", "name"],
            }
        }

        validator = TypeValidator.from_dict(schema)

        # Valid output
        result = validator.validate_output({"id": 1, "name": "test"})
        assert result == {"id": 1, "name": "test"}

        # Missing required field
        with pytest.raises(ValidationError, match="Missing required properties: name"):
            validator.validate_output({"id": 1})

    def test_dataframe_output(self):
        """Test DataFrame output validation."""
        schema = {
            "output": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {"id": {"type": "integer"}, "name": {"type": "string"}},
                },
            }
        }

        validator = TypeValidator.from_dict(schema)

        # DataFrame validates as array of objects
        df = pd.DataFrame([{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}])

        result = validator.validate_output(df)
        assert result == [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}]

    def test_series_output(self):
        """Test Series output validation."""
        schema = {"output": {"type": "array", "items": {"type": "number"}}}

        validator = TypeValidator.from_dict(schema)

        # Series validates as array
        series = pd.Series([1.0, 2.0, 3.0])
        result = validator.validate_output(series)
        assert result == [1.0, 2.0, 3.0]

    def test_sensitive_field_masking(self):
        """Test sensitive field masking."""
        schema = {
            "output": {
                "type": "object",
                "properties": {
                    "username": {"type": "string"},
                    "password": {"type": "string", "sensitive": True},
                    "balance": {"type": "number", "sensitive": True},
                },
            }
        }

        validator = TypeValidator.from_dict(schema)

        # Mask sensitive fields
        result = validator.mask_sensitive_output(
            {"username": "alice", "password": "secret123", "balance": 1000.0}
        )

        assert result == {"username": "alice", "password": "[REDACTED]", "balance": "[REDACTED]"}

    def test_nested_sensitive_fields(self):
        """Test masking of nested sensitive fields."""
        schema = {
            "output": {
                "type": "object",
                "properties": {
                    "user": {
                        "type": "object",
                        "properties": {"name": {"type": "string"}, "email": {"type": "string"}},
                    },
                    "credentials": {
                        "type": "object",
                        "sensitive": True,
                        "properties": {"token": {"type": "string"}, "secret": {"type": "string"}},
                    },
                },
            }
        }

        validator = TypeValidator.from_dict(schema)

        result = validator.mask_sensitive_output(
            {
                "user": {"name": "Alice", "email": "alice@example.com"},
                "credentials": {"token": "abc123", "secret": "xyz789"},
            }
        )

        assert result == {
            "user": {"name": "Alice", "email": "alice@example.com"},
            "credentials": "[REDACTED]",
        }

    def test_datetime_serialization(self):
        """Test datetime object serialization."""
        schema = {
            "output": {
                "type": "object",
                "properties": {
                    "created_at": {"type": "string", "format": "date-time"},
                    "date": {"type": "string", "format": "date"},
                    "time": {"type": "string", "format": "time"},
                },
            }
        }

        validator = TypeValidator.from_dict(schema)

        now = datetime.now()
        today = date.today()
        current_time = time(12, 30, 45)

        result = validator.validate_output({"created_at": now, "date": today, "time": current_time})

        assert result["created_at"] == now.isoformat()
        assert result["date"] == today.isoformat()
        assert result["time"] == current_time.isoformat()

    def test_strict_mode(self):
        """Test strict mode (no type coercion)."""
        schema = {"input": {"parameters": [{"name": "x", "type": "integer"}]}}

        # With coercion (default)
        validator = TypeValidator.from_dict(schema, strict=False)
        result = validator.validate_input({"x": "42"})
        assert result == {"x": 42}

        # Without coercion (strict)
        TypeValidator.from_dict(schema, strict=True)
        # In strict mode, string "42" should not be coerced to int
        # This would need to be implemented in the TypeConverter

    def test_unknown_parameter(self):
        """Test handling of unknown parameters."""
        schema = {"input": {"parameters": [{"name": "x", "type": "integer"}]}}

        validator = TypeValidator.from_dict(schema)

        with pytest.raises(ValidationError, match="Unknown parameter: y"):
            validator.validate_input({"x": 42, "y": "extra"})

    def test_empty_schema(self):
        """Test validator with empty schema."""
        validator = TypeValidator.from_dict({})

        # No validation performed
        assert validator.validate_input({"any": "value"}) == {"any": "value"}
        assert validator.validate_output({"any": "output"}) == {"any": "output"}


class TestSchemaRetrieval:
    """Test get_input_schema and get_output_schema methods."""

    def test_get_input_schema_with_all_fields(self):
        """Test that get_input_schema returns all parameter fields."""
        schema = {
            "input": {
                "parameters": [
                    {
                        "name": "config",
                        "type": "object",
                        "description": "Configuration object",
                        "default": {"debug": False},
                        "examples": [{"debug": True}, {"debug": False}],
                        "sensitive": True,
                        "properties": {
                            "debug": {"type": "boolean"},
                            "timeout": {"type": "integer"},
                        },
                        "required": ["debug"],
                    },
                    {
                        "name": "count",
                        "type": "integer",
                        "minimum": 0,
                        "maximum": 100,
                        "exclusiveMinimum": -1,
                        "exclusiveMaximum": 101,
                        "multipleOf": 5,
                    },
                    {
                        "name": "tags",
                        "type": "array",
                        "minItems": 1,
                        "maxItems": 10,
                        "uniqueItems": True,
                        "items": {"type": "string"},
                    },
                ]
            }
        }

        validator = TypeValidator.from_dict(schema)
        input_schema = validator.get_input_schema()

        assert input_schema is not None
        assert len(input_schema) == 3

        # Check first parameter has all fields including parameter-specific ones
        config_param = input_schema[0]
        assert config_param["name"] == "config"
        assert config_param["type"] == "object"
        assert config_param["description"] == "Configuration object"
        assert config_param["default"] == {"debug": False}
        assert config_param["examples"] == [{"debug": True}, {"debug": False}]
        assert config_param["sensitive"] is True
        assert "properties" in config_param
        assert "required" in config_param

        # Check numeric constraints are included
        count_param = input_schema[1]
        assert count_param["name"] == "count"
        assert count_param["minimum"] == 0
        assert count_param["maximum"] == 100
        assert count_param["multipleOf"] == 5

        # Check array constraints are included
        tags_param = input_schema[2]
        assert tags_param["minItems"] == 1
        assert tags_param["maxItems"] == 10
        assert tags_param["uniqueItems"] is True
        assert "items" in tags_param

    def test_get_output_schema_with_all_fields(self):
        """Test that get_output_schema returns all type fields."""
        schema = {
            "output": {
                "type": "object",
                "description": "Response object",
                "sensitive": True,
                "properties": {
                    "results": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "id": {"type": "integer"},
                                "score": {"type": "number", "minimum": 0, "maximum": 100},
                            },
                            "required": ["id", "score"],
                        },
                        "minItems": 0,
                        "maxItems": 100,
                    },
                    "message": {"type": "string", "minLength": 1, "maxLength": 500},
                },
                "required": ["results"],
                "additionalProperties": False,
            }
        }

        validator = TypeValidator.from_dict(schema)
        output_schema = validator.get_output_schema()

        assert output_schema is not None
        # Check top-level fields
        assert output_schema["type"] == "object"
        assert output_schema["description"] == "Response object"
        assert output_schema["sensitive"] is True
        assert output_schema["additionalProperties"] is False
        assert output_schema["required"] == ["results"]

        # Check nested structure
        assert "properties" in output_schema
        assert "results" in output_schema["properties"]
        results_schema = output_schema["properties"]["results"]
        assert results_schema["type"] == "array"
        assert results_schema["minItems"] == 0
        assert results_schema["maxItems"] == 100

        # Check deeply nested constraints
        assert "items" in results_schema
        assert results_schema["items"]["type"] == "object"
        assert "properties" in results_schema["items"]
        assert results_schema["items"]["properties"]["score"]["minimum"] == 0
        assert results_schema["items"]["properties"]["score"]["maximum"] == 100

    def test_schema_methods_are_consistent(self):
        """Test that input and output schema methods use consistent field naming."""
        schema = {
            "input": {
                "parameters": [
                    {
                        "name": "text",
                        "type": "string",
                        "minLength": 5,  # JSON Schema style
                        "maxLength": 100,
                    }
                ]
            },
            "output": {"type": "array", "minItems": 1, "maxItems": 50},  # JSON Schema style
        }

        validator = TypeValidator.from_dict(schema)

        # Both should use JSON Schema field names (camelCase)
        input_schema = validator.get_input_schema()
        output_schema = validator.get_output_schema()

        assert input_schema is not None
        assert output_schema is not None

        # Check input uses camelCase
        assert "minLength" in input_schema[0]
        assert "maxLength" in input_schema[0]
        assert "min_length" not in input_schema[0]

        # Check output uses camelCase
        assert "minItems" in output_schema
        assert "maxItems" in output_schema
        assert "min_items" not in output_schema

    def test_empty_schemas(self):
        """Test get methods with empty schemas."""
        validator = TypeValidator.from_dict({})

        assert validator.get_input_schema() is None
        assert validator.get_output_schema() is None
