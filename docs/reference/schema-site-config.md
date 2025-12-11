---
title: "Site Configuration Schema"
description: "Complete YAML schema reference for mxcp-site.yml. Project settings, profiles, DuckDB, dbt, extensions, and audit configuration."
sidebar:
  order: 9
---

> **Related Topics:** [Configuration](/operations/configuration) (configuration guide) | [dbt Integration](/integrations/dbt) (dbt setup) | [Auditing](/security/auditing) (audit logs)

This reference documents the complete YAML schema for the `mxcp-site.yml` project configuration file.

## Complete Example

```yaml
mxcp: 1
project: my-analytics
profile: default

secrets:
  - db_credentials
  - api_key

extensions:
  - httpfs
  - parquet
  - name: h3
    repo: community

dbt:
  enabled: true
  model_paths: ["models"]

sql_tools:
  enabled: false

paths:
  tools: tools
  resources: resources
  prompts: prompts
  python: python
  sql: sql

profiles:
  default:
    duckdb:
      path: ./data/app.duckdb
      readonly: false

    drift:
      path: ./drift/snapshot.json

    audit:
      enabled: true
      path: ./audit/logs.jsonl

  production:
    duckdb:
      path: /data/prod.duckdb
      readonly: true

    audit:
      enabled: true
      path: /var/log/mxcp/audit.jsonl
```

## Root Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `mxcp` | integer | Yes | - | Schema version. Must be `1`. |
| `project` | string | Yes | - | Project identifier. Used for matching user config. |
| `profile` | string | Yes | - | Active profile name. Must exist in `profiles`. |
| `secrets` | array | No | - | List of secret names used by the project. |
| `extensions` | array | No | - | DuckDB extensions to load. |
| `dbt` | object | No | - | dbt integration configuration. |
| `sql_tools` | object | No | - | Built-in SQL tools configuration. |
| `paths` | object | No | - | Custom directory paths. |
| `profiles` | object | No | - | Profile-specific configurations. |

## Project and Profile

```yaml
mxcp: 1
project: my-project    # Unique project identifier
profile: default       # Active profile (must exist in profiles section)
```

The `project` name is used to match secrets and authentication in the user configuration file (`~/.mxcp/config.yml`).

The `profile` specifies which profile configuration to use. Switch profiles via:

```bash
mxcp serve --profile production
```

## Secrets

List secret names that the project uses. Actual secret values are defined in the user configuration.

```yaml
secrets:
  - db_credentials     # Database connection
  - api_key           # External API key
  - oauth_secret      # OAuth client secret
```

Secrets are accessed in Python endpoints:

```python
from mxcp.runtime import secrets

api_key = secrets.get("api_key")
```

See [User Configuration Schema](/reference/schema-user-config) for defining secret values.

## Extensions

DuckDB extensions to load automatically.

### Simple Extension Names

```yaml
extensions:
  - httpfs       # HTTP file system
  - parquet      # Parquet file support
  - json         # JSON functions
  - spatial      # Geospatial functions
```

### Extension with Repository

```yaml
extensions:
  - name: h3
    repo: community

  - name: postgres_scanner
    repo: core
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | Yes | Extension name. |
| `repo` | string | No | Repository: `core`, `community`, or custom URL. |

### Common Extensions

| Extension | Purpose |
|-----------|---------|
| `httpfs` | Read files from HTTP/S3 |
| `parquet` | Parquet file support |
| `json` | JSON functions |
| `spatial` | Geospatial functions |
| `postgres_scanner` | Query PostgreSQL |
| `mysql_scanner` | Query MySQL |
| `sqlite_scanner` | Query SQLite |
| `excel` | Read Excel files |
| `h3` | H3 geospatial indexing |

## dbt Configuration

Configure dbt integration for data transformation.

```yaml
dbt:
  enabled: true
  model_paths: ["models"]
  analysis_paths: ["analyses"]
  test_paths: ["tests"]
  seed_paths: ["seeds"]
  macro_paths: ["macros"]
  snapshot_paths: ["snapshots"]
  target_path: "target"
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `enabled` | boolean | `true` | Enable dbt integration. |
| `model_paths` | array | `["models"]` | dbt model directories. |
| `analysis_paths` | array | `["analyses"]` | dbt analysis directories. |
| `test_paths` | array | `["tests"]` | dbt test directories. |
| `seed_paths` | array | `["seeds"]` | dbt seed directories. |
| `macro_paths` | array | `["macros"]` | dbt macro directories. |
| `snapshot_paths` | array | `["snapshots"]` | dbt snapshot directories. |
| `target_path` | string | `"target"` | dbt target directory. |

### dbt Workflow

```bash
# Build dbt models
dbt run

# Run MXCP with dbt tables available
mxcp serve
```

See [dbt Integration](/integrations/dbt) for complete documentation.

## SQL Tools Configuration

Enable built-in SQL tools for direct database access.

```yaml
sql_tools:
  enabled: true
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `enabled` | boolean | `false` | Enable built-in SQL tools. |

When enabled, provides these tools:

| Tool | Description |
|------|-------------|
| `execute_sql_query` | Execute arbitrary SQL queries |
| `list_tables` | List all tables in the database |
| `get_table_schema` | Get schema for a specific table |

**Security Note:** Only enable for trusted environments. Consider using custom tools with proper access controls for production.

## Paths Configuration

Customize directory paths for endpoint definitions.

```yaml
paths:
  tools: tools           # Tool YAML files
  resources: resources   # Resource YAML files
  prompts: prompts       # Prompt YAML files
  python: python         # Python implementation files
  sql: sql              # SQL implementation files
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `tools` | string | `"tools"` | Tool definitions directory. |
| `resources` | string | `"resources"` | Resource definitions directory. |
| `prompts` | string | `"prompts"` | Prompt definitions directory. |
| `python` | string | `"python"` | Python implementations directory. |
| `sql` | string | `"sql"` | SQL implementations directory. |

All paths are relative to the project root.

## Profiles

Define environment-specific configurations.

```yaml
profiles:
  default:
    # Development settings
    duckdb:
      path: ./data/dev.duckdb
      readonly: false
    audit:
      enabled: false

  staging:
    duckdb:
      path: ./data/staging.duckdb
      readonly: false
    audit:
      enabled: true
      path: ./audit/staging.jsonl

  production:
    duckdb:
      path: /data/prod.duckdb
      readonly: true
    audit:
      enabled: true
      path: /var/log/mxcp/audit.jsonl
```

### Profile Configuration

| Field | Type | Description |
|-------|------|-------------|
| `duckdb` | object | DuckDB database configuration. |
| `drift` | object | Drift detection configuration. |
| `audit` | object | Audit logging configuration. |

### DuckDB Configuration

```yaml
duckdb:
  path: ./data/app.duckdb
  readonly: false
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `path` | string | Auto-generated | Database file path. |
| `readonly` | boolean | `false` | Open database in read-only mode. |

**Path Behavior:**
- If not specified, MXCP creates an in-memory database
- Relative paths are resolved from project root
- Use absolute paths for production deployments

### Drift Configuration

```yaml
drift:
  path: ./drift/snapshot.json
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `path` | string | `"./drift/snapshot.json"` | Drift snapshot file path. |

Use drift detection to track schema changes:

```bash
# Create/update snapshot
mxcp drift-snapshot

# Check for changes
mxcp drift-check
```

### Audit Configuration

```yaml
audit:
  enabled: true
  path: ./audit/logs.jsonl
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `enabled` | boolean | `false` | Enable audit logging. |
| `path` | string | Auto-generated | Audit log file path (JSONL format). |

Query audit logs:

```bash
mxcp log --since 1h
mxcp log --tool my_tool
mxcp log --status error
```

See [Auditing](/security/auditing) for complete documentation.

## Environment-Specific Examples

### Development

```yaml
mxcp: 1
project: my-app
profile: default

dbt:
  enabled: true

sql_tools:
  enabled: true  # Convenient for development

profiles:
  default:
    duckdb:
      path: ./data/dev.duckdb
      readonly: false
    audit:
      enabled: false
```

### Production

```yaml
mxcp: 1
project: my-app
profile: production

secrets:
  - db_credentials

extensions:
  - httpfs
  - parquet

dbt:
  enabled: true

sql_tools:
  enabled: false  # Disabled for security

profiles:
  production:
    duckdb:
      path: /data/prod.duckdb
      readonly: true
    drift:
      path: /var/lib/mxcp/drift.json
    audit:
      enabled: true
      path: /var/log/mxcp/audit.jsonl
```

### Multi-Environment

```yaml
mxcp: 1
project: analytics-platform
profile: default

secrets:
  - warehouse_credentials
  - api_keys

extensions:
  - httpfs
  - parquet
  - postgres_scanner

profiles:
  default:
    duckdb:
      path: ./data/local.duckdb
    audit:
      enabled: false

  staging:
    duckdb:
      path: ${STAGING_DB_PATH}
    audit:
      enabled: true
      path: ./logs/staging-audit.jsonl

  production:
    duckdb:
      path: ${PROD_DB_PATH}
      readonly: true
    audit:
      enabled: true
      path: /var/log/mxcp/production-audit.jsonl
```

## Environment Variables

Use environment variables in configuration:

```yaml
profiles:
  production:
    duckdb:
      path: ${DATABASE_PATH}
    audit:
      path: ${AUDIT_LOG_PATH}
```

Environment variables are expanded at runtime.

## Validation

Validate your site configuration:

```bash
mxcp validate
```

Common validation errors:

| Error | Solution |
|-------|----------|
| `profile not found` | Ensure `profile` value exists in `profiles` |
| `missing required field` | Add `mxcp`, `project`, and `profile` |
| `invalid extension` | Check extension name and repository |

## Next Steps

- [User Configuration Schema](/reference/schema-user-config) - Configure secrets and authentication
- [Configuration Guide](/operations/configuration) - Complete configuration documentation
- [dbt Integration](/integrations/dbt) - Set up data transformation
- [Auditing](/security/auditing) - Configure audit logging
