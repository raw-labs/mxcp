"""Tests for JSON schema compatibility with endpoint schemas."""

import pytest
import json
from pathlib import Path
from mxcp.validator import TypeValidator, ValidationError
from mxcp.validator.loaders import validate_schema_structure


class TestSchemaCompatibility:
    """Test that validator works with MXCP endpoint schemas."""
    
    def test_endpoint_schema_structure(self):
        """Test that we can validate against endpoint schema structures."""
        # Example tool endpoint structure
        tool_endpoint = {
            "mxcp": 1,
            "tool": {
                "name": "add_numbers",
                "description": "Add two numbers",
                "parameters": [
                    {
                        "name": "a",
                        "type": "number",
                        "description": "First number"
                    },
                    {
                        "name": "b", 
                        "type": "number",
                        "description": "Second number"
                    }
                ],
                "return": {
                    "type": "number",
                    "description": "Sum of the numbers"
                }
            }
        }
        
        # Extract validation schema from endpoint
        validation_schema = {
            "input": {
                "parameters": tool_endpoint["tool"]["parameters"]
            },
            "output": tool_endpoint["tool"].get("return")
        }
        
        # Should create validator successfully
        validator = TypeValidator.from_dict(validation_schema)
        
        # Validate input
        result = validator.validate_input({"a": 5, "b": 3})
        assert result == {"a": 5.0, "b": 3.0}
        
        # Validate output
        output = validator.validate_output(8.0)
        assert output == 8.0
    
    def test_resource_endpoint_validation(self):
        """Test validation with resource endpoint structure."""
        resource_endpoint = {
            "mxcp": 1,
            "resource": {
                "uri": "users://{user_id}/profile",
                "description": "Get user profile",
                "parameters": [
                    {
                        "name": "user_id",
                        "type": "integer",
                        "minimum": 1,
                        "description": "User ID"
                    }
                ],
                "return": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "integer"},
                        "name": {"type": "string"},
                        "email": {"type": "string", "format": "email"}
                    },
                    "required": ["id", "name", "email"]
                }
            }
        }
        
        # Extract validation schema
        validation_schema = {
            "input": {
                "parameters": resource_endpoint["resource"]["parameters"]
            },
            "output": resource_endpoint["resource"].get("return")
        }
        
        validator = TypeValidator.from_dict(validation_schema)
        
        # Validate input
        result = validator.validate_input({"user_id": 123})
        assert result == {"user_id": 123}
        
        # Invalid user_id (< 1)
        with pytest.raises(ValidationError, match="Value must be >= 1"):
            validator.validate_input({"user_id": 0})
        
        # Validate output
        user_data = {
            "id": 123,
            "name": "Alice",
            "email": "alice@example.com"
        }
        validated = validator.validate_output(user_data)
        assert validated == user_data
        
        # Missing required field
        with pytest.raises(ValidationError, match="Missing required properties: email"):
            validator.validate_output({"id": 123, "name": "Alice"})
    
    def test_prompt_endpoint_validation(self):
        """Test validation with prompt endpoint structure."""
        prompt_endpoint = {
            "mxcp": 1,
            "prompt": {
                "name": "analyze_code",
                "description": "Analyze code snippet",
                "parameters": [
                    {
                        "name": "code",
                        "type": "string",
                        "description": "Code to analyze"
                    },
                    {
                        "name": "language",
                        "type": "string",
                        "enum": ["python", "javascript", "java"],
                        "description": "Programming language"
                    }
                ],
                "messages": [
                    {
                        "role": "user",
                        "prompt": "Analyze this {{language}} code:\n\n{{code}}"
                    }
                ]
            }
        }
        
        # Extract validation schema (prompts typically only have input)
        validation_schema = {
            "input": {
                "parameters": prompt_endpoint["prompt"]["parameters"]
            }
        }
        
        validator = TypeValidator.from_dict(validation_schema)
        
        # Valid input
        result = validator.validate_input({
            "code": "def hello(): pass",
            "language": "python"
        })
        assert result["language"] == "python"
        
        # Invalid language
        with pytest.raises(ValidationError, match="Must be one of"):
            validator.validate_input({
                "code": "function hello() {}",
                "language": "typescript"  # Not in enum
            })
    
    def test_complex_type_definitions(self):
        """Test validation with complex nested type definitions."""
        schema = {
            "input": {
                "parameters": [
                    {
                        "name": "config",
                        "type": "object",
                        "properties": {
                            "database": {
                                "type": "object",
                                "properties": {
                                    "host": {"type": "string"},
                                    "port": {"type": "integer", "minimum": 1, "maximum": 65535},
                                    "credentials": {
                                        "type": "object",
                                        "sensitive": True,
                                        "properties": {
                                            "username": {"type": "string"},
                                            "password": {"type": "string", "sensitive": True}
                                        },
                                        "required": ["username", "password"]
                                    }
                                },
                                "required": ["host", "port", "credentials"]
                            },
                            "features": {
                                "type": "array",
                                "items": {"type": "string"},
                                "minItems": 1
                            }
                        },
                        "required": ["database"]
                    }
                ]
            }
        }
        
        validator = TypeValidator.from_dict(schema)
        
        # Valid complex input
        config = {
            "config": {
                "database": {
                    "host": "localhost",
                    "port": 5432,
                    "credentials": {
                        "username": "admin",
                        "password": "secret123"
                    }
                },
                "features": ["logging", "monitoring"]
            }
        }
        
        result = validator.validate_input(config)
        assert result["config"]["database"]["port"] == 5432
        
        # Test sensitive field masking
        # Create a new validator for sensitive data masking
        sensitive_schema = {
            "output": {
                "type": "object",
                "properties": {
                    "username": {"type": "string"},
                    "password": {"type": "string", "sensitive": True}
                },
                "sensitive": True  # Entire object is sensitive
            }
        }
        validator2 = TypeValidator.from_dict(sensitive_schema)
        
        masked = validator2.mask_sensitive_output({
            "username": "admin",
            "password": "secret123"
        })
        assert masked == "[REDACTED]"  # Entire object marked as sensitive
    
    def test_schema_structure_validation(self):
        """Test the schema structure validation function."""
        # Valid schema
        valid_schema = {
            "input": {
                "parameters": [
                    {"name": "x", "type": "integer"}
                ]
            },
            "output": {
                "type": "string"
            }
        }
        
        # Should not raise
        validate_schema_structure(valid_schema)
        
        # Invalid - missing type in parameter
        invalid_schema = {
            "input": {
                "parameters": [
                    {"name": "x"}  # Missing type
                ]
            }
        }
        
        with pytest.raises(ValueError, match="'type' is a required property"):
            validate_schema_structure(invalid_schema)
        
        # Invalid - parameters not a list
        invalid_schema2 = {
            "input": {
                "parameters": {"x": {"type": "integer"}}  # Should be list
            }
        }
        
        with pytest.raises(ValueError, match="Schema validation error"):
            validate_schema_structure(invalid_schema2) 