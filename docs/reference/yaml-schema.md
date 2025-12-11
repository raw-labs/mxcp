---
title: "YAML Schema Reference"
description: "Complete reference for all MXCP YAML configuration files. Field definitions, types, and valid values for endpoint definitions and project configuration."
sidebar:
  order: 5
---

This reference documents all YAML configuration files in MXCP, their fields, types, and valid values.

## File Types Overview

| File | Purpose | Location |
|------|---------|----------|
| `mxcp-site.yml` | Project configuration | Project root |
| `*.yml` in `tools/` | Tool definitions | `tools/` directory |
| `*.yml` in `resources/` | Resource definitions | `resources/` directory |
| `*.yml` in `prompts/` | Prompt definitions | `prompts/` directory |
| `~/.mxcp/config.yml` | User configuration | Home directory |

## Endpoint Definition Files

All endpoint files (tools, resources, prompts) share a common structure.

### Common Header

```yaml
mxcp: 1                    # Required. Schema version (always 1)
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `mxcp` | integer | Yes | Schema version. Currently only `1` is valid. |

### Tool Definition

```yaml
mxcp: 1
tool:
  name: my_tool              # Required. Unique identifier
  description: Does X        # Required. What the tool does
  language: sql              # Required. sql or python

  parameters:                # Optional. Input parameters
    - name: user_id
      type: integer
      description: User ID

  return:                    # Optional. Return type definition
    type: array
    items:
      type: object

  source:                    # Required. Implementation
    inline: SELECT * FROM users
    # OR
    file: ../sql/query.sql

  tests:                     # Optional. Test cases
    - name: basic_test
      arguments:
        - key: user_id
          value: 1
```

#### Tool Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | Yes | Unique identifier. Use snake_case. |
| `description` | string | Yes | Human-readable description for AI clients. |
| `language` | string | Yes | `sql` or `python` |
| `parameters` | array | No | Input parameter definitions. |
| `return` | object | No | Return type schema. |
| `source` | object | Yes | Implementation source. |
| `tests` | array | No | Test case definitions. |

### Resource Definition

```yaml
mxcp: 1
resource:
  uri_template: "user://{user_id}"  # Required. URI pattern
  name: User Profile                 # Required. Display name
  description: User information      # Required. Description
  mime_type: application/json        # Optional. Content type
  language: sql                      # Required. sql or python

  parameters:                        # Optional. URI parameters
    - name: user_id
      type: integer

  source:
    inline: SELECT * FROM users WHERE id = $user_id
```

#### Resource Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `uri_template` | string | Yes | URI pattern with `{param}` placeholders. |
| `name` | string | Yes | Human-readable name. |
| `description` | string | Yes | What the resource provides. |
| `mime_type` | string | No | Content type. Default: `application/json` |
| `language` | string | Yes | `sql` or `python` |
| `parameters` | array | No | URI parameter definitions. |
| `source` | object | Yes | Implementation source. |

### Prompt Definition

```yaml
mxcp: 1
prompt:
  name: analyze_data           # Required. Unique identifier
  description: Analysis prompt # Required. Description

  parameters:                  # Optional. Template parameters
    - name: topic
      type: string
      description: Topic to analyze

  messages:                    # Required. Prompt messages
    - role: system
      type: text
      prompt: "You are an expert analyst."
    - role: user
      type: text
      prompt: "Analyze the following: {{ topic }}"
```

#### Prompt Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | Yes | Unique identifier. |
| `description` | string | Yes | What the prompt does. |
| `parameters` | array | No | Template parameter definitions. |
| `messages` | array | Yes | Message sequence with Jinja2 templates. |

## Parameter Definition

Parameters are used in tools and resources.

```yaml
parameters:
  # Required parameter (no default)
  - name: user_id              # Required. Parameter name
    type: integer              # Required. Data type
    description: The user ID   # Required. Description
    examples: [1, 2, 3]        # Optional. Example values

  # Optional parameter (has default)
  - name: limit
    type: integer
    description: Maximum results
    default: 10                # Optional. Makes parameter optional

    # Validation constraints
    minimum: 1                 # For numbers
    maximum: 1000              # For numbers
    minLength: 1               # For strings
    maxLength: 100             # For strings
    enum: [a, b, c]            # Allowed values
    minItems: 1                # For arrays
    maxItems: 50               # For arrays
```

### Parameter Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | Yes | Parameter identifier. Use snake_case. |
| `type` | string | Yes | Data type (see Type System below). |
| `description` | string | Yes | Human-readable description. |
| `default` | any | No | Default value. Without it, parameter is required. |
| `examples` | array | No | Example values for documentation. |
| `format` | string | No | Format hint (e.g., `email`, `date-time`). |

### Validation Constraints

| Constraint | Applies To | Description |
|------------|------------|-------------|
| `minimum` | integer, number | Minimum value (inclusive) |
| `maximum` | integer, number | Maximum value (inclusive) |
| `exclusiveMinimum` | integer, number | Minimum value (exclusive) |
| `exclusiveMaximum` | integer, number | Maximum value (exclusive) |
| `minLength` | string | Minimum string length |
| `maxLength` | string | Maximum string length |
| `pattern` | string | Regex pattern to match |
| `enum` | any | List of allowed values |
| `minItems` | array | Minimum array length |
| `maxItems` | array | Maximum array length |

## Type System

### Primitive Types

| Type | Description | Example |
|------|-------------|---------|
| `string` | Text value | `"hello"` |
| `integer` | Whole number | `42` |
| `number` | Decimal number | `3.14` |
| `boolean` | True/false | `true` |
| `null` | Null value | `null` |

### Complex Types

#### Array Type

```yaml
type: array
items:
  type: string        # Type of array elements
minItems: 1           # Optional minimum length
maxItems: 100         # Optional maximum length
```

#### Object Type

```yaml
type: object
properties:
  name:
    type: string
  age:
    type: integer
required:             # Optional list of required properties
  - name
additionalProperties: false  # Optional. Disallow extra properties
```

### Format Hints

| Format | Type | Description |
|--------|------|-------------|
| `date` | string | ISO 8601 date (YYYY-MM-DD) |
| `date-time` | string | ISO 8601 datetime |
| `time` | string | ISO 8601 time |
| `email` | string | Email address |
| `uri` | string | URI/URL |
| `uuid` | string | UUID |
| `hostname` | string | Hostname |
| `ipv4` | string | IPv4 address |
| `ipv6` | string | IPv6 address |

## Source Definition

The `source` field defines where the implementation code lives.

### Inline Source

```yaml
source:
  code: |
    SELECT * FROM users
    WHERE id = $user_id
```

### File Source

```yaml
source:
  file: ../sql/get_user.sql    # Relative path from YAML file
```

| Field | Type | Description |
|-------|------|-------------|
| `code` | string | Code written directly in YAML |
| `file` | string | Path to external file |

Only one of `code` or `file` should be specified.

## Test Definition

Tests validate endpoint behavior.

```yaml
tests:
  - name: test_basic           # Required. Test identifier
    description: Basic test    # Optional. Test description

    arguments:                 # Required. Input arguments
      - key: user_id
        value: 1

    # Assertions
    result:                    # Expected exact result
      id: 1
      name: "Alice"
    result_contains:           # Partial match (fields must exist)
      name: "Alice"
    result_contains_text: "Alice"  # For string results
    result_length: 5           # For array results

  - name: test_with_user_context
    description: Test policy filtering
    arguments:
      - key: user_id
        value: 1
    user_context:              # User context for policy testing
      role: admin
      permissions: ["data.read"]
    result_not_contains:       # Fields that should NOT exist
      - ssn
      - salary
```

### Test Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | Yes | Unique test identifier |
| `description` | string | No | Human-readable description |
| `arguments` | array | Yes | Input arguments as key-value pairs |
| `user_context` | object | No | User context for policy testing |

### Test Assertions

| Assertion | Type | Description |
|-----------|------|-------------|
| `result` | any | Expected exact result |
| `result_contains` | object | Partial match - fields must exist |
| `result_contains_text` | string | For string results - must contain substring |
| `result_not_contains` | array | List of field names that should NOT exist |
| `result_contains_item` | object | For arrays - at least one item must match |
| `result_contains_all` | array | For arrays - all items must be present |
| `result_length` | integer | For arrays - exact length required |

## Project Configuration (mxcp-site.yml)

The project configuration file in the project root.

```yaml
mxcp: 1
project:
  name: my-project             # Required. Project identifier
  description: My MCP server   # Optional. Project description

profiles:
  default:                     # Profile name
    duckdb:
      path: ./data/app.duckdb  # Database path
      readonly: false          # Read-only mode

    extensions:                # DuckDB extensions to load
      - httpfs
      - parquet

    secrets:                   # Secret definitions
      - name: api_key
        type: env
        key: API_KEY

    audit:                     # Audit logging
      enabled: true
      path: ./audit/logs.jsonl

    dbt:                       # dbt integration
      enabled: true
      project_dir: ./dbt

    sql_tools:                 # Built-in SQL tools
      enabled: false

  production:                  # Additional profile
    duckdb:
      path: /data/prod.duckdb
      readonly: true
```

### Project Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | Yes | Project identifier |
| `description` | string | No | Project description |

### Profile Fields

| Field | Type | Description |
|-------|------|-------------|
| `duckdb` | object | Database configuration |
| `extensions` | array | DuckDB extensions to load |
| `secrets` | array | Secret definitions |
| `audit` | object | Audit logging configuration |
| `dbt` | object | dbt integration settings |
| `sql_tools` | object | Built-in SQL tools settings |

### DuckDB Configuration

```yaml
duckdb:
  path: ./data/app.duckdb      # Database file path
  readonly: false              # Read-only mode
  memory_limit: 4GB            # Memory limit
  threads: 4                   # Number of threads
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `path` | string | `:memory:` | Database file path |
| `readonly` | boolean | `false` | Read-only mode |
| `memory_limit` | string | - | Memory limit (e.g., "4GB") |
| `threads` | integer | - | Number of worker threads |

### Secret Types

```yaml
secrets:
  # Environment variable
  - name: api_key
    type: env
    key: API_KEY

  # File contents
  - name: cert
    type: file
    path: /etc/ssl/cert.pem

  # HashiCorp Vault
  - name: db_password
    type: vault
    path: secret/data/db
    key: password

  # Custom key-value
  - name: custom
    type: custom
    parameters:
      key1: value1
      key2: value2
```

| Type | Fields | Description |
|------|--------|-------------|
| `env` | `key` | Environment variable name |
| `file` | `path` | File path to read |
| `vault` | `path`, `key` | Vault secret path and key |
| `custom` | `parameters` | Custom key-value pairs |

### Audit Configuration

```yaml
audit:
  enabled: true
  path: ./audit/logs.jsonl
  retention:
    days: 90
    max_size: 1GB
    max_files: 10
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `enabled` | boolean | `false` | Enable audit logging |
| `path` | string | `./audit/logs.jsonl` | Log file path |
| `retention.days` | integer | `30` | Days to retain logs |
| `retention.max_size` | string | `500MB` | Maximum file size |
| `retention.max_files` | integer | `10` | Maximum rotated files |

### dbt Configuration

```yaml
dbt:
  enabled: true
  project_dir: ./dbt
  profiles_dir: ~/.dbt
  target: dev
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `enabled` | boolean | `false` | Enable dbt integration |
| `project_dir` | string | `./dbt` | dbt project directory |
| `profiles_dir` | string | `~/.dbt` | dbt profiles directory |
| `target` | string | `dev` | dbt target to use |

### SQL Tools Configuration

```yaml
sql_tools:
  enabled: true
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `enabled` | boolean | `false` | Enable built-in SQL tools |

When enabled, provides: `execute_sql_query`, `list_tables`, `get_table_schema`

## User Configuration (~/.mxcp/config.yml)

User-level configuration for secrets and defaults.

```yaml
mxcp: 1
projects:
  my-project:                  # Project name to match
    profiles:
      default:                 # Profile name
        secrets:
          - name: api_key
            type: env
            key: MY_API_KEY

vault:                         # Global Vault settings
  address: https://vault.example.com
  token_path: ~/.vault-token
```

### Vault Configuration

```yaml
vault:
  address: https://vault.example.com
  token_path: ~/.vault-token
  namespace: admin
  auth_method: token           # token, approle, kubernetes
```

| Field | Type | Description |
|-------|------|-------------|
| `address` | string | Vault server URL |
| `token_path` | string | Path to token file |
| `namespace` | string | Vault namespace |
| `auth_method` | string | Authentication method |

## Complete Example

A complete tool definition with all features:

```yaml
mxcp: 1
tool:
  name: search_orders
  description: Search customer orders with filters
  language: sql

  parameters:
    - name: customer_id
      type: integer
      description: Filter by customer ID
      required: false
      minimum: 1

    - name: status
      type: string
      description: Order status filter
      required: false
      enum: [pending, shipped, delivered, cancelled]
      default: pending

    - name: limit
      type: integer
      description: Maximum results
      required: false
      default: 50
      minimum: 1
      maximum: 1000

  return:
    type: array
    items:
      type: object
      properties:
        order_id:
          type: integer
        customer_id:
          type: integer
        status:
          type: string
        total:
          type: number
        created_at:
          type: string
          format: date-time

  source:
    file: ../sql/search_orders.sql

  tests:
    - name: test_default_status
      arguments:
        - key: customer_id
          value: 1
      result_contains:
        status: pending

    - name: test_limit
      arguments:
        - key: limit
          value: 5
      expect_count: 5
```

## Next Steps

- [Endpoints Concepts](/concepts/endpoints) - How endpoints work
- [Type System](/concepts/type-system) - Detailed type documentation
- [Testing](/quality/testing) - Writing effective tests
- [Configuration](/operations/configuration) - Runtime configuration
