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

## Sensitive Data Marking

Fields containing sensitive data can be marked with the `sensitive` flag. This provides:

1. **Automatic redaction** in audit logs
2. **Policy-based filtering** for access control
3. **Clear documentation** of sensitive data

The `sensitive` flag can be applied to **any type** - strings, numbers, integers, booleans, arrays, or objects. When a type is marked as sensitive, it will be completely redacted in logs and can be filtered out by policies.

### Example: Marking Sensitive Fields

```yaml
parameters:
  - name: username
    type: string
    description: User's username
  - name: password
    type: string
    sensitive: true  # This field will be redacted in logs
    description: User's password
  - name: balance
    type: number
    sensitive: true  # Numbers can also be sensitive
    description: Account balance
  - name: config
    type: object
    properties:
      host:
        type: string
      api_key:
        type: string
        sensitive: true  # Nested sensitive field
```

### Marking Entire Objects as Sensitive

You can mark an entire object or array as sensitive:

```yaml
return:
  type: object
  properties:
    user_info:
      type: object
      properties:
        name:
          type: string
        email:
          type: string
    credentials:
      type: object
      sensitive: true  # Entire object is sensitive
      properties:
        token:
          type: string
        refresh_token:
          type: string
```

### Using with Policies

The `filter_sensitive_fields` policy action automatically removes all fields marked as sensitive:

```yaml
policies:
  output:
    - condition: "user.role != 'admin'"
      action: filter_sensitive_fields
      reason: "Non-admin users cannot see sensitive data"
```

This is more maintainable than `filter_fields` as sensitive fields are defined once in the schema rather than repeated in policies.

## Examples

### Simple Parameter Types

```yaml
parameters:
  - name: user_id
    type: integer
    description: Unique user identifier
    minimum: 1
  
  - name: email
    type: string
    format: email
    description: User's email address
  
  - name: is_active
    type: boolean
    description: Whether the user is active
    default: true
```

### Complex Object Types

```yaml
parameters:
  - name: filter
    type: object
    description: Filter criteria
    properties:
      status:
        type: string
        enum: ["active", "inactive", "pending"]
      created_after:
        type: string
        format: date-time
      tags:
        type: array
        items:
          type: string
        minItems: 1
    required: ["status"]
```

### Return Type Definition

```yaml
return:
  type: array
  description: List of matching users
  items:
    type: object
    properties:
      id:
        type: integer
      name:
        type: string
      email:
        type: string
        format: email
      api_token:
        type: string
        sensitive: true  # Automatically filtered for non-admin users
      created_at:
        type: string
        format: date-time
    required: ["id", "name", "email"]
```

## Best Practices

1. **Always define types** - Even for simple parameters
2. **Use constraints** - They provide validation and documentation
3. **Mark sensitive fields** - Use the `sensitive` flag for any data that should be protected
4. **Provide descriptions** - Help users understand what each field is for
5. **Use enums** - When there's a fixed set of valid values
6. **Define return types** - Helps with validation and client code generation
7. **Group sensitive data** - Consider putting all sensitive fields in a dedicated object that can be marked sensitive as a whole 