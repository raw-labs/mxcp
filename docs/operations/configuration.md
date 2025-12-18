---
title: "Configuration"
description: "Complete MXCP configuration reference. Site config, user config, profiles, secrets, and environment variables."
sidebar:
  order: 2
---

> **Related Topics:** [Deployment](/operations/deployment) (production setup) | [Authentication](/security/authentication) (OAuth setup) | [Project Structure](/concepts/project-structure) (file locations)

MXCP uses **two configuration files** with distinct purposes:

| File | Location | Purpose | Commit to Git? |
|------|----------|---------|----------------|
| `mxcp-site.yml` | Project root | Project settings, profiles, extensions | Yes |
| `config.yml` | `~/.mxcp/` | Secrets, credentials, auth tokens | **Never** |

This separation ensures secrets stay out of your repository while project structure remains version-controlled.

## Quick Start

**Minimal site configuration** (`mxcp-site.yml`):

```yaml
mxcp: 1
project: my-project
profile: default
```

That's it. MXCP will:
- Create a DuckDB database at `data/db-default.duckdb`
- Look for endpoints in `tools/`, `resources/`, `prompts/`
- Use default settings for everything else

**User configuration** (`~/.mxcp/config.yml`) is optional for local development without secrets.

## Site Configuration

The `mxcp-site.yml` file lives in your project root and defines project structure.

### Required Fields

```yaml
mxcp: 1              # Schema version (always 1)
project: my-project  # Project name (used to match user config)
profile: default     # Active profile name
```

### Profiles

Profiles let you have different settings per environment:

```yaml
mxcp: 1
project: my-project
profile: default

profiles:
  default:
    duckdb:
      path: data/dev.duckdb
      readonly: false
    audit:
      enabled: false

  production:
    duckdb:
      path: /data/mxcp.duckdb
      readonly: true
    audit:
      enabled: true
      path: /var/log/mxcp/audit.jsonl
```

Switch profiles:

```bash
# Command line
mxcp serve --profile production

# Environment variable
export MXCP_PROFILE=production
```

### Profile Settings

Each profile can configure:

| Setting | Description | Default |
|---------|-------------|---------|
| `duckdb.path` | Database file location | `data/db-{profile}.duckdb` |
| `duckdb.readonly` | Read-only mode | `false` |
| `drift.path` | Drift snapshot location | `drift/drift-{profile}.json` |
| `audit.enabled` | Enable audit logging | `false` |
| `audit.path` | Audit log location | `audit/logs-{profile}.jsonl` |

**Drift Detection:**
The `drift.path` specifies where to store the drift snapshot file. This is used by `mxcp drift-snapshot` to create a baseline and `mxcp drift-check` to detect schema changes. Use separate paths per profile to avoid conflicts. See [Validation](/quality/validation) for details.

### DuckDB Extensions

Load DuckDB extensions for additional functionality:

```yaml
extensions:
  # Core extensions (simple string format)
  - httpfs
  - parquet
  - json

  # Community extensions (object format)
  - name: h3
    repo: community

  # Nightly extensions
  - name: uc_catalog
    repo: core_nightly
```

### dbt Integration

Enable dbt for data transformations:

```yaml
dbt:
  enabled: true
  model_paths: ["models"]
  test_paths: ["tests"]
```

See [dbt Integration](/integrations/dbt) for details.

### SQL Tools

Enable built-in SQL query tools:

```yaml
sql_tools:
  enabled: true  # Disabled by default
```

### Declaring Secrets

List the secrets your project needs (values are defined in user config):

```yaml
secrets:
  - db_credentials
  - api_key
```

## User Configuration

The `~/.mxcp/config.yml` file stores secrets and credentials outside your repository.

### Structure

```yaml
mxcp: 1

# Global settings (apply to all projects)
transport:
  provider: streamable-http
  http:
    port: 8000
    host: localhost

vault:
  enabled: true
  address: https://vault.example.com
  token_env: VAULT_TOKEN

# Project-specific settings
projects:
  my-project:           # Must match project name in mxcp-site.yml
    profiles:
      default:          # Must match profile name
        secrets:
          - name: db_credentials
            type: database
            parameters:
              host: localhost
              port: "5432"
              database: mydb
              username: user
              password: "${DB_PASSWORD}"
```

### Why the Deep Nesting?

The `projects.{name}.profiles.{name}` structure allows:
- **Multiple projects**: One user config can serve multiple MXCP projects
- **Multiple profiles**: Different credentials for dev/staging/production
- **Separation of concerns**: Global settings (vault, transport) vs project-specific (secrets, auth)

## Secrets

Secrets bridge site config and user config. Here's the complete workflow:

### 1. Declare in Site Config

```yaml
# mxcp-site.yml
secrets:
  - db_credentials
```

### 2. Define in User Config

```yaml
# ~/.mxcp/config.yml
projects:
  my-project:
    profiles:
      default:
        secrets:
          - name: db_credentials
            type: database
            parameters:
              host: localhost
              port: "5432"
              database: mydb
              username: admin
              password: "${DB_PASSWORD}"
```

### 3. Use in Endpoints

**In Python endpoints**, access secrets via the runtime:

```python title="python/api_client.py"
from mxcp.runtime import config

def call_external_api(query: str) -> dict:
    # Get secret parameters as dict
    api_creds = config.get_secret("api_credentials")
    if api_creds:
        api_key = api_creds.get("api_key")
        api_url = api_creds.get("api_url")

    # Use credentials...
    return {"result": "..."}
```

**For DuckDB extensions** (httpfs, postgres_scanner), secrets are automatically applied based on type. See [DuckDB Integration](/integrations/duckdb) for details.

### Secret Types

| Type | Purpose | Common Parameters |
|------|---------|-------------------|
| `database` | Database connections | `host`, `port`, `database`, `username`, `password` |
| `api` | API credentials | `api_key`, `api_url`, `api_secret` |
| `custom` | Any key-value pairs | Any parameters you need |

The type is informational and helps organize your secrets. All types work the same way.

## Dynamic Values

MXCP supports four methods for injecting values at runtime:

### Environment Variables

```yaml
password: "${DB_PASSWORD}"
host: "${DB_HOST}"
```

**Note:** Default value syntax (`${VAR:-default}`) is not supported. Environment variables must be set or the configuration will fail to load.

### HashiCorp Vault

```yaml
password: "vault://secret/database#password"
api_key: "vault://secret/api#key"
```

Format: `vault://path/to/secret#field`
- `path/to/secret`: The path to the secret in Vault
- `field`: The specific key within that secret

Requires:
```bash
pip install "mxcp[vault]"
export VAULT_TOKEN=your-token
```

**Supported Secret Engines:** KV Secrets Engine v2 (default), KV v1 (fallback)

### 1Password

```yaml
password: "op://vault/database-creds/password"
totp: "op://vault/database-creds/totp?attribute=otp"
```

Format: `op://vault/item/field[?attribute=otp]`
- `vault`: The name or ID of the vault in 1Password
- `item`: The name or ID of the item in 1Password
- `field`: The name or ID of the field within the item
- `?attribute=otp`: Optional parameter to retrieve TOTP/OTP value

Requires:
```bash
pip install "mxcp[onepassword]"
export OP_SERVICE_ACCOUNT_TOKEN=your-token
```

**Examples:**
- Basic field: `op://Private/Login Item/username`
- TOTP/OTP: `op://Private/Login Item/totp?attribute=otp`
- Using vault ID: `op://hfnjvi6aymbsnfc2gshk5b6o5q/Login Item/password`
- Using item ID: `op://Private/j5hbqmr7nz3uqsw3j5qam2fgji/password`

### File References

Read configuration values from local files. Useful for:
- Loading certificates or keys from files
- Reading API tokens from secure file locations
- Separating sensitive data from configuration files

```yaml
cert: "file:///etc/ssl/certs/server.crt"
key: "file://./keys/server.key"  # Relative path
```

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

### Error Handling

If any referenced value cannot be resolved (missing environment variable, Vault secret, or file), MXCP raises an error when loading the configuration. This ensures configuration issues are caught early rather than at runtime.

### File Reference Notes

Important details about `file://` references:
- Content is read when configuration is loaded
- Whitespace (including newlines) is automatically stripped
- The file must exist and be readable when config loads
- Relative paths are resolved from the current working directory, not the config file location
- Use appropriate file permissions to protect sensitive files

## Transport Configuration

Configure how MXCP serves requests:

```yaml
transport:
  provider: streamable-http  # or: sse, stdio
  http:
    port: 8000
    host: localhost
    stateless: false    # true for serverless
    trust_proxy: false  # true behind reverse proxy
```

| Provider | Use Case |
|----------|----------|
| `streamable-http` | Default HTTP with streaming |
| `sse` | Server-sent events |
| `stdio` | Claude Desktop integration |

**Stateless Mode:**
When `stateless: true`, no session state is maintained between requests. This is required for serverless deployments (AWS Lambda, Cloud Functions). Can also be enabled with `mxcp serve --stateless`.

## Model Configuration

Configure LLM models for evaluations (used by `mxcp evals`):

```yaml
models:
  default: claude-sonnet

  models:
    claude-sonnet:
      type: claude
      api_key: "${ANTHROPIC_API_KEY}"
      timeout: 30
      max_retries: 3

    gpt-4o:
      type: openai
      api_key: "${OPENAI_API_KEY}"
      base_url: https://api.openai.com/v1
```

**Model Options:**

| Option | Description |
|--------|-------------|
| `default` | Model to use when not specified in eval suite or CLI |
| `type` | Either `claude` or `openai` |
| `api_key` | API key (supports environment variable references) |
| `base_url` | Custom API endpoint (optional, for OpenAI-compatible services) |
| `timeout` | Request timeout in seconds |
| `max_retries` | Number of retries on failure |

See [Evals](/quality/evals) for using models in evaluation tests.

## Environment Variables

Override configuration via environment:

| Variable | Description | Default |
|----------|-------------|---------|
| `MXCP_PROFILE` | Active profile | `default` |
| `MXCP_CONFIG` | User config path | `~/.mxcp/config.yml` |
| `MXCP_DUCKDB_PATH` | Override database path | from config |
| `MXCP_READONLY` | Force read-only mode | `false` |
| `MXCP_DEBUG` | Enable debug logging | `false` |
| `MXCP_ADMIN_ENABLED` | Enable admin socket | `false` |
| `MXCP_ADMIN_SOCKET` | Admin socket path | `/run/mxcp/mxcp.sock` |
| `MXCP_AUDIT_ENABLED` | Override audit setting | from config |
| `MXCP_DISABLE_ANALYTICS` | Disable analytics | `false` |

**DuckDB Path Override:**
`MXCP_DUCKDB_PATH` overrides the path specified in `profiles.<profile>.duckdb.path`. Useful for:
- Centralized database location across projects
- Running tests with temporary databases
- Deploying to environments where configured path isn't writable

## Configuration Reload

For long-running servers, reload configuration without restart:

```bash
# Send SIGHUP signal
kill -HUP $(pgrep -f "mxcp serve")

# Or use admin socket
curl --unix-socket /run/mxcp/mxcp.sock -X POST http://localhost/reload
```

**Reload behavior:**
- SIGHUP handler waits synchronously (up to 60 seconds)
- Service remains available - new requests wait while reload completes
- Automatic rollback on failure - if new values cause errors, server continues with old values

**What gets reloaded:**
- Vault secrets (`vault://`)
- File contents (`file://`)
- Environment variables (`${VAR}`)
- DuckDB connections (always recreated to pick up database file changes)
- Python runtimes with updated configs

**What does NOT reload:**
- Configuration file structure
- OAuth provider settings
- Server host/port
- Endpoint definitions

See [Admin Socket](/operations/admin-socket) for details.

## Validation

Validate your configuration before running:

```bash
mxcp validate
```

Checks:
- YAML syntax
- Required fields
- Secret references
- File paths
- Extension availability

## Best Practices

### 1. Never Commit Secrets

Keep `~/.mxcp/config.yml` outside your repository. Use environment variables or secret managers for CI/CD.

### 2. Use Profiles for Environments

```yaml
profiles:
  development:
    duckdb: { path: dev.duckdb, readonly: false }
  production:
    duckdb: { path: /data/prod.duckdb, readonly: true }
```

### 3. Use Environment Variables in CI/CD

```yaml
password: "${DB_PASSWORD}"  # Set in CI/CD environment
```

### 4. Quality Assurance Workflow

```bash
# During development
mxcp validate              # Check structure
mxcp test                  # Run tests
mxcp lint                  # Improve metadata

# Before deployment
mxcp drift-snapshot        # Create baseline
mxcp evals                 # Test LLM behavior

# In production
mxcp drift-check          # Monitor changes
```

### 5. Use Vault/1Password in Production

Avoid plain text secrets. Use secret managers for production deployments.

### 6. Document Endpoints

Add clear descriptions to endpoints, parameters, and return types. Run `mxcp lint` to identify missing documentation that affects LLM understanding.

## Troubleshooting

### "Config file not found"

```bash
# Check default location
ls ~/.mxcp/config.yml

# Override location
export MXCP_CONFIG=/path/to/config.yml
```

### "Secret not resolved"

- Verify secret name matches between site and user config
- Check Vault/1Password is enabled and token is set
- Verify the secret path exists

### "Profile not found"

- Check profile name spelling in both config files
- Verify profile exists in `mxcp-site.yml`

### "Project not found in user config"

- Ensure `project` name in `mxcp-site.yml` matches key in user config's `projects`

## Next Steps

- [Deployment](/operations/deployment) - Production deployment patterns
- [Authentication](/security/authentication) - OAuth configuration
- [Admin Socket](/operations/admin-socket) - Health checks and hot reload
