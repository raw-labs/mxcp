# MXCP Type System

MXCP's type system provides a robust foundation for defining and validating data structures in your endpoints. It combines the best aspects of JSON Schema, OpenAPI, and AI function calling conventions while maintaining compatibility with SQL/DuckDB types.

## Core Concepts

### Type Definitions

Every parameter and return value in MXCP endpoints is defined using a type definition. These definitions support:

- Base types (string, number, integer, boolean, array, object)
- Format annotations for specialized string types
- Validation constraints (min/max values, lengths, etc.)
- Nested structures (arrays of objects, etc.)

### Type Safety

MXCP enforces strict type checking to ensure:

1. Input validation before execution
2. Output validation after execution
3. Compatibility with DuckDB types
4. Safe serialization/deserialization

## Supported Types

### Base Types

| Type     | Description                       | Example            | DuckDB Type    |
|----------|-----------------------------------|--------------------|----------------|
| string   | Text values                       | `"hello"`          | `VARCHAR`      |
| number   | Floating-point number             | `3.14`             | `DOUBLE`       |
| integer  | Whole number                      | `42`               | `INTEGER`      |
| boolean  | `true` or `false`                 | `true`             | `BOOLEAN`      |
| array    | Ordered list of elements          | `["a", "b", "c"]`  | `ARRAY`        |
| object   | Key-value structure with schema   | `{ "foo": 1 }`     | `STRUCT`       |

### String Format Annotations

MXCP uses format annotations to specialize string types into well-defined subtypes. These formats are **mandatory** in certain contexts and control serialization, validation, and SQL/DuckDB type mapping.

| Format     | Description                          | Example                  | DuckDB Type                |
|------------|--------------------------------------|--------------------------|----------------------------|
| email      | RFC 5322 email address               | `"alice@example.com"`    | `VARCHAR`                  |
| uri        | URI/URL string                       | `"https://raw-labs.com"` | `VARCHAR`                  |
| date       | ISO 8601 date                        | `"2023-01-01"`           | `DATE`                     |
| time       | ISO 8601 time                        | `"14:30:00"`             | `TIME`                     |
| date-time  | ISO 8601 timestamp (Z or offset)     | `"2023-01-01T14:30:00Z"` | `TIMESTAMP WITH TIME ZONE` |
| duration   | ISO 8601 duration                    | `"P1DT2H"`               | `INTERVAL`                 |
| timestamp  | Unix timestamp (seconds since epoch) | `1672531199`             | `TIMESTAMP` (converted)    |

> **Note:** Format annotations are validated and converted automatically when passed to SQL endpoints. For example, `timestamp` values are transformed into proper DuckDB `TIMESTAMP` types during execution.

## Type Annotations

Each type supports standard JSON Schema annotations:

### Common Annotations

- `description`: Human-readable description of the type
- `default`: Default value if none is provided
- `examples`: Example values for documentation
- `enum`: List of allowed values
- `required`: Whether the field is required (for objects)

### String Annotations

- `minLength`: Minimum string length
- `maxLength`: Maximum string length
- `format`: Specialized string format (see above)

### Numeric Annotations

- `minimum`: Minimum value (inclusive)
- `maximum`: Maximum value (inclusive)
- `exclusiveMinimum`: Minimum value (exclusive)
- `exclusiveMaximum`: Maximum value (exclusive)
- `multipleOf`: Value must be a multiple of this number

### Array Annotations

- `minItems`: Minimum number of items
- `maxItems`: Maximum number of items
- `uniqueItems`: Whether items must be unique
- `items`: Schema for array items

### Object Annotations

- `properties`: Schema for object properties
- `required`: List of required properties
- `additionalProperties`: Whether to allow undefined properties

## Type Conversion

MXCP automatically handles type conversion between:

1. JSON/YAML input → Python types
2. Python types → DuckDB types
3. DuckDB results → Python types
4. Python types → JSON/YAML output

### Example Type Definition

```yaml
parameters:
  - name: user_id
    type: string
    format: email
    description: "User's email address"
    examples: ["user@example.com"]
  - name: age
    type: integer
    minimum: 0
    maximum: 120
    description: "User's age in years"
  - name: preferences
    type: object
    properties:
      theme:
        type: string
        enum: ["light", "dark"]
      notifications:
        type: boolean
        default: true
    required: ["theme"]
```

## Limitations

MXCP intentionally restricts schema complexity to promote clarity and compatibility. The following features are **not supported**:

- `$ref` (no schema reuse or references)
- `allOf`, `oneOf`, `anyOf` (no union or intersection types)
- `patternProperties`, `pattern` (no regex-based constraints)
- Conditional schemas (`if` / `then`)
- Complex numeric constraints (`multipleOf`, `exclusiveMinimum`, etc.)

This allows MXCP endpoints to remain:
- Static and serializable
- Directly usable in SQL-based execution
- Compatible with AI tooling
- Easy to validate and test

## Best Practices

1. **Use Format Annotations**
   - Always specify `format` for specialized string types
   - This ensures proper validation and DuckDB type mapping

2. **Provide Examples**
   - Include `examples` for better documentation
   - Helps with testing and validation

3. **Be Explicit**
   - Define all required fields
   - Set `additionalProperties: false` when appropriate
   - Use `enum` for constrained choices

4. **Validate Early**
   - Use `mxcp validate` to check type definitions
   - Test with example values before deployment

## Error Handling

MXCP provides clear error messages for type validation failures:

- Type mismatches
- Format validation errors
- Constraint violations
- Missing required fields

Example error messages:
```
Error: Invalid email format: not-an-email
Error: Value must be >= 0
Error: String must be at least 3 characters long
Error: Missing required properties: name, email
``` 