"""Tests for mxcp.validator.decorators module."""

import asyncio

import pytest

from mxcp.sdk.validator import ValidationError
from mxcp.validator import validate


class TestValidateDecorator:
    """Test the validate decorator."""

    def test_sync_function_validation(self):
        """Test validation on synchronous functions."""

        @validate(
            input_schema=[
                {"name": "x", "type": "integer", "minimum": 0},
                {"name": "y", "type": "integer", "minimum": 0},
            ],
            output_schema={"type": "integer", "minimum": 0},
        )
        def add(x: int, y: int) -> int:
            return x + y

        # Valid call
        assert add(2, 3) == 5

        # Type coercion
        assert add("2", "3") == 5

        # Invalid input (negative)
        with pytest.raises(ValidationError, match="Value must be >= 0"):
            add(-1, 3)

    def test_async_function_validation(self):
        """Test validation on asynchronous functions."""

        @validate(
            input_schema=[
                {"name": "name", "type": "string", "minLength": 1},
                {"name": "age", "type": "integer", "minimum": 0},
            ],
            output_schema={"type": "object", "properties": {"message": {"type": "string"}}},
        )
        async def greet(name: str, age: int) -> dict:
            return {"message": f"Hello {name}, you are {age} years old"}

        # Valid call
        result = asyncio.run(greet("Alice", 25))
        assert result == {"message": "Hello Alice, you are 25 years old"}

        # Invalid input (empty name)
        with pytest.raises(ValidationError, match="String must be at least 1 characters long"):
            asyncio.run(greet("", 25))

    def test_decorator_with_defaults(self):
        """Test decorator with default parameter values."""

        @validate(
            input_schema=[
                {"name": "x", "type": "number"},
                {"name": "y", "type": "number", "default": 1.0},
            ]
        )
        def multiply(x: float, y: float = 1.0) -> float:
            return x * y

        # With default
        assert multiply(5) == 5.0

        # Override default
        assert multiply(5, 2) == 10.0

    def test_decorator_with_mixed_args(self):
        """Test decorator with mixed positional and keyword arguments."""

        @validate(
            input_schema=[
                {"name": "a", "type": "integer"},
                {"name": "b", "type": "integer"},
                {"name": "c", "type": "integer", "default": 0},
            ]
        )
        def compute(a: int, b: int, c: int = 0) -> int:
            return a + b + c

        # Positional args
        assert compute(1, 2) == 3
        assert compute(1, 2, 3) == 6

        # Keyword args
        assert compute(a=1, b=2) == 3
        assert compute(1, b=2, c=3) == 6

        # Mixed
        assert compute(1, 2, c=3) == 6

    def test_output_only_validation(self):
        """Test validation of output only."""

        @validate(output_schema={"type": "array", "items": {"type": "string"}, "minItems": 1})
        def get_names() -> list:
            return ["Alice", "Bob"]

        # Valid output
        assert get_names() == ["Alice", "Bob"]

        # Test with invalid output
        @validate(output_schema={"type": "array", "items": {"type": "string"}, "minItems": 1})
        def get_empty() -> list:
            return []

        with pytest.raises(ValidationError, match="Array must have at least 1 items"):
            get_empty()

    def test_input_only_validation(self):
        """Test validation of input only."""

        @validate(input_schema=[{"name": "email", "type": "string", "format": "email"}])
        def process_email(email: str) -> str:
            return f"Processing {email}"

        # Valid email
        assert process_email("test@example.com") == "Processing test@example.com"

        # Invalid email
        with pytest.raises(ValidationError, match="Invalid email format"):
            process_email("not-an-email")

    def test_complex_nested_validation(self):
        """Test validation of complex nested structures."""

        @validate(
            input_schema=[
                {
                    "name": "user",
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "preferences": {
                            "type": "object",
                            "properties": {
                                "theme": {"type": "string", "enum": ["light", "dark"]},
                                "notifications": {"type": "boolean"},
                            },
                            "required": ["theme"],
                        },
                    },
                    "required": ["name", "preferences"],
                }
            ],
            output_schema={
                "type": "object",
                "properties": {"status": {"type": "string"}, "user_id": {"type": "integer"}},
            },
        )
        def create_user(user: dict) -> dict:
            return {"status": "created", "user_id": 123}

        # Valid input
        result = create_user(
            {"name": "Alice", "preferences": {"theme": "dark", "notifications": True}}
        )
        assert result == {"status": "created", "user_id": 123}

        # Missing required nested field
        with pytest.raises(ValidationError, match="Missing required properties: theme"):
            create_user({"name": "Alice", "preferences": {"notifications": True}})

    def test_no_signature_validation(self):
        """Test decorator without signature validation."""

        # This should not raise an error even though function has extra params
        @validate(input_schema=[{"name": "x", "type": "integer"}], validate_signature=False)
        def func(x: int, y: int) -> int:
            return x + y

        # Only x is validated, y is passed through
        result = func(x=5, y=10)
        assert result == 15

    def test_class_method_validation(self):
        """Test validation on class methods."""

        class Calculator:
            @validate(
                input_schema=[{"name": "x", "type": "number"}, {"name": "y", "type": "number"}],
                output_schema={"type": "number"},
            )
            def add(self, x: float, y: float) -> float:
                return x + y

        calc = Calculator()
        assert calc.add(2.5, 3.5) == 6.0

        # Type validation still works
        assert calc.add("2.5", "3.5") == 6.0
