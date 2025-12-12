---
title: "Glossary"
description: "Key terms and concepts in MXCP. Quick reference for understanding MCP endpoints, policies, CEL expressions, and other terminology."
sidebar:
  order: 3
---

Quick reference for key terms used throughout MXCP documentation.

## Core Concepts

### MCP (Model Context Protocol)
An open standard that enables AI assistants to interact with external tools and data. MXCP implements and extends this protocol. See [Introduction](/getting-started/introduction/).

### Endpoint
A function or data source exposed to AI clients. MXCP supports three types: [tools](#tool), [resources](#resource), and [prompts](#prompt). See [Endpoints](/concepts/endpoints/).

### Tool
An endpoint that performs actions. Tools have parameters (inputs) and return values (outputs). AI can call tools to query data, perform calculations, or execute operations.

```yaml
tool:
  name: get_user
  description: Retrieve user by ID
```

### Resource
A data source with a URI pattern. Resources are read-only and identified by URIs like `users://{id}`.

```yaml
resource:
  uri: users://{id}
  description: User profile data
```

### Prompt
A reusable message template with Jinja2 templating. Prompts help standardize AI interactions.

```yaml
prompt:
  name: analyze_data
  template: "Analyze this data: {{ data }}"
```

## Endpoint Metadata

### Annotations
Behavioral hints that help AI models use endpoints safely. Defined in endpoint YAML files.

```yaml
annotations:
  readOnlyHint: true      # Endpoint doesn't modify data
  idempotentHint: true    # Safe to retry
  openWorldHint: false    # Results are complete
```

### Tags
Labels for categorizing and discovering endpoints. Useful for organizing large projects.

```yaml
tags:
  - analytics
  - reporting
```

### Examples
Sample values that help AI models understand how to use parameters correctly.

```yaml
parameters:
  - name: region
    type: string
    description: Sales region
    examples: ["North", "South", "East", "West"]
```

## Security Terms

### CEL (Common Expression Language)
A simple expression language used for writing [policy](#policy) conditions. CEL expressions evaluate to true or false. See [Policies](/security/policies/).

```yaml
# CEL expression examples
condition: "user.role == 'admin'"
condition: "'read' in user.permissions"
condition: "user.email.endsWith('@company.com')"
```

### Policy
A rule that controls access to endpoints. Policies use [CEL](#cel-common-expression-language) expressions and are evaluated before (input) or after (output) execution.

### Input Policy
A policy evaluated **before** endpoint execution. Can deny requests based on user context or parameters.

**Available action:** `deny`

### Output Policy
A policy evaluated **after** endpoint execution. Can deny, filter, or mask fields in responses.

**Available actions:** `deny`, `filter_fields`, `filter_sensitive_fields`, `mask_fields`

### Policy Actions

**Input policy actions:**
- `deny` - Block the request

**Output policy actions:**
- `deny` - Block the response
- `filter_fields` - Remove specific fields from response
- `filter_sensitive_fields` - Remove fields marked with `sensitive: true`
- `mask_fields` - Replace field values with `"****"`

### Sensitive Field
A return type field marked as containing sensitive data. Used with `filter_sensitive_fields` policy action.

```yaml
return:
  type: object
  properties:
    name:
      type: string
    ssn:
      type: string
      sensitive: true  # Will be filtered by filter_sensitive_fields
```

### User Context
Information about the authenticated user, available in policies and SQL. See [Authentication](/security/authentication/).
- `user.role` - User's role
- `user.permissions` - Array of permissions
- `user.email` - User's email
- `user.id` - User identifier

## Configuration Terms

### Site Configuration (`mxcp-site.yml`)
Project-specific settings stored in your repository. Defines project name, profiles, extensions, and audit settings. See [Configuration](/operations/configuration/).

### User Configuration (`~/.mxcp/config.yml`)
User-specific settings stored outside the repository. Contains secrets, OAuth credentials, and per-project configurations.

### Profile
A named configuration set for different environments (development, staging, production). Select with `--profile` flag.

### Secret
Sensitive configuration values like API keys and passwords. Stored in user configuration or secret managers (Vault, 1Password), never in version control. See [Configuration](/operations/configuration/#secret-types).

## Data Terms

### DuckDB
The analytical SQL database engine that MXCP uses for SQL endpoints. Supports PostgreSQL syntax with analytical extensions. See [DuckDB Integration](/integrations/duckdb/).

### dbt (data build tool)
A transformation framework that MXCP integrates with. Run dbt to create tables and views that endpoints can query. See [dbt Integration](/integrations/dbt/).

### Parameter Binding
How endpoint parameters are passed to SQL queries. Use `$parameter_name` syntax:

```sql
SELECT * FROM users WHERE id = $user_id
```

### Return Type
The schema that defines what an endpoint outputs. MXCP validates responses against this schema. See [Type System](/concepts/type-system/).

## Quality Terms

### Validation
Checking that endpoints are correctly defined (YAML syntax, required fields, type schemas). Run with `mxcp validate`. See [Validation](/quality/validation/).

### Testing
Running assertions against endpoint outputs. Tests are defined in endpoint YAML files. Run with `mxcp test`. See [Testing](/quality/testing/).

### Test Assertion
A condition that verifies endpoint behavior. Common assertions:
- `result` - Exact match (use `result: null` to check for null)
- `result_contains` - Partial object match
- `result_not_contains` - List of fields that must NOT exist
- `result_contains_item` - Array contains matching item
- `result_contains_all` - Array contains all specified items
- `result_length` - Array has exact item count
- `result_contains_text` - String contains substring

### Linting
Checking metadata quality for better AI comprehension (descriptions, examples, annotations). Run with `mxcp lint`. See [Linting](/quality/linting/).

### Evals (Evaluations)
Testing how AI models interact with your endpoints. Ensures AI uses tools correctly and safely. See [Evals](/quality/evals/).

### Drift Detection
Monitoring for changes in endpoint schemas between environments. Helps catch unintended changes. Run with `mxcp drift-snapshot` and `mxcp drift-check`.

## Operations Terms

### Transport
How MXCP communicates with clients:
- `stdio` - Standard input/output (default, for Claude Desktop)
- `streamable-http` - HTTP with streaming support
- `sse` - Server-sent events

See [CLI Reference](/reference/cli/#mxcp-serve).

### Audit Logging
Recording every endpoint execution for compliance and debugging. Can be stored as JSONL files or in a database. See [Auditing](/security/auditing/).

### Hot Reload
Updating configuration without restarting the server. Triggered by SIGHUP signal or via [Admin Socket](#admin-socket).

### Admin Socket
A Unix socket for server management (health checks, status, configuration reloads). See [Admin Socket](/operations/admin-socket/).

## Runtime Terms

### Runtime API
Python functions available in Python endpoints. See [Python Reference](/reference/python/).
- `db` - Database access
- `config` - Configuration access
- `plugins` - Plugin access

### Lifecycle Hooks
Decorators for functions called at server lifecycle events:
- `@on_init` - Called once when server starts
- `@on_shutdown` - Called when server stops

### reload_duckdb()
Function to request an asynchronous system reload. The reload sequence:
1. Drains active requests (waits for completion)
2. Shuts down runtime components (Python + DuckDB)
3. Runs your optional payload function (if provided)
4. Restarts runtime components

**When to use:** Only use `reload_duckdb()` when external tools need exclusive access to the database file (e.g., replacing the file). For normal database operations, use the `db` proxy directly.

See [Python Reference](/reference/python/#reload_duckdb).

### UDF (User Defined Function)
A custom SQL function implemented in Python via plugins. See [Plugins](/reference/plugins/).

## File Types

| Extension | Purpose |
|-----------|---------|
| `.yml` | Endpoint definitions, configuration |
| `.sql` | SQL implementations |
| `.py` | Python implementations |
| `.jsonl` | Audit logs (JSON Lines format) |
| `.json` | Drift snapshots |

## Common Abbreviations

| Abbreviation | Meaning |
|--------------|---------|
| CEL | Common Expression Language |
| dbt | data build tool |
| JSONL | JSON Lines (newline-delimited JSON) |
| MCP | Model Context Protocol |
| MXCP | MCP eXtension Platform |
| OAuth | Open Authorization |
| OTEL | OpenTelemetry |
| PII | Personally Identifiable Information |
| SSE | Server-Sent Events |
| UDF | User Defined Function |

## Next Steps

- [Introduction](/getting-started/introduction/) - Full MXCP overview
- [Quickstart](/getting-started/quickstart/) - Start building
- [Concepts](/concepts/) - Deep dive into concepts
