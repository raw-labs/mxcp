---
title: "YAML Schemas"
description: "Overview of all MXCP YAML configuration files with links to detailed schema references for tools, resources, prompts, and configuration."
sidebar:
  order: 1
---

> **Related Topics:** [Endpoints](/concepts/endpoints) (endpoint types) | [Type System](/concepts/type-system) (parameter types) | [Configuration](/operations/configuration) (runtime config) | [Validation](/quality/validation) (check syntax)

This page provides an overview of all YAML configuration files in MXCP. Click through to detailed schema references for complete documentation.

## Schema References

| Schema | File Location | Description |
|--------|---------------|-------------|
| [Tool Schema](/schemas/tool) | `tools/*.yml` | Tool endpoint definitions |
| [Resource Schema](/schemas/resource) | `resources/*.yml` | Resource endpoint definitions |
| [Prompt Schema](/schemas/prompt) | `prompts/*.yml` | Prompt endpoint definitions |
| [Site Configuration](/schemas/site-config) | `mxcp-site.yml` | Project configuration |
| [User Configuration](/schemas/user-config) | `~/.mxcp/config.yml` | User-level settings and secrets |

## File Types Overview

### Endpoint Definitions

Endpoints are the core building blocks of MXCP. Each type has its own schema:

**[Tools](/schemas/tool)** - Callable functions that AI agents can invoke:

```yaml
mxcp: 1
tool:
  name: get_user
  description: Retrieve user by ID
  parameters:
    - name: user_id
      type: integer
  source:
    file: ../sql/get_user.sql
```

**[Resources](/schemas/resource)** - Data accessible via URI patterns:

```yaml
mxcp: 1
resource:
  uri: "user://{user_id}/profile"
  name: User Profile
  source:
    file: ../sql/user_profile.sql
```

**[Prompts](/schemas/prompt)** - Templated conversation starters:

```yaml
mxcp: 1
prompt:
  name: analyze_data
  description: Analyze data with customizable focus
  parameters:
    - name: topic
      type: string
  messages:
    - role: system
      type: text
      prompt: "You are an expert analyst."
    - role: user
      type: text
      prompt: "Analyze: {{ topic }}"
```

### Configuration Files

**[Site Configuration](/schemas/site-config)** (`mxcp-site.yml`) - Project-level settings:

```yaml
mxcp: 1
project: my-project
profile: default

extensions:
  - httpfs
  - parquet

profiles:
  default:
    duckdb:
      path: ./data/app.duckdb
    audit:
      enabled: true
```

**[User Configuration](/schemas/user-config)** (`~/.mxcp/config.yml`) - User-level secrets and auth:

```yaml
mxcp: 1
projects:
  my-project:
    profiles:
      default:
        secrets:
          - name: api_key
            type: api
            parameters:
              api_key: "${MY_API_KEY}"
        auth:
          provider: github
          github:
            client_id: Ov23li...
            client_secret: "${GITHUB_SECRET}"
            callback_path: /callback
```

## Common Schema Elements

### Schema Version

All MXCP YAML files start with the schema version:

```yaml
mxcp: 1    # Required, always 1
```

### Parameters

Parameters are shared across tools, resources, and prompts:

```yaml
parameters:
  - name: user_id          # Required: identifier
    type: integer          # Required: data type
    description: User ID   # Recommended: description
    default: null          # Optional: makes parameter optional
    minimum: 1             # Optional: validation constraint
```

See [Type System](/concepts/type-system) for complete type documentation.

### Source

Tools and resources require a source definition:

```yaml
# Inline code
source:
  code: |
    SELECT * FROM users WHERE id = $user_id

# External file
source:
  file: ../sql/get_user.sql
```

### Tests

All endpoint types support inline tests:

```yaml
tests:
  - name: test_basic
    arguments:
      - key: user_id
        value: 1
    result_contains:
      name: "Alice"
```

See [Testing](/quality/testing) for complete documentation.

### Policies

Tools and resources support access control policies:

```yaml
policies:
  input:
    - condition: "user.role == 'guest'"
      action: deny
      reason: "Guests cannot access this endpoint"
  output:
    - condition: "user.role != 'admin'"
      action: filter_fields
      fields: ["salary", "ssn"]
```

See [Policies](/security/policies) for complete documentation.

## Validation

Validate all YAML files:

```bash
# Validate entire project
mxcp validate

# Validate specific file
mxcp validate tools/my-tool.yml

# Verbose output
mxcp validate --debug
```

## Quick Reference

### Required Fields by Type

| Type | Required Fields |
|------|-----------------|
| Tool | `mxcp`, `tool.name`, `tool.source` |
| Resource | `mxcp`, `resource.uri`, `resource.source` |
| Prompt | `mxcp`, `prompt.name`, `prompt.description`, `prompt.messages` |
| Site Config | `mxcp`, `project`, `profile` |
| User Config | `mxcp` |

### Data Types

| Type | Description | Example |
|------|-------------|---------|
| `string` | Text value | `"hello"` |
| `integer` | Whole number | `42` |
| `number` | Decimal number | `3.14` |
| `boolean` | True/false | `true` |
| `array` | List of items | `[1, 2, 3]` |
| `object` | Key-value pairs | `{key: value}` |

### Policy Actions

| Action | Type | Description |
|--------|------|-------------|
| `deny` | input | Block the request |
| `filter_fields` | output | Remove specified fields |
| `mask_fields` | output | Mask field values |
| `filter_sensitive_fields` | output | Remove sensitive fields |

## Next Steps

- [Tool Schema](/schemas/tool) - Complete tool reference
- [Resource Schema](/schemas/resource) - Complete resource reference
- [Prompt Schema](/schemas/prompt) - Complete prompt reference
- [Site Configuration](/schemas/site-config) - Project configuration
- [User Configuration](/schemas/user-config) - Secrets and authentication
