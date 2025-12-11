---
title: "Glossary"
description: "Key terms and concepts in MXCP. Quick reference for understanding MCP endpoints, policies, CEL expressions, and other terminology."
sidebar:
  order: 3
---

Quick reference for key terms used throughout MXCP documentation.

## Core Concepts

### MCP (Model Context Protocol)
An open standard that enables AI assistants to interact with external tools and data. MXCP implements and extends this protocol.

### Endpoint
A function or data source exposed to AI clients. MXCP supports three types: tools, resources, and prompts.

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

## Security Terms

### CEL (Common Expression Language)
A simple expression language used for writing policy conditions. CEL expressions evaluate to true or false.

```yaml
# CEL expression examples
condition: "user.role == 'admin'"
condition: "'read' in user.permissions"
condition: "user.email.endsWith('@company.com')"
```

### Input Policy
A policy evaluated **before** endpoint execution. Can deny requests or log warnings.

### Output Policy
A policy evaluated **after** endpoint execution. Can filter or mask fields in responses.

### Policy Action
What happens when a policy condition matches:
- `deny` - Block the request
- `warn` - Log a warning but allow
- `filter_fields` - Remove specific fields
- `filter_sensitive_fields` - Remove fields marked sensitive
- `mask_fields` - Replace field values with placeholders

### User Context
Information about the authenticated user, available in policies and SQL:
- `user.role` - User's role
- `user.permissions` - Array of permissions
- `user.email` - User's email
- `user.id` - User identifier

## Configuration Terms

### Site Configuration (`mxcp-site.yml`)
Project-specific settings stored in your repository. Defines project name, profiles, extensions, and audit settings.

### User Configuration (`~/.mxcp/config.yml`)
User-specific settings stored outside the repository. Contains secrets, OAuth credentials, and per-project configurations.

### Profile
A named configuration set for different environments (development, staging, production). Select with `--profile` flag.

### Secret
Sensitive configuration values like API keys and passwords. Stored in user configuration, never in version control.

## Data Terms

### DuckDB
The analytical SQL database engine that MXCP uses for SQL endpoints. Supports PostgreSQL syntax with analytical extensions.

### dbt (data build tool)
A transformation framework that MXCP can integrate with. dbt models create tables and views that endpoints can query.

### Parameter Binding
How endpoint parameters are passed to SQL queries. Use `$parameter_name` syntax:

```sql
SELECT * FROM users WHERE id = $user_id
```

### Return Type
The schema that defines what an endpoint outputs. MXCP validates responses against this schema.

## Quality Terms

### Validation
Checking that endpoints are correctly defined. Run with `mxcp validate`.

### Testing
Running assertions against endpoint outputs. Tests are defined in endpoint YAML files.

### Linting
Checking metadata quality for better AI comprehension. Run with `mxcp lint`.

### Evals (Evaluations)
Testing how AI models interact with your endpoints. Ensures AI uses tools correctly and safely.

### Drift Detection
Monitoring for changes in endpoint schemas between environments. Helps catch unintended changes.

## Operations Terms

### Transport
How MXCP communicates with clients:
- `stdio` - Standard input/output (for Claude Desktop)
- `streamable-http` - HTTP with streaming
- `sse` - Server-sent events

### Audit Logging
Recording every endpoint execution for compliance and debugging. Stored in JSONL format.

### Hot Reload
Updating configuration without restarting the server. Triggered by SIGHUP signal.

### Admin Socket
A Unix socket for server management (health checks, status, reloads).

## Runtime Terms

### Runtime API
Python functions available in Python endpoints:
- `db` - Database access
- `config` - Configuration access
- `plugins` - Plugin access

### Lifecycle Hooks
Functions called at server lifecycle events:
- `@on_init` - Server startup
- `@on_shutdown` - Server shutdown
- `@on_reload` - Configuration reload

### UDF (User Defined Function)
A custom SQL function implemented in Python via plugins.

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
| MCP | Model Context Protocol |
| MXCP | MCP eXtension Platform |
| CEL | Common Expression Language |
| dbt | data build tool |
| UDF | User Defined Function |
| OAuth | Open Authorization |
| OTEL | OpenTelemetry |
| PII | Personally Identifiable Information |

## Next Steps

- [Introduction](introduction) - Full MXCP overview
- [Quickstart](quickstart) - Start building
- [Concepts](/concepts/) - Deep dive into concepts
