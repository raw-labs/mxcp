"""
MXCP Type Validator

A standalone validation module for MXCP's type system. Provides pure type validation 
without metadata like tool hints or titles. Language-agnostic with JSON/YAML specs.

## Features

- Complete MXCP type system support (OpenAPI-style with restrictions)
- DataFrame/SQL compatibility (DataFrames validate as array of objects)  
- Sensitive data marking and masking
- Multiple usage patterns (decorators, file-based, direct validation)
- Strict mode for unknown parameters
- Function signature validation

## Basic Usage

```python
from mxcp.validator import TypeValidator, validate, ValidationError

# Direct validation
validator = TypeValidator.from_dict({
    "input": {
        "parameters": [
            {"name": "age", "type": "integer", "minimum": 0, "maximum": 150},
            {"name": "email", "type": "string", "format": "email"}
        ]
    },
    "output": {"type": "string"}
})

# Validate input
result = validator.validate_input({"age": 25, "email": "user@example.com"})

# Validate output  
output = validator.validate_output("Success!")

# Using decorators
@validate({
    "input": {
        "parameters": [
            {"name": "x", "type": "number"},
            {"name": "y", "type": "number"}
        ]
    },
    "output": {"type": "number"}
})
def add(x, y):
    return x + y

# From file
@validate("calculator.yaml")
def calculate(operation, a, b):
    # Implementation
    pass
```

## Type System

### Base Types
- `string`, `number`, `integer`, `boolean`, `array`, `object`

### String Formats
- `email`, `uri`, `date`, `time`, `date-time`, `duration`, `timestamp`

### Constraints
- String: `minLength`, `maxLength`, `enum`
- Numeric: `minimum`, `maximum`, `exclusiveMinimum`, `exclusiveMaximum`, `multipleOf`
- Array: `minItems`, `maxItems`, `uniqueItems`, `items`
- Object: `properties`, `required`, `additionalProperties`

### Special Features
- `sensitive`: Mark fields for masking
- `default`: Default values for optional parameters
- `examples`: Example values for documentation

## DataFrame Support

SQL query results returning DataFrames are automatically validated:

```python
validator = TypeValidator.from_dict({
    "output": {
        "type": "array",
        "items": {
            "type": "object",
            "properties": {
                "id": {"type": "integer"},
                "name": {"type": "string"}
            }
        }
    }
})

# DataFrame validates successfully
import pandas as pd
df = pd.DataFrame({"id": [1, 2], "name": ["Alice", "Bob"]})
result = validator.validate_output(df)
# Returns: [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}]
```

## Schema Compatibility

The validator schema is fully aligned with MXCP's `common-types-schema-1.json`:

- **Type Enums**: Exact match (`string`, `number`, `integer`, `boolean`, `array`, `object`)
- **Format Enums**: Exact match (`email`, `uri`, `date`, `time`, `date-time`, `duration`, `timestamp`)
- **Constraints**: All common-types constraints supported
- **Parameter Pattern**: Name validation with `^[a-zA-Z_][a-zA-Z0-9_]*$`

### Intentional Differences
1. **Description Optional**: Parameters don't require descriptions (common-types does)
2. **Output Enums**: Supports enum constraints on outputs (common-types doesn't)
3. **Unified Type System**: Same constraints for inputs and outputs

### Compatibility
- All common-types schemas work with the validator
- Validator schemas with output enums/descriptions won't work with common-types
- See `tests/validator/test_schema_comparison.py` for verification

## Error Handling

```python
from mxcp.validator import ValidationError

try:
    validator.validate_input({"age": -5})
except ValidationError as e:
    print(e.message)  # "Validation failed"
    print(e.details)  # {"age": "-5 is less than minimum value 0"}
```

## Advanced Features

### Strict Mode
```python
validator = TypeValidator.from_dict(schema, strict=True)
# Rejects unknown parameters
```

### Sensitive Data Masking
```python
schema = {
    "output": {
        "type": "object",
        "properties": {
            "password": {"type": "string", "sensitive": True}
        }
    }
}
validator = TypeValidator.from_dict(schema)
result = validator.validate_output({"password": "secret123"}, mask_sensitive=True)
# Returns: {"password": "***REDACTED***"}
```

### No Signature Validation
```python
@validate(schema, validate_signature=False)
def flexible_function(*args, **kwargs):
    # Function can accept any arguments
    pass
```
"""

from .core import TypeValidator, ValidationError
from .decorators import validate
from .loaders import load_schema, load_schema_from_file

__all__ = [
    "TypeValidator",
    "ValidationError", 
    "validate",
    "load_schema",
    "load_schema_from_file",
]

__version__ = "0.1.0" 