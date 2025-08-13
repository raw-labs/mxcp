"""Tests for parameter name validation."""

import pytest

from mxcp.sdk.validator import TypeValidator
from mxcp.sdk.validator.loaders import validate_schema_structure


class TestParameterNameValidation:
    """Test parameter name pattern validation."""

    def test_valid_parameter_names(self):
        """Test that valid parameter names are accepted."""
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
            schema = {"input": {"parameters": [{"name": name, "type": "string"}]}}
            # Should not raise
            validate_schema_structure(schema)

    def test_invalid_parameter_names(self):
        """Test that invalid parameter names are rejected."""
        invalid_names = [
            "123name",  # starts with number
            "name-with-dash",  # contains dash
            "name.with.dot",  # contains dot
            "name with space",  # contains space
            "name@symbol",  # contains @
            "",  # empty string
            "name$var",  # contains $
            "name!",  # contains !
            "日本語",  # non-ASCII
        ]

        # Note: "class" is actually a valid parameter name according to the pattern
        # The pattern just requires [a-zA-Z_][a-zA-Z0-9_]* which allows reserved words

        for name in invalid_names:
            schema = {"input": {"parameters": [{"name": name, "type": "string"}]}}

            # Should raise validation error
            with pytest.raises(ValueError) as exc_info:
                validate_schema_structure(schema)

            # Check that it's specifically about the name pattern or length
            assert "does not match" in str(exc_info.value), f"Name '{name}' error: {exc_info.value}"

    def test_parameter_name_in_validator(self):
        """Test that TypeValidator correctly handles parameter names."""
        # Valid parameter name
        validator = TypeValidator.from_dict(
            {"input": {"parameters": [{"name": "user_id", "type": "integer"}]}}
        )

        result = validator.validate_input({"user_id": 123})
        assert result == {"user_id": 123}

        # The validator itself doesn't validate parameter names at runtime
        # It trusts that the schema is valid (validated by JSON schema)
        # So we can still use invalid names if we bypass schema validation
        validator_direct = TypeValidator.from_dict(
            {
                "input": {
                    "parameters": [
                        {
                            "name": "123invalid",  # Would fail JSON schema validation
                            "type": "string",
                        }
                    ]
                }
            }
        )

        # But it will still work at runtime
        result = validator_direct.validate_input({"123invalid": "test"})
        assert result == {"123invalid": "test"}
