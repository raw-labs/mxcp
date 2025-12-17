---
title: "Tool Schema"
description: "Complete YAML schema reference for MXCP tool definitions. Parameters, return types, source, tests, and policies."
sidebar:
  order: 2
---

> **Related Topics:** [Endpoints](/concepts/endpoints) (tool concepts) | [SQL Endpoints](/tutorials/sql-endpoints) (tutorial) | [Python Endpoints](/tutorials/python-endpoints) (tutorial) | [Type System](/concepts/type-system) (parameter types)

This reference documents the complete YAML schema for tool definitions in MXCP.

## Complete Example

```yaml
mxcp: 1
tool:
  name: get_employee
  description: Retrieve employee information by ID
  language: sql
  tags:
    - hr
    - employee

  annotations:
    title: "Get Employee"
    readOnlyHint: true
    destructiveHint: false
    idempotentHint: true
    openWorldHint: false

  parameters:
    - name: employee_id
      type: integer
      description: The employee's unique identifier
      minimum: 1
      examples: [1, 42, 100]

  return:
    type: object
    properties:
      id:
        type: integer
      name:
        type: string
      email:
        type: string
        sensitive: true
      department:
        type: string
      salary:
        type: number
        sensitive: true

  source:
    file: ../sql/get_employee.sql

  policies:
    input:
      - condition: "user.role == 'guest'"
        action: deny
        reason: "Guests cannot access employee data"
    output:
      - condition: "user.role != 'hr'"
        action: filter_sensitive_fields
        reason: "Sensitive data restricted to HR"

  tests:
    - name: get_existing_employee
      arguments:
        - key: employee_id
          value: 1
      result_contains:
        id: 1
        name: "Alice"

  enabled: true
```

## Root Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `mxcp` | integer | Yes | - | Schema version. Must be `1`. |
| `tool` | object | Yes | - | Tool definition object. |
| `metadata` | object | No | - | Custom metadata (not processed by MXCP). |

> **Note:** The `mxcp` field accepts both integer (`1`) and string (`"1"`) values - strings are automatically coerced to integers.

## Tool Object

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `name` | string | Yes | - | Unique identifier. Must start with letter/underscore, alphanumeric only. |
| `description` | string | No | - | Human-readable description for AI clients. |
| `language` | string | No | `"sql"` | Implementation language: `sql` or `python`. |
| `tags` | array | No | - | List of tags for categorization. |
| `annotations` | object | No | - | MCP tool annotations (hints for AI). |
| `parameters` | array | No | - | Input parameter definitions. |
| `return` | object | No | - | Return type definition. |
| `source` | object | Yes | - | Implementation source (code or file). |
| `policies` | object | No | - | Input and output policy rules. |
| `tests` | array | No | - | Test case definitions. |
| `enabled` | boolean | No | `true` | Whether the tool is enabled. |

## Annotations Object

Tool annotations provide hints to AI clients about the tool's behavior.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `title` | string | - | Display title for the tool. |
| `readOnlyHint` | boolean | - | Hint that the tool only reads data. |
| `destructiveHint` | boolean | - | Hint that the tool may delete or modify data. |
| `idempotentHint` | boolean | - | Hint that repeated calls produce the same result. |
| `openWorldHint` | boolean | - | Hint that the tool interacts with external systems. |

```yaml
annotations:
  title: "Delete User"
  readOnlyHint: false
  destructiveHint: true
  idempotentHint: false
```

## Parameters Array

Each parameter defines an input to the tool.

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `name` | string | Yes | - | Parameter identifier (snake_case). |
| `type` | string | Yes | - | Data type: `string`, `integer`, `number`, `boolean`, `array`, `object`. |
| `description` | string | No | - | Human-readable description. |
| `default` | any | No | - | Default value (makes parameter optional). |
| `examples` | array | No | - | Example values for documentation. |
| `enum` | array | No | - | Allowed values. |
| `sensitive` | boolean | No | `false` | Mark as sensitive (for filtering). |

### Type-Specific Constraints

**String constraints:**

| Field | Type | Description |
|-------|------|-------------|
| `minLength` | integer | Minimum string length. |
| `maxLength` | integer | Maximum string length. |
| `pattern` | string | Regex pattern to match. |
| `format` | string | Format hint: `email`, `uri`, `date`, `time`, `date-time`, `duration`, `timestamp`. |

**Number/Integer constraints:**

| Field | Type | Description |
|-------|------|-------------|
| `minimum` | number | Minimum value (inclusive). |
| `maximum` | number | Maximum value (inclusive). |
| `exclusiveMinimum` | number | Minimum value (exclusive). |
| `exclusiveMaximum` | number | Maximum value (exclusive). |
| `multipleOf` | number | Value must be multiple of this. |

**Array constraints:**

| Field | Type | Description |
|-------|------|-------------|
| `items` | object | Type definition for array items. |
| `minItems` | integer | Minimum array length. |
| `maxItems` | integer | Maximum array length. |
| `uniqueItems` | boolean | Whether items must be unique. |

**Object constraints:**

| Field | Type | Description |
|-------|------|-------------|
| `properties` | object | Map of property names to type definitions. |
| `required` | array | List of required property names. |
| `additionalProperties` | boolean | Whether extra properties are allowed. |

### Parameter Examples

```yaml
parameters:
  # Required string with validation
  - name: email
    type: string
    description: User email address
    format: email
    maxLength: 255

  # Optional integer with range
  - name: limit
    type: integer
    description: Maximum results
    default: 10
    minimum: 1
    maximum: 100

  # Enum parameter
  - name: status
    type: string
    description: Order status
    enum: ["pending", "shipped", "delivered"]

  # Array parameter
  - name: ids
    type: array
    description: List of IDs to fetch
    items:
      type: integer
    minItems: 1
    maxItems: 100

  # Object parameter
  - name: filters
    type: object
    description: Search filters
    properties:
      department:
        type: string
      min_salary:
        type: number
    required:
      - department
```

## Return Object

The return type defines the structure of the tool's output.

```yaml
return:
  type: object
  properties:
    id:
      type: integer
    name:
      type: string
    email:
      type: string
      sensitive: true
    created_at:
      type: string
      format: date-time
```

Same fields as parameters, minus `name` and `default`.

## Source Object

The source defines where the implementation lives.

| Field | Type | Description |
|-------|------|-------------|
| `code` | string | Inline SQL or Python code. |
| `file` | string | Path to external file (relative to YAML file). |
| `language` | string | Override language detection: `sql` or `python`. |

**Note:** Exactly one of `code` or `file` must be specified.

### Inline Source

```yaml
source:
  code: |
    SELECT id, name, email
    FROM users
    WHERE id = $user_id
```

### File Source

```yaml
source:
  file: ../sql/get_user.sql
```

### Python Source

For Python tools, the function name in the Python file must match the tool name:

```yaml title="tools/calculate_tax.yml"
tool:
  name: calculate_tax      # Function name must match
  language: python
  source:
    file: ../python/tax.py
```

```python title="python/tax.py"
def calculate_tax(amount: float, rate: float) -> float:
    """Function name must match tool name."""
    return amount * rate
```

## Policies Object

Policies control access and data filtering.

```yaml
policies:
  input:
    - condition: "user.role == 'guest'"
      action: deny
      reason: "Guests cannot access this tool"

  output:
    - condition: "user.role != 'admin'"
      action: filter_fields
      fields: ["salary", "ssn"]
      reason: "Sensitive fields restricted"
```

### Policy Rule Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `condition` | string | Yes | CEL expression to evaluate. |
| `action` | string | Yes | Action to take: `deny`, `filter_fields`, `mask_fields`, `filter_sensitive_fields`. |
| `reason` | string | No | Human-readable reason. |
| `fields` | array | No | Fields to filter/mask (for `filter_fields`, `mask_fields`). |

### Policy Actions

| Action | Type | Description |
|--------|------|-------------|
| `deny` | input | Block the request entirely. |
| `filter_fields` | output | Remove specified fields from response. |
| `mask_fields` | output | Replace field values with masks. |
| `filter_sensitive_fields` | output | Remove fields marked `sensitive: true`. |

See [Policies](/security/policies) for complete documentation.

## Tests Array

Tests verify tool behavior.

```yaml
tests:
  - name: get_user_success
    description: Successfully retrieves a user
    arguments:
      - key: user_id
        value: 1
    result_contains:
      id: 1
      name: "Alice"

  - name: get_user_not_found
    description: Returns null for non-existent user
    arguments:
      - key: user_id
        value: 99999
    result: null

  - name: admin_sees_all_fields
    description: Admin can see sensitive fields
    arguments:
      - key: user_id
        value: 1
    user_context:
      role: admin
    result_contains:
      salary: 75000
```

### Test Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | Yes | Unique test identifier. |
| `description` | string | No | Human-readable description. |
| `arguments` | array | Yes | Input arguments as key-value pairs. |
| `user_context` | object | No | Simulated user context for policy testing. |

### Test Assertions

| Field | Type | Description |
|-------|------|-------------|
| `result` | any | Expected exact result. |
| `result_contains` | any | Partial match - fields must exist with values. |
| `result_not_contains` | array | Field names that must NOT exist. |
| `result_contains_item` | object | For arrays - at least one item must match. |
| `result_contains_all` | array | For arrays - all items must be present. |
| `result_length` | integer | For arrays - exact length required. |
| `result_contains_text` | string | For strings - must contain substring. |

See [Testing](/quality/testing) for complete documentation.

## Naming Conventions

- **Tool names**: Use `snake_case` (e.g., `get_user`, `search_orders`)
- **Parameter names**: Use `snake_case` (e.g., `user_id`, `max_results`)
- **File paths**: Relative to the YAML file location

## Validation

Validate your tool definitions:

```bash
mxcp validate
mxcp validate tools/my-tool.yml
```

## Next Steps

- [Endpoints](/concepts/endpoints) - Understand tool concepts
- [SQL Endpoints Tutorial](/tutorials/sql-endpoints) - Build SQL tools
- [Python Endpoints Tutorial](/tutorials/python-endpoints) - Build Python tools
- [Testing](/quality/testing) - Write comprehensive tests
