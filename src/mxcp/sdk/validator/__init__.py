"""MXCP SDK Validator - OpenAPI-style type validation and conversion.

This module provides core type validation functionality used by MXCP internally:
- Input parameter validation with default values and constraints
- Output result validation with schema compliance
- Type conversion between Python and OpenAPI types
- Sensitive field masking and data protection

## Key Components

### Core Classes
- `TypeValidator`: Main validation engine for inputs and outputs
- `TypeConverter`: Handles type conversion and coercion
- `ValidationError`: Exception raised for validation failures

### Schema Types
- `ValidationSchema`: Complete validation configuration
- `ParameterSchema`: Individual parameter definition
- `TypeSchema`: Type definitions (string, number, object, array, etc.)

## High-Level Decorators

For decorator-based validation and schema loading utilities, see the
`mxcp.sdk.validator.decorators` submodule:

```python
from mxcp.sdk.validator.decorators import validate, validate_input, validate_output
```

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
]
