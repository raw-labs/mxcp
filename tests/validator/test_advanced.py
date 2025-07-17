"""Advanced tests for validator functionality."""

import pytest
from datetime import date
from mxcp.sdk.validator import TypeValidator, ValidationError
from mxcp.validator import validate


class TestAdvancedValidation:
    """Test advanced validation scenarios."""
    
    def test_complex_nested_order_structure(self):
        """Test validation of complex nested structures like orders."""
        @validate(
            input_schema=[{
                "name": "order",
                "type": "object",
                "properties": {
                    "customer": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "email": {"type": "string", "format": "email"}
                        },
                        "required": ["name", "email"]
                    },
                    "items": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "product_id": {"type": "integer"},
                                "quantity": {"type": "integer", "minimum": 1},
                                "price": {"type": "number", "minimum": 0}
                            },
                            "required": ["product_id", "quantity", "price"]
                        },
                        "minItems": 1
                    }
                },
                "required": ["customer", "items"]
            }]
        )
        def process_order(order: dict) -> dict:
            total = sum(item["quantity"] * item["price"] for item in order["items"])
            return {
                "order_id": 12345,
                "customer_email": order["customer"]["email"],
                "total": total,
                "status": "processed"
            }
        
        # Valid order
        order_data = {
            "customer": {
                "name": "John Doe",
                "email": "john@example.com"
            },
            "items": [
                {"product_id": 101, "quantity": 2, "price": 29.99},
                {"product_id": 102, "quantity": 1, "price": 49.99}
            ]
        }
        result = process_order(order_data)
        assert result["total"] == 109.97
        assert result["customer_email"] == "john@example.com"
        
        # Invalid - missing customer email
        with pytest.raises(ValidationError, match="Missing required properties: email"):
            process_order({
                "customer": {"name": "John"},
                "items": [{"product_id": 1, "quantity": 1, "price": 10}]
            })
        
        # Invalid - empty items array
        with pytest.raises(ValidationError, match="Array must have at least 1 items"):
            process_order({
                "customer": {"name": "John", "email": "john@example.com"},
                "items": []
            })
    
    def test_direct_validator_usage(self):
        """Test using TypeValidator directly without decorator."""
        # Create validator
        validator = TypeValidator.from_dict({
            "input": {
                "parameters": [
                    {"name": "items", "type": "array", "items": {"type": "string"}},
                    {"name": "max_length", "type": "integer", "minimum": 1}
                ]
            },
            "output": {
                "type": "array",
                "items": {"type": "string"}
            }
        })
        
        # Validate input
        params = {"items": ["apple", "banana", "cherry"], "max_length": 6}
        validated_params = validator.validate_input(params)
        
        # Process
        result = [item for item in validated_params["items"] 
                 if len(item) <= validated_params["max_length"]]
        
        # Validate output
        validated_output = validator.validate_output(result)
        assert validated_output == ["apple", "banana", "cherry"]
        
        # Test with filtering
        params2 = {"items": ["apple", "watermelon", "kiwi"], "max_length": 5}
        validated_params2 = validator.validate_input(params2)
        result2 = [item for item in validated_params2["items"] 
                  if len(item) <= validated_params2["max_length"]]
        assert validator.validate_output(result2) == ["apple", "kiwi"]
    
    def test_date_format_conversion(self):
        """Test date format conversion and validation."""
        # Direct validator test
        validator = TypeValidator.from_dict({
            "input": {
                "parameters": [
                    {"name": "date_str", "type": "string", "format": "date"}
                ]
            }
        })
        
        # Valid date string
        result = validator.validate_input({"date_str": "2024-01-15"})
        converted_date = result["date_str"]
        assert isinstance(converted_date, date)
        assert converted_date.year == 2024
        assert converted_date.month == 1
        assert converted_date.day == 15
        
        # Invalid date format
        with pytest.raises((ValidationError, ValueError)):
            validator.validate_input({"date_str": "15/01/2024"})
        
        with pytest.raises((ValidationError, ValueError)):
            validator.validate_input({"date_str": "2024-13-01"})  # Invalid month
    
    def test_sensitive_data_in_nested_structures(self):
        """Test sensitive data handling in complex nested structures."""
        validator = TypeValidator.from_dict({
            "output": {
                "type": "object",
                "properties": {
                    "user": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "integer"},
                            "profile": {
                                "type": "object",
                                "properties": {
                                    "name": {"type": "string"},
                                    "ssn": {"type": "string", "sensitive": True}
                                }
                            }
                        }
                    },
                    "account": {
                        "type": "object",
                        "sensitive": True,
                        "properties": {
                            "number": {"type": "string"},
                            "balance": {"type": "number"}
                        }
                    }
                }
            }
        })
        
        data = {
            "user": {
                "id": 123,
                "profile": {
                    "name": "Alice",
                    "ssn": "123-45-6789"
                }
            },
            "account": {
                "number": "ACC-12345",
                "balance": 1500.00
            }
        }
        
        # Validate normally
        validated = validator.validate_output(data)
        assert validated["user"]["profile"]["ssn"] == "123-45-6789"
        
        # Mask sensitive data
        masked = validator.mask_sensitive_output(data)
        assert masked["user"]["profile"]["ssn"] == "[REDACTED]"
        assert masked["account"] == "[REDACTED]"  # Entire object is sensitive
    
    def test_array_string_filtering(self):
        """Test array validation with string length constraints."""
        @validate(
            input_schema=[{
                "name": "words",
                "type": "array",
                "items": {
                    "type": "string",
                    "minLength": 3,
                    "maxLength": 10
                },
                "minItems": 1
            }]
        )
        def filter_words(words: list) -> list:
            return [w.upper() for w in words]
        
        # Valid input
        result = filter_words(["hello", "world", "python"])
        assert result == ["HELLO", "WORLD", "PYTHON"]
        
        # Invalid - word too short
        with pytest.raises(ValidationError, match="String must be at least 3 characters"):
            filter_words(["hi", "world"])
        
        # Invalid - word too long
        with pytest.raises(ValidationError, match="String must be at most 10 characters"):
            filter_words(["hello", "verylongwordhere"])
        
        # Invalid - empty array
        with pytest.raises(ValidationError, match="Array must have at least 1 items"):
            filter_words([])
    
    def test_mixed_type_coercion(self):
        """Test type coercion with mixed input types."""
        @validate(
            input_schema=[
                {"name": "count", "type": "integer"},
                {"name": "price", "type": "number"},
                {"name": "active", "type": "boolean"}
            ]
        )
        def process_data(count: int, price: float, active: bool) -> dict:
            return {
                "count": count,
                "price": price,
                "active": active,
                "total": count * price if active else 0
            }
        
        # String to number conversions
        result = process_data("5", "19.99", "true")  # type: ignore
        assert result["count"] == 5
        assert result["price"] == 19.99
        assert result["active"] is True
        assert abs(result["total"] - 99.95) < 0.0001  # Float precision
        
        # Boolean string variations - only "true" (case-insensitive) converts to True
        assert process_data("1", "10", "true")["active"] is True  # type: ignore
        assert process_data("1", "10", "True")["active"] is True  # type: ignore
        assert process_data("1", "10", "TRUE")["active"] is True  # type: ignore
        
        # Any other string converts to False
        assert process_data("1", "10", "false")["active"] is False  # type: ignore
        assert process_data("1", "10", "yes")["active"] is False  # type: ignore
        assert process_data("1", "10", "1")["active"] is False  # type: ignore
        assert process_data("1", "10", "")["active"] is False  # type: ignore 