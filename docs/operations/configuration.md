---
title: "Configuration"
description: "Complete MXCP configuration reference. Site config, user config, profiles, secrets, and environment variables."
sidebar:
  order: 2
---

> **Related Topics:** [Deployment](deployment) (production setup) | [Authentication](/security/authentication) (OAuth secrets) | [Project Structure](/concepts/project-structure) (config file location) | [Common Tasks](/reference/common-tasks#how-do-i-use-secrets) (quick how-to)

MXCP uses two configuration files: site configuration for project settings and user configuration for secrets and authentication.

## Configuration Files

### Site Configuration (`mxcp-site.yml`)

Project-specific settings stored in your repository:

```yaml
mxcp: 1
project: my-project
profile: default

# Secrets used by this project
secrets:
  - db_credentials
  - api_key

# DuckDB extensions
extensions:
  - httpfs
  - parquet
  - name: h3
    repo: community

# dbt integration
dbt:
  enabled: true
  model_paths: ["models"]

# SQL tools (disabled by default)
sql_tools:
  enabled: false

# Profile-specific settings
profiles:
  default:
    duckdb:
      path: db.duckdb
      readonly: false
    drift:
      path: drift/snapshot.json
    audit:
      enabled: false

  production:
    duckdb:
      path: /data/mxcp.duckdb
      readonly: true
    drift:
      path: /data/drift.json
    audit:
      enabled: true
      path: /var/log/mxcp/audit.jsonl
```

### User Configuration (`~/.mxcp/config.yml`)

User-specific settings with secrets and authentication:

```yaml
mxcp: 1

# Transport defaults
transport:
  provider: streamable-http
  http:
    port: 8000
    host: localhost
    stateless: false

# Vault integration
vault:
  enabled: true
  address: https://vault.example.com
  token_env: VAULT_TOKEN

# 1Password integration
onepassword:
  enabled: true
  token_env: OP_SERVICE_ACCOUNT_TOKEN

# Project-specific settings
projects:
  my-project:
    profiles:
      default:
        secrets:
          - name: db_credentials
            type: database
            parameters:
              host: localhost
              port: 5432
              database: mydb
              username: user
              password: "vault://secret/db#password"

        auth:
          provider: github
          github:
            client_id: your_client_id
            client_secret: your_client_secret

# Model configuration for evals
models:
  default: claude-4-sonnet
  models:
    claude-4-sonnet:
      type: claude
      api_key: "${ANTHROPIC_API_KEY}"
      timeout: 30
```

## Dynamic Value Interpolation

MXCP supports three methods for injecting values dynamically:

### Environment Variables

Use `${VAR_NAME}` syntax:

```yaml
parameters:
  host: "${DB_HOST}"
  port: "${DB_PORT}"
```

### Vault Secrets

Use `vault://` URLs:

```yaml
parameters:
  password: "vault://secret/database#password"
  api_key: "vault://secret/api#key"
```

Format: `vault://path/to/secret#key`

### File References

Use `file://` URLs:

```yaml
parameters:
  cert: "file:///etc/ssl/certs/server.crt"
  key: "file://keys/server.key"
```

### 1Password Secrets

Use `op://` URLs:

```yaml
parameters:
  password: "op://vault/database-creds/password"
  totp: "op://vault/database-creds/totp?attribute=otp"
```

Format: `op://vault/item/field[?attribute=otp]`

### Combining Methods

```yaml
secrets:
  - name: app_config
    parameters:
      db_host: "${DB_HOST}"                       # Environment
      db_password: "vault://secret/db#password"   # Vault
      api_key: "op://Private/api-keys/production" # 1Password
      ssl_cert: "file:///etc/ssl/app.crt"         # File
```

## Profile Configuration

Profiles allow environment-specific settings:

```yaml
profiles:
  development:
    duckdb:
      path: dev.duckdb
      readonly: false
    audit:
      enabled: false

  staging:
    duckdb:
      path: staging.duckdb
      readonly: false
    audit:
      enabled: true
      path: audit/staging.jsonl

  production:
    duckdb:
      path: prod.duckdb
      readonly: true
    audit:
      enabled: true
      path: /var/log/mxcp/audit.jsonl
```

Select profile:

```bash
# Command line
mxcp serve --profile production

# Environment variable
export MXCP_PROFILE=production
mxcp serve
```

## DuckDB Configuration

### Basic Settings

```yaml
profiles:
  default:
    duckdb:
      path: data/myapp.duckdb  # Database file path (default: data/db-{profile}.duckdb)
      readonly: false          # Read-only mode
```

If `path` is not specified, MXCP creates the database at `data/db-{profile_name}.duckdb` (e.g., `data/db-default.duckdb` for the default profile).

### Extensions

Load DuckDB extensions:

```yaml
extensions:
  # Core extensions
  - httpfs
  - parquet
  - json

  # Community extensions
  - name: h3
    repo: community

  # Nightly extensions
  - name: uc_catalog
    repo: core_nightly
```

### DuckDB Path Override

Override database path via environment:

```bash
MXCP_DUCKDB_PATH=/tmp/test.duckdb mxcp serve
```

## Transport Configuration

Configure default transport settings:

```yaml
transport:
  provider: streamable-http  # streamable-http, sse, or stdio
  http:
    port: 8000
    host: localhost
    stateless: false  # For serverless deployments
```

Transport options:
- `streamable-http` - HTTP with streaming (default)
- `sse` - Server-sent events
- `stdio` - Standard input/output (for Claude Desktop)

## Secret Types

### Database Credentials

```yaml
secrets:
  - name: db_credentials
    type: database
    parameters:
      host: localhost
      port: 5432
      database: mydb
      username: user
      password: secret
```

### API Credentials

```yaml
secrets:
  - name: api_credentials
    type: api
    parameters:
      api_key: your-key
      api_url: https://api.example.com
```

### Custom Secrets

```yaml
secrets:
  - name: custom_config
    type: custom
    parameters:
      key1: value1
      key2: value2
```

## Vault Integration

Enable HashiCorp Vault:

```yaml
vault:
  enabled: true
  address: "https://vault.example.com"
  token_env: "VAULT_TOKEN"  # Environment variable with token
```

Requirements:
- Install: `pip install "mxcp[vault]"`
- Set `VAULT_TOKEN` environment variable
- Vault must be accessible

Supported engines:
- KV Secrets Engine v2 (default)
- KV Secrets Engine v1 (fallback)

## 1Password Integration

Enable 1Password service account:

```yaml
onepassword:
  enabled: true
  token_env: "OP_SERVICE_ACCOUNT_TOKEN"
```

Requirements:
- Install: `pip install "mxcp[onepassword]"`
- Create service account in 1Password
- Set `OP_SERVICE_ACCOUNT_TOKEN` environment variable

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `MXCP_CONFIG` | User config path | `~/.mxcp/config.yml` |
| `MXCP_PROFILE` | Active profile | `default` |
| `MXCP_DEBUG` | Debug logging | `false` |
| `MXCP_READONLY` | Read-only mode | `false` |
| `MXCP_DUCKDB_PATH` | Override DuckDB path | from config |
| `MXCP_DISABLE_ANALYTICS` | Disable analytics | `false` |
| `MXCP_ADMIN_ENABLED` | Enable admin API | `false` |
| `MXCP_ADMIN_SOCKET` | Admin socket path | `/run/mxcp/mxcp.sock` |

## Configuration Reload

For long-running servers, reload configuration without restart:

```bash
# Send SIGHUP signal
kill -HUP $(pgrep -f "mxcp serve")

# Or use admin socket
curl --unix-socket /run/mxcp/mxcp.sock -X POST http://localhost/reload
```

**Reload Process:**
1. SIGHUP handler waits synchronously (up to 60 seconds)
2. Only external references are refreshed (not the configuration file structure)
3. Service remains available - new requests wait while reload completes
4. Automatic rollback on failure - if new values cause errors, server continues with old values

**What gets reloaded:**
- Vault secrets (`vault://`)
- File contents (`file://`)
- Environment variables (`${VAR}`)
- DuckDB connection (always recreated to pick up database changes)
- Python runtimes with updated configs

**What does NOT reload:**
- Configuration file structure
- OAuth provider settings
- Server host/port
- Registered endpoints

**Note:** The DuckDB connection is always recreated during a reload, regardless of whether configuration values have changed. This ensures any external changes to the database file (new tables, data updates) are visible after reload.

## Model Configuration

Configure models for LLM evaluations:

```yaml
models:
  default: claude-4-sonnet

  models:
    claude-4-sonnet:
      type: claude
      api_key: "${ANTHROPIC_API_KEY}"
      timeout: 30
      max_retries: 3

    gpt-4o:
      type: openai
      api_key: "${OPENAI_API_KEY}"
      base_url: https://api.openai.com/v1
      timeout: 45
```

## Validation

Validate configuration:

```bash
mxcp validate
```

This checks:
- YAML syntax
- Required fields
- File references
- Extension availability

## Best Practices

### 1. Never Commit Secrets
Keep secrets in `~/.mxcp/config.yml`, not in the repository.

### 2. Use Environment Variables
For CI/CD and containers:
```yaml
password: "${DB_PASSWORD}"
```

### 3. Use Profiles
Separate development from production:
```yaml
profiles:
  dev: ...
  prod: ...
```

### 4. Validate Early
Run `mxcp validate` before deployment.

### 5. Document Configuration
Comment complex configurations.

## Troubleshooting

### "Config file not found"
- Check path: `~/.mxcp/config.yml`
- Override: `MXCP_CONFIG=/path/to/config.yml`

### "Secret not resolved"
- Check Vault/1Password is enabled
- Verify token is set
- Check secret path

### "Profile not found"
- Verify profile name in `mxcp-site.yml`
- Check for typos

## Next Steps

- [Deployment](deployment) - Deploy to production
- [Monitoring](monitoring) - Set up observability
- [Authentication](/security/authentication) - Configure OAuth
