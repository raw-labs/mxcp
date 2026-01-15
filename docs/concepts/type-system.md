---
title: "Type System"
description: "Complete guide to MXCP's type system for defining and validating data structures. JSON Schema compatible with DuckDB type mapping."
sidebar:
  order: 3
---

> **Related Topics:** [Endpoints](/concepts/endpoints) (use types in definitions) | [Policies](/security/policies) (filter by type) | [YAML Schemas](/schemas/) (complete field reference) | [Testing](/quality/testing) (validate types)

MXCP's type system provides robust data validation for endpoint parameters and return values. It combines JSON Schema compatibility with DuckDB type mapping, ensuring type safety across your entire application.

**Why types matter:**
- **Validation** - Invalid data is rejected before execution
- **Documentation** - LLMs understand what values are expected
- **SQL Safety** - Parameters are properly typed in queries
- **Policy Filtering** - Sensitive fields can be automatically filtered

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
| `duration` | ISO 8601 duration | `"P1DT2H"` | `VARCHAR` |
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

### Required vs Optional Parameters

Parameters are **required by default**. A parameter becomes **optional** when it has a `default` value:

```yaml
parameters:
  # Required - must be provided
  - name: user_id
    type: integer
    description: User ID

  # Optional - uses default if not provided
  - name: limit
    type: integer
    description: Maximum results
    default: 10
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

- name: quantity
  type: integer
  minimum: 1
  multipleOf: 5
  description: Quantity (must be multiple of 5)

- name: price
  type: number
  minimum: 0
  exclusiveMaximum: 1000000
  description: Price in dollars
```

> **Note:** `multipleOf` works reliably with integers. For decimal precision (e.g., currency), use integer cents instead of `multipleOf: 0.01` due to floating-point precision limitations.

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
| `additionalProperties` | Allow (and preserve) undefined properties. Default: `true` (if omitted). Use `false` to reject unknown keys. |

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

Mark fields containing sensitive data with `sensitive: true`. The `sensitive` flag can be applied to **any type** - strings, numbers, integers, booleans, arrays, or objects:

```yaml
return:
  type: object
  properties:
    username:
      type: string
    password:
      type: string
      sensitive: true
    balance:
      type: number
      sensitive: true  # Numbers can also be sensitive
    config:
      type: object
      properties:
        host:
          type: string
        api_key:
          type: string
          sensitive: true  # Nested sensitive field
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

## Using Types in SQL

Parameters defined in your YAML are available in SQL queries using `$parameter_name` syntax:

```yaml
parameters:
  - name: user_id
    type: integer
  - name: status
    type: string
    enum: ["active", "inactive"]
```

```sql
SELECT * FROM users
WHERE id = $user_id
  AND status = $status
```

The type system ensures parameters are properly escaped and typed when passed to DuckDB.

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
- `pattern`, `patternProperties` - No regex-based constraints
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

### Always Add Descriptions
Every parameter and return field should have a description:
```yaml
- name: user_id
  type: integer
  description: Unique identifier for the user
```

### Use Format Annotations
Specify formats for specialized strings:
```yaml
- name: email
  type: string
  format: email  # Validates email format
```

### Set Defaults for Optional Parameters
Make optional parameters explicit:
```yaml
- name: limit
  type: integer
  default: 10  # Optional - uses 10 if not provided
```

### Use Enums for Fixed Values
Constrain to valid options:
```yaml
- name: status
  type: string
  enum: ["active", "inactive", "pending"]
```

### Mark Sensitive Data
Protect sensitive information:
```yaml
- name: api_key
  type: string
  sensitive: true  # Redacted in logs, filterable by policies
```

### Define Complete Return Types
Always specify return schemas with required fields:
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

### Provide Examples
Include examples for documentation and testing:
```yaml
- name: region
  type: string
  examples: ["North", "South", "East", "West"]
```

### Be Explicit with Constraints
Define array and numeric constraints:
```yaml
- name: items
  type: array
  items:
    type: string
  minItems: 1
  maxItems: 100
```

### Validate Early
Use `mxcp validate` to check type definitions before deployment:
```bash
mxcp validate
```

### Group Sensitive Data
Consider putting all sensitive fields in a dedicated object that can be marked sensitive as a whole:
```yaml
return:
  type: object
  properties:
    public:
      type: object
      properties:
        name: { type: string }
    secrets:
      type: object
      sensitive: true
      properties:
        token: { type: string }
        key: { type: string }
```

## Next Steps

- [Endpoints](/concepts/endpoints) - Use types in endpoint definitions
- [Policies](/security/policies) - Filter based on types
- [Testing](/quality/testing) - Test type validation
