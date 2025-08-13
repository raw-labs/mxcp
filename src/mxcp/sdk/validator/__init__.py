"""MXCP SDK Validator - OpenAPI-style type validation and conversion.

This module provides comprehensive type validation functionality including:
- Input parameter validation with default values and constraints
- Output result validation with schema compliance
- Type conversion between Python and OpenAPI types
- Sensitive field masking and data protection
- Validation decorators for functions and methods
- Schema loading from files and validation

## Key Components

### Core Classes
- `TypeValidator`: Main validation engine for inputs and outputs
- `TypeConverter`: Handles type conversion and coercion
- `ValidationError`: Exception raised for validation failures

### Schema Types
- `ValidationSchema`: Complete validation configuration
- `ParameterSchema`: Individual parameter definition
- `TypeSchema`: Type definitions (string, number, object, array, etc.)

### Decorators
- `@validate`: Full validation decorator with input and output schemas
- `@validate_input`: Validate only input parameters
- `@validate_output`: Validate only output results
- `@validate_strict`: Strict validation with no type coercion

### Schema Loading
- `load_schema`: Load schema from string content
- `load_schema_from_file`: Load schema from YAML/JSON file
- `validate_schema_structure`: Validate schema structure

## Quick Examples

### Input Validation
```python
from mxcp.sdk.validator import TypeValidator, ValidationSchema

# Define validation schema
schema = ValidationSchema(
    parameters=[
        {
            "name": "user_id",
            "type": "string",
            "required": True,
            "pattern": "^user_[0-9]+$"
        },
        {
            "name": "limit",
            "type": "integer",
            "default": 10,
            "minimum": 1,
            "maximum": 100
        }
    ]
)

# Validate inputs
validator = TypeValidator(schema)
validated_params = validator.validate_input({
    "user_id": "user_123",
    "limit": 25
})
# Returns: {"user_id": "user_123", "limit": 25}
```

### Output Validation
```python
# Define output schema
schema = ValidationSchema(
    return_type={
        "type": "object",
        "properties": {
            "users": {"type": "array", "items": {"type": "object"}},
            "total": {"type": "integer"},
            "sensitive_data": {"type": "string", "sensitive": True}
        }
    }
)

# Validate and mask sensitive output
result = {
    "users": [{"name": "Alice"}, {"name": "Bob"}],
    "total": 2,
    "sensitive_data": "secret-value"
}

validator = TypeValidator(schema)
validated_output = validator.validate_output(result)
# sensitive_data is automatically masked: "[REDACTED]"
```

### Using Decorators
```python
from mxcp.sdk.validator import validate

# Inline schema validation
@validate(
    input_schema=[
        {"name": "user_id", "type": "string", "required": True},
        {"name": "limit", "type": "integer", "default": 10}
    ],
    output_schema={"type": "array", "items": {"type": "object"}}
)
def get_users(user_id: str, limit: int = 10) -> list[dict]:
    return [{"id": user_id, "name": "User"}]

# Schema from file
@validate.from_file("schemas/my_function.yaml")
def my_function(x: int) -> str:
    return str(x)
```
"""

from ._types import (
    BaseTypeSchema,
    ParameterSchema,
    TypeSchema,
    ValidationSchema,
)
from .converters import (
    TypeConverter,
    ValidationError,
)
from .core import TypeValidator
from .decorators import validate, validate_input, validate_output, validate_strict
from .loaders import load_schema, load_schema_from_file, validate_schema_structure

__all__ = [
    # Types
    "BaseTypeSchema",
    "TypeSchema",
    "ParameterSchema",
    "ValidationSchema",
    # Converter classes
    "TypeConverter",
    "ValidationError",
    # Core validator
    "TypeValidator",
    # Decorators
    "validate",
    "validate_input",
    "validate_output",
    "validate_strict",
    # Loaders
    "load_schema",
    "load_schema_from_file",
    "validate_schema_structure",
]
