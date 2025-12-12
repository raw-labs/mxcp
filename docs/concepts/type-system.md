---
title: "Type System"
description: "Complete guide to MXCP's type system for defining and validating data structures. JSON Schema compatible with DuckDB type mapping."
sidebar:
  order: 3
---

> **Related Topics:** [Endpoints](endpoints) (use types in definitions) | [Policies](/security/policies) (filter by type) | [YAML Schema](/reference/yaml-schema) (complete field reference) | [Testing](/quality/testing) (validate types)

MXCP's type system provides robust data validation for endpoint parameters and return values. It combines JSON Schema compatibility with DuckDB type mapping, ensuring type safety across your entire application.

## Base Types

MXCP supports six base types:

| Type | Description | Example | DuckDB Type |
|------|-------------|---------|-------------|
| `string` | Text values | `"hello"` | `VARCHAR` |
| `number` | Floating-point | `3.14` | `DOUBLE` |
| `integer` | Whole numbers | `42` | `INTEGER` |
| `boolean` | True/false | `true` | `BOOLEAN` |
| `array` | Ordered list | `[1, 2, 3]` | `ARRAY` |
| `object` | Key-value structure | `{"key": "value"}` | `STRUCT` |

## String Format Annotations

String types can have format annotations for specialized handling:

| Format | Description | Example | DuckDB Type |
|--------|-------------|---------|-------------|
| `email` | Email address | `"user@example.com"` | `VARCHAR` |
| `uri` | URL/URI | `"https://example.com"` | `VARCHAR` |
| `date` | ISO 8601 date | `"2024-01-15"` | `DATE` |
| `time` | ISO 8601 time | `"14:30:00"` | `TIME` |
| `date-time` | ISO 8601 timestamp | `"2024-01-15T14:30:00Z"` | `TIMESTAMP WITH TIME ZONE` |
| `duration` | ISO 8601 duration | `"P1DT2H"` | `INTERVAL` |
| `timestamp` | Unix timestamp | `1705329000` | `TIMESTAMP` |

### Using Formats

```yaml
parameters:
  - name: email
    type: string
    format: email
    description: User's email address

  - name: start_date
    type: string
    format: date
    description: Start date (YYYY-MM-DD)

  - name: created_at
    type: string
    format: date-time
    description: Creation timestamp
```

Format annotations are validated automatically when values are passed to endpoints.

## Type Annotations

### Common Annotations

Available for all types:

| Annotation | Description |
|------------|-------------|
| `description` | Human-readable description |
| `default` | Default value if not provided |
| `examples` | Example values for documentation |
| `enum` | List of allowed values |

```yaml
parameters:
  - name: status
    type: string
    description: Order status
    enum: ["pending", "shipped", "delivered"]
    default: "pending"
    examples: ["pending", "shipped"]
```

### String Annotations

| Annotation | Description |
|------------|-------------|
| `minLength` | Minimum string length |
| `maxLength` | Maximum string length |
| `format` | Specialized format |

```yaml
- name: username
  type: string
  minLength: 3
  maxLength: 50
  description: Username (3-50 characters)
```

### Numeric Annotations

| Annotation | Description |
|------------|-------------|
| `minimum` | Minimum value (inclusive) |
| `maximum` | Maximum value (inclusive) |
| `exclusiveMinimum` | Minimum value (exclusive) |
| `exclusiveMaximum` | Maximum value (exclusive) |
| `multipleOf` | Value must be multiple of this |

```yaml
- name: age
  type: integer
  minimum: 0
  maximum: 150
  description: Age in years

- name: price
  type: number
  minimum: 0
  exclusiveMaximum: 1000000
  multipleOf: 0.01
  description: Price in dollars
```

### Array Annotations

| Annotation | Description |
|------------|-------------|
| `items` | Schema for array items |
| `minItems` | Minimum array length |
| `maxItems` | Maximum array length |
| `uniqueItems` | Items must be unique |

```yaml
- name: tags
  type: array
  items:
    type: string
  minItems: 1
  maxItems: 10
  uniqueItems: true
  description: List of tags (1-10 unique strings)
```

### Object Annotations

| Annotation | Description |
|------------|-------------|
| `properties` | Schema for object properties |
| `required` | List of required properties |
| `additionalProperties` | Allow undefined properties |

```yaml
- name: address
  type: object
  properties:
    street:
      type: string
    city:
      type: string
    zip:
      type: string
  required: ["street", "city"]
```

## Nested Types

Types can be nested to any depth:

### Array of Objects

```yaml
return:
  type: array
  description: List of users
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
```

### Object with Nested Objects

```yaml
return:
  type: object
  properties:
    user:
      type: object
      properties:
        id:
          type: integer
        name:
          type: string
    orders:
      type: array
      items:
        type: object
        properties:
          order_id:
            type: string
          amount:
            type: number
```

## Sensitive Data

Mark fields containing sensitive data with `sensitive: true`:

```yaml
return:
  type: object
  properties:
    username:
      type: string
    password:
      type: string
      sensitive: true
    api_key:
      type: string
      sensitive: true
```

Sensitive fields are:
- **Redacted in audit logs** - Replaced with `[REDACTED]`
- **Filterable by policies** - Can be removed with `filter_sensitive_fields` action
- **Documented as sensitive** - Clear indication in schemas

### Marking Entire Objects

You can mark entire objects as sensitive:

```yaml
return:
  type: object
  properties:
    public_data:
      type: object
      properties:
        name:
          type: string
    credentials:
      type: object
      sensitive: true
      properties:
        access_token:
          type: string
        refresh_token:
          type: string
```

## Type Conversion

MXCP automatically handles type conversion between:

1. **JSON/YAML input** → Python types
2. **Python types** → DuckDB types
3. **DuckDB results** → Python types
4. **Python types** → JSON/YAML output

### Python to DuckDB Mapping

| Python Type | DuckDB Type |
|-------------|-------------|
| `str` | `VARCHAR` |
| `int` | `INTEGER` |
| `float` | `DOUBLE` |
| `bool` | `BOOLEAN` |
| `list` | `ARRAY` |
| `dict` | `STRUCT` |
| `datetime` | `TIMESTAMP` |
| `date` | `DATE` |
| `time` | `TIME` |

## Complete Example

Here's a complete parameter definition showcasing various type features:

```yaml
parameters:
  - name: user_id
    type: integer
    description: Unique user identifier
    minimum: 1
    examples: [1, 42, 100]

  - name: email
    type: string
    format: email
    description: User's email address
    examples: ["user@example.com"]

  - name: role
    type: string
    description: User role
    enum: ["admin", "user", "guest"]
    default: "user"

  - name: tags
    type: array
    items:
      type: string
    minItems: 0
    maxItems: 5
    description: User tags

  - name: preferences
    type: object
    description: User preferences
    properties:
      theme:
        type: string
        enum: ["light", "dark", "auto"]
        default: "auto"
      notifications:
        type: boolean
        default: true
      language:
        type: string
        default: "en"
    required: ["theme"]

  - name: created_after
    type: string
    format: date-time
    description: Filter users created after this time
```

## Limitations

MXCP intentionally restricts schema complexity:

**Not supported:**
- `$ref` - No schema references
- `allOf`, `oneOf`, `anyOf` - No union types
- `patternProperties` - No regex property matching
- Conditional schemas (`if`/`then`)

These restrictions ensure:
- Static, serializable schemas
- SQL-compatible types
- AI tooling compatibility
- Simpler validation and testing

## Validation Errors

MXCP provides clear error messages:

```
Error: Invalid email format: not-an-email
Error: Value must be >= 0
Error: String must be at least 3 characters long
Error: Missing required properties: name, email
Error: Value 'invalid' not in enum: ['admin', 'user', 'guest']
```

## Best Practices

### 1. Use Format Annotations
Always specify formats for specialized strings:
```yaml
# Good
type: string
format: email

# Avoid
type: string  # No format for email
```

### 2. Provide Examples
Include examples for better documentation:
```yaml
- name: region
  type: string
  examples: ["North", "South", "East", "West"]
```

### 3. Be Explicit
Define all constraints:
```yaml
# Good
- name: items
  type: array
  items:
    type: string
  minItems: 1
  maxItems: 100

# Avoid
- name: items
  type: array  # No item schema or constraints
```

### 4. Mark Sensitive Data
Protect sensitive information:
```yaml
- name: api_key
  type: string
  sensitive: true
```

### 5. Use Enums for Fixed Values
Constrain to valid options:
```yaml
- name: status
  type: string
  enum: ["active", "inactive", "pending"]
```

### 6. Define Return Types
Always define complete return schemas:
```yaml
return:
  type: object
  properties:
    id:
      type: integer
    name:
      type: string
  required: ["id", "name"]
```

## Next Steps

- [Endpoints](endpoints) - Use types in endpoint definitions
- [Policies](/security/policies) - Filter based on types
- [Testing](/quality/testing) - Test type validation
