---
title: "User Configuration Schema"
description: "Complete YAML schema reference for ~/.mxcp/config.yml. Secrets, authentication providers, Vault integration, and user-level settings."
sidebar:
  order: 6
---

> **Related Topics:** [Configuration](/operations/configuration) (configuration guide) | [Authentication](/security/authentication) (OAuth setup) | [Site Configuration](/schemas/site-config) (project config)

This reference documents the complete YAML schema for the user configuration file at `~/.mxcp/config.yml`.

## Complete Example

```yaml
mxcp: 1

projects:
  my-analytics:
    profiles:
      default:
        secrets:
          - name: db_credentials
            type: database
            parameters:
              host: localhost
              port: 5432
              database: analytics
              username: app_user
              password: "vault://secret/db#password"

          - name: api_key
            type: api
            parameters:
              api_key: "${MY_API_KEY}"

        auth:
          provider: github
          github:
            client_id: "${GITHUB_CLIENT_ID}"
            client_secret: "${GITHUB_CLIENT_SECRET}"
            callback_path: /auth/github/callback
            auth_url: https://github.com/login/oauth/authorize
            token_url: https://github.com/login/oauth/access_token
            scope: "read:user user:email"
          persistence:
            type: sqlite
            path: ~/.mxcp/oauth.db

      production:
        secrets:
          - name: db_credentials
            type: database
            parameters:
              host: prod-db.example.com
              port: 5432
              database: analytics_prod
              username: "vault://secret/prod#username"
              password: "vault://secret/prod#password"

vault:
  enabled: true
  address: https://vault.example.com
  token_env: VAULT_TOKEN

onepassword:
  enabled: true
  token_env: OP_SERVICE_ACCOUNT_TOKEN

transport:
  provider: streamable-http
  http:
    host: 0.0.0.0
    port: 8000
    stateless: false

logging:
  enabled: true
  level: INFO
```

## Root Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `mxcp` | integer | Yes | - | Schema version. Must be `1`. |
| `projects` | object | No | - | Project-specific configurations. |
| `vault` | object | No | - | HashiCorp Vault global settings. |
| `onepassword` | object | No | - | 1Password global settings. |
| `models` | object | No | - | LLM model configurations. |
| `transport` | object | No | - | Transport layer settings. |
| `logging` | object | No | - | Logging configuration. |

> **Note:** The `mxcp` field accepts both integer (`1`) and string (`"1"`) values - strings are automatically coerced to integers.

## Projects Configuration

Define settings for specific projects, matched by the `project` field in `mxcp-site.yml`.

```yaml
projects:
  project-name:           # Must match project name in mxcp-site.yml
    profiles:
      profile-name:       # Must match profile name
        secrets: [...]
        auth: {...}
```

### Profile Configuration

| Field | Type | Description |
|-------|------|-------------|
| `secrets` | array | Secret definitions for this profile. |
| `plugin` | object | Plugin configuration for this profile. |
| `auth` | object | Authentication configuration. |
| `telemetry` | object | OpenTelemetry configuration for this profile. |

## Secrets Configuration

Define secret values that can be used in endpoints.

```yaml
secrets:
  - name: my_secret        # Secret name (must match mxcp-site.yml)
    type: database         # Secret type
    parameters:            # Type-specific parameters
      host: localhost
      password: "vault://secret/db#password"
```

### Secret Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | Yes | Secret identifier (matches `secrets` in site config). |
| `type` | string | Yes | Secret type: `database`, `api`, `custom`, `env`. |
| `parameters` | object | No | Type-specific parameters. |

### Secret Types

#### Database Secret

```yaml
- name: db_credentials
  type: database
  parameters:
    host: localhost
    port: 5432
    database: mydb
    username: app_user
    password: "${DB_PASSWORD}"
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `host` | string | Database hostname. |
| `port` | integer | Database port. |
| `database` | string | Database name. |
| `username` | string | Database username. |
| `password` | string | Database password. |

#### API Secret

```yaml
- name: api_credentials
  type: api
  parameters:
    api_key: "${API_KEY}"
    api_secret: "vault://secret/api#secret"
    base_url: https://api.example.com
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `api_key` | string | API key. |
| `api_secret` | string | API secret (optional). |
| `base_url` | string | API base URL (optional). |

#### Environment Secret

```yaml
- name: simple_key
  type: env
  key: MY_ENV_VAR        # Environment variable name
```

#### Custom Secret

```yaml
- name: custom_config
  type: custom
  parameters:
    key1: value1
    key2: "vault://secret/custom#key2"
    nested:
      key3: value3
```

### Secret Value Sources

Secret values can come from multiple sources:

| Source | Format | Example |
|--------|--------|---------|
| Literal | Plain string | `"my-secret-value"` |
| Environment | `${VAR_NAME}` | `"${API_KEY}"` |
| Vault | `vault://path#key` | `"vault://secret/db#password"` |
| 1Password | `op://vault/item/field` | `"op://Private/DB/password"` |
| File | `file://path` | `"file:///etc/ssl/cert.pem"` |

### File References

Read secret values from local files using `file://` URLs:

```yaml
secrets:
  - name: ssl_certificates
    type: custom
    parameters:
      cert: "file:///etc/ssl/certs/server.crt"
      key: "file:///etc/ssl/private/server.key"
  - name: api_config
    type: api
    parameters:
      api_key: "file://secrets/api_key.txt"  # Relative path
```

**File URL Format:**
- Absolute paths: `file:///absolute/path/to/file`
- Relative paths: `file://relative/path/to/file` (relative to current working directory)

**Important Notes:**
- File content is read when the configuration is loaded
- Whitespace (including newlines) is automatically stripped
- The file must exist and be readable when the configuration is loaded
- Relative paths are resolved from the current working directory, not the config file location
- Use appropriate file permissions to protect sensitive files

### Using Secrets in Python

```python
from mxcp.runtime import config

# Get database credentials (returns dict with parameters, or None if not found)
db_creds = config.get_secret("db_credentials")
if db_creds:
    connection_string = f"postgresql://{db_creds['username']}:{db_creds['password']}@{db_creds['host']}:{db_creds['port']}/{db_creds['database']}"

# Get API key
api_creds = config.get_secret("api_key")
if api_creds:
    api_key = api_creds.get("api_key")
```

## Authentication Configuration

Configure OAuth authentication for the MCP server.

```yaml
auth:
  provider: github              # Required: Provider name
  github:                       # Provider-specific config
    client_id: "${GITHUB_CLIENT_ID}"
    client_secret: "${GITHUB_CLIENT_SECRET}"
    callback_path: /auth/github/callback
    auth_url: https://github.com/login/oauth/authorize
    token_url: https://github.com/login/oauth/access_token
    scope: "read:user user:email"
  persistence:                  # Optional: Token storage
    type: sqlite
    path: ~/.mxcp/oauth.db
  authorization:                # Optional: Scope requirements
    required_scopes:
      - "mxcp:access"
  clients:                      # Optional: Pre-configured clients
    - client_id: my-app
      name: "My Application"
      redirect_uris:
        - "https://myapp.com/callback"
```

### Auth Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `provider` | string | `"none"` | OAuth provider: `none`, `github`, `google`, `atlassian`, `salesforce`, `keycloak`. |
| `<provider>` | object | - | Provider-specific configuration (required when provider is not `none`). |
| `persistence` | object | - | Token persistence settings. Auto-created when provider is not `none`. |
| `authorization` | object | - | Authorization requirements. |
| `clients` | array | - | Pre-configured OAuth clients. |

> **Note:** When `provider` is set to anything other than `none`, persistence is automatically configured with SQLite at `~/.mxcp/oauth.db` if not explicitly specified.

### GitHub Provider

```yaml
auth:
  provider: github
  github:
    client_id: Ov23li...
    client_secret: "${GITHUB_CLIENT_SECRET}"
    callback_path: /callback
    auth_url: https://github.com/login/oauth/authorize
    token_url: https://github.com/login/oauth/access_token
    scope: "read:user user:email read:org"
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `client_id` | string | Yes | GitHub OAuth App client ID. |
| `client_secret` | string | Yes | GitHub OAuth App client secret. |
| `callback_path` | string | Yes | OAuth callback path (e.g., `/callback`). |
| `auth_url` | string | Yes | Authorization URL (e.g., `https://github.com/login/oauth/authorize`). |
| `token_url` | string | Yes | Token URL (e.g., `https://github.com/login/oauth/access_token`). |
| `scope` | string | No | OAuth scopes (space-separated). |

### Google Provider

```yaml
auth:
  provider: google
  google:
    client_id: xxx.apps.googleusercontent.com
    client_secret: "${GOOGLE_CLIENT_SECRET}"
    callback_path: /callback
    auth_url: https://accounts.google.com/o/oauth2/v2/auth
    token_url: https://oauth2.googleapis.com/token
    scope: "openid email profile"
```

### Atlassian Provider

```yaml
auth:
  provider: atlassian
  atlassian:
    client_id: your_client_id
    client_secret: "${ATLASSIAN_SECRET}"
    callback_path: /callback
    auth_url: https://auth.atlassian.com/authorize
    token_url: https://auth.atlassian.com/oauth/token
    scope: "read:me read:jira-work"
```

### Salesforce Provider

```yaml
auth:
  provider: salesforce
  salesforce:
    client_id: your_consumer_key
    client_secret: "${SALESFORCE_SECRET}"
    callback_path: /callback
    auth_url: https://login.salesforce.com/services/oauth2/authorize
    token_url: https://login.salesforce.com/services/oauth2/token
    scope: "openid profile email api"
```

For sandbox environments:

```yaml
auth_url: https://test.salesforce.com/services/oauth2/authorize
token_url: https://test.salesforce.com/services/oauth2/token
```

### Keycloak Provider

```yaml
auth:
  provider: keycloak
  keycloak:
    client_id: mxcp-server
    client_secret: "${KEYCLOAK_SECRET}"
    callback_path: /callback
    realm: myrealm
    server_url: https://keycloak.example.com
    scope: "openid profile email"
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `client_id` | string | Yes | Keycloak client ID. |
| `client_secret` | string | Yes | Keycloak client secret. |
| `callback_path` | string | Yes | OAuth callback path. |
| `realm` | string | Yes | Keycloak realm name. |
| `server_url` | string | Yes | Keycloak server URL. |
| `scope` | string | No | OAuth scopes. |

### Persistence Configuration

Store OAuth tokens for session continuity:

```yaml
persistence:
  type: sqlite
  path: ~/.mxcp/oauth.db
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `type` | string | `"sqlite"` | Storage type: `sqlite`. |
| `path` | string | `~/.mxcp/oauth.db` | Database file path. |

### Authorization Configuration

Require specific scopes for access:

```yaml
authorization:
  required_scopes:
    - "mxcp:access"
    - "mxcp:admin"
```

### Pre-Configured Clients

Define static OAuth clients:

```yaml
clients:
  - client_id: my-app
    client_secret: "${MY_APP_SECRET}"
    name: "My Application"
    redirect_uris:
      - "https://myapp.com/callback"
      - "http://localhost:3000/callback"
    grant_types:
      - "authorization_code"
    scopes:
      - "mxcp:access"
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `client_id` | string | Yes | Unique client identifier. |
| `client_secret` | string | No | Client secret (for confidential clients). |
| `name` | string | Yes | Human-readable name. |
| `redirect_uris` | array | No | Allowed redirect URIs. |
| `grant_types` | array | No | Allowed grant types. |
| `scopes` | array | No | Allowed scopes. |

## Vault Configuration

Global HashiCorp Vault settings for resolving `vault://` references in secrets.

```yaml
vault:
  enabled: true
  address: https://vault.example.com
  token_env: VAULT_TOKEN
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `enabled` | boolean | `false` | Whether Vault integration is enabled. |
| `address` | string | - | Vault server URL. |
| `token_env` | string | - | Environment variable name containing the Vault token. |

### Requirements

```bash
pip install "mxcp[vault]"
# or
pip install hvac
```

### Vault URL Format

`vault://path/to/secret#key`

- `path/to/secret`: The path to the secret in Vault
- `key`: The specific key within that secret

**Supported Secret Engines:**
- KV Secrets Engine v2 (default)
- KV Secrets Engine v1 (fallback)

### Usage Example

Set the Vault token in your environment:

```bash
export VAULT_TOKEN="your-vault-token"
```

Then reference Vault secrets in your configuration:

```yaml
secrets:
  - name: db_credentials
    type: database
    parameters:
      password: "vault://secret/db#password"
```

## 1Password Configuration

Global 1Password settings for resolving `op://` references in secrets.

```yaml
onepassword:
  enabled: true
  token_env: OP_SERVICE_ACCOUNT_TOKEN
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `enabled` | boolean | `false` | Whether 1Password integration is enabled. |
| `token_env` | string | - | Environment variable name containing the 1Password service account token. |

### Requirements

```bash
pip install "mxcp[onepassword]"
# or
pip install onepassword-sdk
```

### 1Password URL Format

`op://vault/item/field[?attribute=otp]`

- `vault`: The name or ID of the vault in 1Password
- `item`: The name or ID of the item in 1Password
- `field`: The name or ID of the field within the item
- `?attribute=otp`: Optional parameter to retrieve TOTP/OTP value

**Examples:**
- Basic field: `op://Private/Login Item/username`
- Password field: `op://Private/Login Item/password`
- TOTP/OTP: `op://Private/Login Item/totp?attribute=otp`
- Using vault ID: `op://hfnjvi6aymbsnfc2gshk5b6o5q/Login Item/password`
- Using item ID: `op://Private/j5hbqmr7nz3uqsw3j5qam2fgji/password`

### Usage Example

Set the 1Password service account token in your environment:

```bash
export OP_SERVICE_ACCOUNT_TOKEN="your-service-account-token"
```

Then reference 1Password secrets in your configuration:

```yaml
secrets:
  - name: db_credentials
    type: database
    parameters:
      password: "op://Private/Database/password"
```

## Models Configuration

Configure LLM providers for AI-powered features.

```yaml
models:
  default: claude
  models:
    claude:
      type: claude
      api_key: "${ANTHROPIC_API_KEY}"
      timeout: 30
      max_retries: 3
    openai:
      type: openai
      api_key: "${OPENAI_API_KEY}"
      base_url: https://api.openai.com/v1
```

### Models Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `default` | string | No | Default model identifier. |
| `models` | object | No | Named model configurations. |

### Model Configuration

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `type` | string | Yes | Model type: `claude` or `openai`. |
| `api_key` | string | No | API key for the model provider. |
| `base_url` | string | No | Custom API base URL. |
| `timeout` | integer | No | Request timeout in seconds. |
| `max_retries` | integer | No | Maximum retry attempts. |

## Transport Configuration

Configure MCP transport settings.

```yaml
transport:
  provider: streamable-http
  http:
    host: 0.0.0.0
    port: 8000
    scheme: http
    stateless: false
    trust_proxy: false
```

### Transport Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `provider` | string | `"streamable-http"` | Transport provider: `streamable-http`, `sse`, `stdio`. |
| `http` | object | - | HTTP transport settings (see below). |

### HTTP Transport Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `host` | string | `"localhost"` | Bind address. |
| `port` | integer | `8000` | Listen port. |
| `scheme` | string | `"http"` | URL scheme: `http` or `https`. |
| `base_url` | string | - | Custom base URL (overrides host/port/scheme). |
| `stateless` | boolean | `false` | Stateless mode (no sessions). |
| `trust_proxy` | boolean | `false` | Trust proxy headers for client IP. |

## Logging Configuration

Configure file-based logging behavior.

```yaml
logging:
  enabled: true
  path: ~/.mxcp/logs/mxcp.log
  level: INFO
  max_bytes: 10485760
  backup_count: 5
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `enabled` | boolean | `true` | Whether file logging is enabled. |
| `path` | string | - | Log file path. If not set, logs to stderr only. |
| `level` | string | `"WARNING"` | Log level: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`. |
| `max_bytes` | integer | `10485760` | Maximum log file size in bytes (10 MB default). |
| `backup_count` | integer | `5` | Number of backup log files to keep. |

## Telemetry Configuration

Configure OpenTelemetry for tracing and metrics. This is configured per-profile.

```yaml
projects:
  my-project:
    profiles:
      default:
        telemetry:
          enabled: true
          endpoint: https://otel-collector.example.com:4318
          service_name: mxcp-server
          service_version: "1.0.0"
          environment: production
          headers:
            Authorization: "Bearer ${OTEL_TOKEN}"
          tracing:
            enabled: true
            console_export: false
          metrics:
            enabled: true
            export_interval: 60
```

### Telemetry Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `enabled` | boolean | `false` | Whether telemetry is enabled. |
| `endpoint` | string | - | OpenTelemetry collector endpoint. |
| `headers` | object | - | Headers to send with telemetry requests. |
| `service_name` | string | - | Service name for telemetry data. |
| `service_version` | string | - | Service version for telemetry data. |
| `environment` | string | - | Environment name (e.g., `production`, `staging`). |
| `resource_attributes` | object | - | Additional resource attributes. |
| `tracing` | object | - | Tracing configuration (see below). |
| `metrics` | object | - | Metrics configuration (see below). |

### Tracing Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `enabled` | boolean | `false` | Whether tracing is enabled. |
| `console_export` | boolean | `false` | Export traces to console (for debugging). |

### Metrics Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `enabled` | boolean | `false` | Whether metrics are enabled. |
| `export_interval` | integer | `60` | Metrics export interval in seconds. |

## Environment Variables

Use environment variables anywhere in the configuration with `${VAR_NAME}` syntax:

```yaml
secrets:
  - name: api_key
    type: api
    parameters:
      api_key: "${API_KEY}"
      base_url: "${API_URL}"
```

### MXCP Environment Variables

| Variable | Description |
|----------|-------------|
| `MXCP_CONFIG` | Path to user config file (default: `~/.mxcp/config.yml`) |
| `MXCP_PROFILE` | Override the active profile |
| `MXCP_DUCKDB_PATH` | Override DuckDB database path |
| `MXCP_AUDIT_ENABLED` | Override audit logging (`true`/`false`, `1`/`0`, `yes`/`no`) |
| `MXCP_DEBUG` | Enable debug logging |
| `MXCP_READONLY` | Enable read-only mode |
| `MXCP_DISABLE_ANALYTICS` | Disable analytics (set to `1`, `true`, or `yes`) |
| `MXCP_ADMIN_ENABLED` | Enable local admin control socket |
| `MXCP_ADMIN_SOCKET` | Path to admin socket (default: `/run/mxcp/mxcp.sock`) |

### Telemetry Environment Variables

| Variable | Description |
|----------|-------------|
| `MXCP_TELEMETRY_ENABLED` | Enable OpenTelemetry |
| `MXCP_TELEMETRY_TRACING_CONSOLE` | Export traces to console |
| `MXCP_TELEMETRY_METRICS_INTERVAL` | Metrics export interval in seconds |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | OpenTelemetry collector endpoint |
| `OTEL_SERVICE_NAME` | Service name for telemetry |
| `OTEL_RESOURCE_ATTRIBUTES` | Additional resource attributes |
| `OTEL_EXPORTER_OTLP_HEADERS` | Headers for OTLP exporter |

## Configuration Reload

For long-running MCP servers, you can reload external configuration values without restarting:

```bash
# Send SIGHUP signal to reload external values
kill -HUP <pid>
```

**What gets refreshed:**
- ✅ Vault secrets (`vault://`)
- ✅ File contents (`file://`)
- ✅ Environment variables (`${VAR}`)
- ✅ DuckDB connection (recreated to pick up database changes)
- ✅ Python runtimes with updated configs

**What does NOT change:**
- ❌ Configuration file structure
- ❌ OAuth provider settings
- ❌ Server host/port settings
- ❌ Registered endpoints

The reload process waits up to 60 seconds synchronously. If new values cause errors, the server continues with old values.

## File Location

The user configuration file is located at:

| Platform | Path |
|----------|------|
| Linux/macOS | `~/.mxcp/config.yml` |
| Windows | `%USERPROFILE%\.mxcp\config.yml` |

Create the directory if it doesn't exist:

```bash
mkdir -p ~/.mxcp
```

## Validation

Test your configuration:

```bash
# Validate all configuration
mxcp validate

# Test with specific profile
mxcp serve --profile production
```

## Security Best Practices

1. **Never commit secrets** - Use environment variables or secret managers
2. **Set file permissions** - `chmod 600 ~/.mxcp/config.yml`
3. **Use secret managers** - Prefer Vault or 1Password over environment variables
4. **Rotate secrets** - Regularly rotate OAuth client secrets and API keys
5. **Limit scopes** - Request only necessary OAuth scopes

## Next Steps

- [Site Configuration Schema](/schemas/site-config) - Project configuration
- [Authentication](/security/authentication) - OAuth setup guide
- [Configuration Guide](/operations/configuration) - Complete configuration documentation
