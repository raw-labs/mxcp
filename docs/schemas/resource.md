---
title: "Resource Schema"
description: "Complete YAML schema reference for MXCP resource definitions. URI patterns, parameters, return types, source, tests, and policies."
sidebar:
  order: 3
---

> **Related Topics:** [Endpoints](/concepts/endpoints) (resource concepts) | [SQL Endpoints](/tutorials/sql-endpoints) (tutorial) | [Python Endpoints](/tutorials/python-endpoints) (tutorial) | [Type System](/concepts/type-system) (parameter types)

This reference documents the complete YAML schema for resource definitions in MXCP.

## Complete Example

```yaml
mxcp: 1
resource:
  uri: "employee://{employee_id}/profile"
  name: Employee Profile
  description: Retrieve employee profile information by ID
  language: sql
  mime_type: application/json
  tags:
    - hr
    - employee

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
      hire_date:
        type: string
        format: date

  source:
    file: ../sql/get_employee_profile.sql

  policies:
    input:
      - condition: "user.role == 'guest'"
        action: deny
        reason: "Guests cannot access employee profiles"
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
| `resource` | object | Yes | - | Resource definition object. |
| `metadata` | object | No | - | Custom metadata (not processed by MXCP). |

> **Note:** The `mxcp` field accepts both integer (`1`) and string (`"1"`) values - strings are automatically coerced to integers.

## Resource Object

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `uri` | string | Yes | - | URI pattern with `{param}` placeholders. |
| `name` | string | No | - | Human-readable display name. |
| `description` | string | No | - | Human-readable description for AI clients. |
| `language` | string | No | `"sql"` | Implementation language: `sql` or `python`. |
| `mime_type` | string | No | - | Content type of the resource. |
| `tags` | array | No | - | List of tags for categorization. |
| `parameters` | array | No | - | URI parameter definitions. |
| `return` | object | No | - | Return type definition. |
| `source` | object | Yes | - | Implementation source (code or file). |
| `policies` | object | No | - | Input and output policy rules. |
| `tests` | array | No | - | Test case definitions. |
| `enabled` | boolean | No | `true` | Whether the resource is enabled. |

## URI Patterns

Resources are accessed via URI patterns with parameter placeholders.

### Basic Pattern

```yaml
uri: "user://{user_id}"
```

### Nested Pattern

```yaml
uri: "org://{org_id}/team/{team_id}/member/{member_id}"
```

### Pattern Rules

- Use `{param_name}` for parameter placeholders
- Parameter names must match entries in the `parameters` array
- **All parameters must be used in the URI** - parameters not in the URI will cause validation errors (use a tool instead if you need extra parameters)
- Use hierarchical paths for nested resources
- Avoid query strings (use parameters instead)

### Pattern Examples

```yaml
# Simple resource
uri: "config://settings"

# Single parameter
uri: "user://{user_id}"

# Multiple parameters
uri: "order://{order_id}/item/{item_id}"

# Hierarchical resource
uri: "project://{project_id}/environment/{env_name}/config"
```

## MIME Types

Common MIME types for resources:

| MIME Type | Use Case |
|-----------|----------|
| `application/json` | Structured data (default) |
| `text/plain` | Plain text content |
| `text/markdown` | Markdown documents |
| `text/html` | HTML content |
| `application/xml` | XML data |
| `text/csv` | CSV data |

```yaml
resource:
  uri: "report://{report_id}"
  mime_type: text/markdown
  # ...
```

## Parameters Array

Each parameter defines a URI placeholder.

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `name` | string | Yes | - | Parameter identifier (must match URI placeholder). |
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
| `additionalProperties` | boolean | Whether extra (unspecified) object properties are accepted and preserved. Default: `true` (if omitted). Use `false` to reject unknown keys. |

**Note:** If `additionalProperties` is omitted, MXCP treats it as `true` (extra keys are allowed and preserved). Set `additionalProperties: false` to forbid unknown keys.

```yaml
# Allow unknown keys (default behavior)
type: object
properties:
  objid:
    type: integer
required: ["objid"]

# Forbid unknown keys
type: object
properties:
  objid:
    type: integer
required: ["objid"]
additionalProperties: false
```

### Parameter Examples

```yaml
parameters:
  # Required integer parameter
  - name: user_id
    type: integer
    description: User's unique identifier
    minimum: 1

  # String with pattern
  - name: slug
    type: string
    description: URL-friendly identifier
    pattern: "^[a-z0-9-]+$"
    minLength: 1
    maxLength: 100

  # Enum parameter
  - name: format
    type: string
    description: Output format
    enum: ["json", "xml", "csv"]
    default: "json"
```

## Return Object

The return type defines the structure of the resource's content.

```yaml
return:
  type: object
  properties:
    id:
      type: integer
    title:
      type: string
    content:
      type: string
    metadata:
      type: object
      properties:
        created_at:
          type: string
          format: date-time
        author:
          type: string
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
    SELECT id, title, content, created_at
    FROM documents
    WHERE id = $document_id
```

### File Source

```yaml
source:
  file: ../sql/get_document.sql
```

### Python Source

For Python resources, the function name in the Python file must match the resource name (derived from the URI pattern):

```yaml title="resources/user_profile.yml"
resource:
  uri: "user://{user_id}/profile"
  name: user_profile          # Function name must match
  language: python
  source:
    file: ../python/profiles.py
```

```python title="python/profiles.py"
def user_profile(user_id: int) -> dict:
    """Function name must match resource name."""
    return {"id": user_id, "name": "Alice"}
```

## Policies Object

Policies control access and data filtering.

```yaml
policies:
  input:
    - condition: "user.role == 'guest'"
      action: deny
      reason: "Guests cannot access this resource"

  output:
    - condition: "user.role != 'admin'"
      action: filter_fields
      fields: ["internal_notes", "audit_log"]
      reason: "Internal fields restricted"
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

Tests verify resource behavior.

```yaml
tests:
  - name: get_document_success
    description: Successfully retrieves a document
    arguments:
      - key: document_id
        value: 1
    result_contains:
      id: 1
      title: "Welcome"

  - name: get_document_not_found
    description: Returns null for non-existent document
    arguments:
      - key: document_id
        value: 99999
    result: null

  - name: admin_sees_internal_fields
    description: Admin can see internal fields
    arguments:
      - key: document_id
        value: 1
    user_context:
      role: admin
    result_contains:
      internal_notes: "Review scheduled"
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

## Resource vs Tool

| Aspect | Resource | Tool |
|--------|----------|------|
| Purpose | Retrieve data/content | Perform actions |
| Access | Via URI pattern | Via name |
| Semantics | Read-only by convention | Any operation |
| Use case | Documents, configs, profiles | CRUD, calculations, API calls |

### When to Use Resources

- Static or semi-static content
- Document retrieval
- Configuration access
- User profiles
- File content

### When to Use Tools

- Data modifications
- Complex calculations
- External API calls
- Multi-step operations

## Naming Conventions

- **URI patterns**: Use hierarchical paths (e.g., `user://{id}/settings`)
- **Parameter names**: Use `snake_case` (e.g., `user_id`, `document_slug`)
- **File paths**: Relative to the YAML file location

## Validation

Validate your resource definitions:

```bash
mxcp validate
mxcp validate resources/my-resource.yml
```

## Next Steps

- [Endpoints](/concepts/endpoints) - Understand resource concepts
- [SQL Endpoints Tutorial](/tutorials/sql-endpoints) - Build SQL resources
- [Python Endpoints Tutorial](/tutorials/python-endpoints) - Build Python resources
- [Testing](/quality/testing) - Write comprehensive tests
