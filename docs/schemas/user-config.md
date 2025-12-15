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
            client_id: Ov23li...
            client_secret: "${GITHUB_CLIENT_SECRET}"
            callback_path: /callback
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
  address: https://vault.example.com
  token_path: ~/.vault-token
  namespace: admin

onepassword:
  service_account_token: "${OP_SERVICE_ACCOUNT_TOKEN}"

transport:
  http:
    host: 0.0.0.0
    port: 8000
    stateless: false

logging:
  level: info
  format: json
```

## Root Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `mxcp` | integer | Yes | - | Schema version. Must be `1`. |
| `projects` | object | No | - | Project-specific configurations. |
| `vault` | object | No | - | HashiCorp Vault global settings. |
| `onepassword` | object | No | - | 1Password global settings. |
| `transport` | object | No | - | Transport layer settings. |
| `logging` | object | No | - | Logging configuration. |

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
| `auth` | object | Authentication configuration. |

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

### Using Secrets in Python

```python
from mxcp.runtime import secrets

# Get database credentials
db = secrets.get("db_credentials")
connection_string = f"postgresql://{db['username']}:{db['password']}@{db['host']}:{db['port']}/{db['database']}"

# Get API key
api_key = secrets.get("api_key")["api_key"]
```

## Authentication Configuration

Configure OAuth authentication for the MCP server.

```yaml
auth:
  provider: github              # Required: Provider name
  github:                       # Provider-specific config
    client_id: Ov23li...
    client_secret: "${GITHUB_SECRET}"
    callback_path: /callback
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

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `provider` | string | Yes | OAuth provider: `github`, `google`, `atlassian`, `salesforce`, `keycloak`. |
| `<provider>` | object | Yes | Provider-specific configuration (see below). |
| `persistence` | object | No | Token persistence settings. |
| `authorization` | object | No | Authorization requirements. |
| `clients` | array | No | Pre-configured OAuth clients. |

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
| `auth_url` | string | No | Authorization URL. |
| `token_url` | string | No | Token URL. |
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

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `type` | string | Yes | Storage type: `sqlite`. |
| `path` | string | Yes | Database file path. |

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

Global HashiCorp Vault settings.

```yaml
vault:
  address: https://vault.example.com
  token_path: ~/.vault-token
  namespace: admin
  auth_method: token
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `address` | string | Yes | Vault server URL. |
| `token_path` | string | No | Path to token file. |
| `namespace` | string | No | Vault namespace. |
| `auth_method` | string | No | Auth method: `token`, `approle`, `kubernetes`. |

### AppRole Authentication

```yaml
vault:
  address: https://vault.example.com
  auth_method: approle
  role_id: "${VAULT_ROLE_ID}"
  secret_id: "${VAULT_SECRET_ID}"
```

### Kubernetes Authentication

```yaml
vault:
  address: https://vault.example.com
  auth_method: kubernetes
  role: mxcp-role
```

## 1Password Configuration

Global 1Password settings.

```yaml
onepassword:
  service_account_token: "${OP_SERVICE_ACCOUNT_TOKEN}"
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `service_account_token` | string | Yes | 1Password service account token. |

Use 1Password references in secrets:

```yaml
secrets:
  - name: db_credentials
    type: database
    parameters:
      password: "op://Private/Database/password"
```

## Transport Configuration

Configure HTTP transport settings.

```yaml
transport:
  http:
    host: 0.0.0.0
    port: 8000
    stateless: false
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `host` | string | `"127.0.0.1"` | Bind address. |
| `port` | integer | `8000` | Listen port. |
| `stateless` | boolean | `false` | Stateless mode (no sessions). |

## Logging Configuration

Configure logging behavior.

```yaml
logging:
  level: info
  format: json
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `level` | string | `"info"` | Log level: `debug`, `info`, `warning`, `error`. |
| `format` | string | `"text"` | Log format: `text`, `json`. |

## Environment Variables

Use environment variables anywhere in the configuration:

```yaml
secrets:
  - name: api_key
    type: api
    parameters:
      api_key: "${API_KEY}"              # Required variable
      base_url: "${API_URL:-https://api.example.com}"  # With default
```

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
