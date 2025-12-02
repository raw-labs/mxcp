"""Tests for parameter name validation."""

import pytest

from mxcp.sdk.validator import TypeValidator


class TestParameterNameValidation:
    """Test parameter name pattern validation."""

    def test_valid_parameter_names(self):
        """Test that valid parameter names are accepted in TypeValidator."""
        valid_names = [
            "name",
            "user_id",
            "_private",
            "camelCase",
            "snake_case",
            "CONSTANT_NAME",
            "name123",
            "_123name",
            "a",
            "A",
            "_",
        ]

        for name in valid_names:
            validator = TypeValidator.from_dict(
                {"input": {"parameters": [{"name": name, "type": "string"}]}}
            )
            result = validator.validate_input({name: "test"})
            assert result == {name: "test"}

    def test_parameter_name_in_validator(self):
        """Test that TypeValidator correctly handles parameter names."""
        # Valid parameter name
        validator = TypeValidator.from_dict(
            {"input": {"parameters": [{"name": "user_id", "type": "integer"}]}}
        )

        result = validator.validate_input({"user_id": 123})
        assert result == {"user_id": 123}

    def test_parameter_with_default(self):
        """Test that parameters with defaults work correctly."""
        validator = TypeValidator.from_dict(
            {
                "input": {
                    "parameters": [
                        {"name": "required_param", "type": "string"},
                        {"name": "optional_param", "type": "integer", "default": 42},
                    ]
                }
            }
        )

        # Test with only required param
        result = validator.validate_input({"required_param": "test"})
        assert result["required_param"] == "test"
        assert result["optional_param"] == 42

        # Test with both params
        result = validator.validate_input({"required_param": "test", "optional_param": 100})
        assert result["required_param"] == "test"
        assert result["optional_param"] == 100
