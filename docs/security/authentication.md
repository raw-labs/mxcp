---
title: "Authentication"
description: "OAuth 2.0 setup for MXCP: GitHub, Google, Atlassian, Salesforce, Keycloak. Client configuration, token handling, user context for policies."
sidebar:
  order: 2
---

> **Related Topics:** [Policies](/security/policies) (use user context for access control) | [Configuration](/operations/configuration) (secrets management) | [Common Tasks](/reference/common-tasks#how-do-i-add-authentication) (quick setup)

MXCP supports OAuth 2.0 authentication to control who can access your MCP server. This guide covers configuring various OAuth providers.

## How It Works

When authentication is enabled:

1. **Client connects** to your MCP server
2. **Server redirects** to OAuth provider (GitHub, Google, etc.)
3. **User authenticates** with the provider
4. **Provider redirects back** with authorization code
5. **Server exchanges** code for access token
6. **User context** becomes available in policies and SQL

All tools, resources, and prompts require valid authentication tokens when auth is enabled.

### Protected Features

When authentication is enabled, these features require valid tokens:
- **Custom Endpoints**: All tools, resources, and prompts defined in your YAML files
- **SQL Tools**: Built-in DuckDB querying and schema exploration tools

### User Information Logging

MXCP automatically logs user information for each authenticated request:
- Username and user ID
- OAuth provider (GitHub, Google, etc.)
- User's display name and email (when available)

## Supported Providers

| Provider | Use Case |
|----------|----------|
| GitHub | Developer teams, open source projects |
| Atlassian | Enterprise teams using Jira/Confluence |
| Salesforce | CRM integrations, enterprise apps |
| Google | Google Workspace organizations |
| Keycloak | Self-hosted identity management |

## Configuration Overview

Authentication is configured in your user configuration file (`~/.mxcp/config.yml`):

```yaml
mxcp: 1
projects:
  my-project:
    profiles:
      default:
        auth:
          provider: github
          github:
            client_id: "${GITHUB_CLIENT_ID}"
            client_secret: "${GITHUB_CLIENT_SECRET}"
            callback_path: /callback
            auth_url: https://github.com/login/oauth/authorize
            token_url: https://github.com/login/oauth/access_token
```

### Disable Authentication

By default, authentication is disabled (`provider: none`):

```yaml
mxcp: 1
projects:
  my-project:
    profiles:
      default:
        auth:
          provider: none  # No authentication required
```

Use this for:
- Local development
- Internal tools with network-level security
- Read-only public APIs

## GitHub Authentication

### 1. Create OAuth App

1. Go to **GitHub Settings** → **Developer settings** → **OAuth Apps**
2. Click **New OAuth App**
3. Configure:
   - **Application name**: Your MCP Server
   - **Homepage URL**: `http://localhost:8000`
   - **Authorization callback URL**: `http://localhost:8000/callback`
4. Copy the **Client ID** and **Client Secret**

### 2. Configure MXCP

```yaml
mxcp: 1
projects:
  my-project:
    profiles:
      default:
        auth:
          provider: github
          github:
            client_id: "${GITHUB_CLIENT_ID}"
            client_secret: "${GITHUB_CLIENT_SECRET}"
            callback_path: /callback
            auth_url: https://github.com/login/oauth/authorize
            token_url: https://github.com/login/oauth/access_token
            scope: "read:user user:email"
```

**Note:** The examples below for other providers show just the `auth` block for brevity. Place them at the same location: `projects.{project}.profiles.{profile}.auth`.

### 3. Available Scopes

| Scope | Access |
|-------|--------|
| `read:user` | User profile information |
| `user:email` | User email addresses |
| `read:org` | Organization membership |
| `repo` | Repository access (if needed) |

## Atlassian Authentication

For Jira and Confluence integration.

### 1. Create OAuth 2.0 App

1. Go to [Atlassian Developer Console](https://developer.atlassian.com/console/myapps/)
2. Create a new **OAuth 2.0 integration**
3. Configure:
   - **Name**: Your MCP Server
   - **Callback URL**: `http://localhost:8000/callback`
4. Enable required **API scopes**
5. Copy credentials

### 2. Configure MXCP

```yaml
# In ~/.mxcp/config.yml
auth:
  provider: atlassian
  atlassian:
    client_id: "${ATLASSIAN_CLIENT_ID}"
    client_secret: "${ATLASSIAN_CLIENT_SECRET}"
    callback_path: /callback
    auth_url: https://auth.atlassian.com/authorize
    token_url: https://auth.atlassian.com/oauth/token
    scope: "read:me read:jira-work write:jira-work"
```

### 3. Available Scopes

| Scope | Access |
|-------|--------|
| `read:me` | User profile |
| `read:jira-work` | Read Jira issues |
| `write:jira-work` | Create/update issues |
| `read:confluence-content.all` | Read Confluence pages |
| `offline_access` | Enable refresh tokens |

### 4. Accessing Multiple Sites

Atlassian OAuth grants access to all sites where your app is installed. To work with specific sites:

1. **Get accessible resources** (returns cloud IDs):
   ```bash
   curl -H "Authorization: Bearer ACCESS_TOKEN" \
        https://api.atlassian.com/oauth/token/accessible-resources
   ```

2. **Use the cloud ID** in API requests:
   ```bash
   # JIRA API
   curl -H "Authorization: Bearer ACCESS_TOKEN" \
        https://api.atlassian.com/ex/jira/{cloudid}/rest/api/2/project

   # Confluence API
   curl -H "Authorization: Bearer ACCESS_TOKEN" \
        https://api.atlassian.com/ex/confluence/{cloudid}/rest/api/space
   ```

## Salesforce Authentication

For CRM and enterprise integrations.

### 1. Create Connected App

1. Go to **Salesforce Setup** → **App Manager**
2. Click **New Connected App**
3. Enable **OAuth Settings**:
   - **Callback URL**: `http://localhost:8000/callback`
   - Select required **OAuth Scopes**
4. Copy **Consumer Key** and **Consumer Secret**

### 2. Configure MXCP

```yaml
# In ~/.mxcp/config.yml
auth:
  provider: salesforce
  salesforce:
    client_id: "${SALESFORCE_CLIENT_ID}"
    client_secret: "${SALESFORCE_CLIENT_SECRET}"
    callback_path: /callback
    auth_url: https://login.salesforce.com/services/oauth2/authorize
    token_url: https://login.salesforce.com/services/oauth2/token
    scope: "openid profile email api"
```

### 3. Available Scopes

| Scope | Access |
|-------|--------|
| `openid` | OpenID Connect authentication |
| `profile` | User profile information |
| `email` | User email address |
| `api` | Access to Salesforce APIs |
| `refresh_token` | Enable token refresh |

### 4. Sandbox Environment

For sandbox/test environments:

```yaml
auth_url: https://test.salesforce.com/services/oauth2/authorize
token_url: https://test.salesforce.com/services/oauth2/token
```

## Google Authentication

For Google Workspace organizations.

### 1. Create OAuth Client

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create or select a project
3. Go to **APIs & Services** → **Credentials**
4. Click **Create Credentials** → **OAuth client ID**
5. Configure:
   - **Application type**: Web application
   - **Authorized redirect URIs**: `http://localhost:8000/callback`
6. Copy credentials

### 2. Configure MXCP

```yaml
# In ~/.mxcp/config.yml
auth:
  provider: google
  google:
    client_id: "${GOOGLE_CLIENT_ID}"
    client_secret: "${GOOGLE_CLIENT_SECRET}"
    callback_path: /callback
    auth_url: https://accounts.google.com/o/oauth2/v2/auth
    token_url: https://oauth2.googleapis.com/token
    scope: "openid email profile"
```

### 3. Available Scopes

| Scope | Access |
|-------|--------|
| `openid` | OpenID Connect authentication |
| `email` | User email address |
| `profile` | User profile information |
| `https://www.googleapis.com/auth/calendar.readonly` | Read calendar events |
| `https://www.googleapis.com/auth/drive.readonly` | Read Drive files |

### 4. Domain Restriction

To restrict to a specific Google Workspace domain, validate the user's email domain in your policies:

```yaml
policies:
  input:
    - condition: "!user.email.endsWith('@yourcompany.com')"
      action: deny
      reason: "Access restricted to company domain"
```

### 5. Working with Google APIs

Once authenticated, use the user's token to access Google services from SQL:

```sql
-- List Google Calendar events
SELECT *
FROM read_json_auto(
    'https://www.googleapis.com/calendar/v3/calendars/primary/events',
    headers = MAP {
        'Authorization': 'Bearer ' || get_user_external_token()
    }
);

-- Search Google Drive files
SELECT *
FROM read_json_auto(
    'https://www.googleapis.com/drive/v3/files?q=name+contains+''report''',
    headers = MAP {
        'Authorization': 'Bearer ' || get_user_external_token()
    }
);
```

## Keycloak Authentication

For self-hosted identity management.

### 1. Create Client

1. Go to your Keycloak Admin Console
2. Select your realm
3. Go to **Clients** → **Create**
4. Configure:
   - **Client ID**: mxcp-server
   - **Client Protocol**: openid-connect
   - **Access Type**: confidential
   - **Valid Redirect URIs**: `http://localhost:8000/callback`
5. Go to **Credentials** tab for Client Secret

### 2. Configure MXCP

```yaml
# In ~/.mxcp/config.yml
auth:
  provider: keycloak
  keycloak:
    client_id: "${KEYCLOAK_CLIENT_ID}"
    client_secret: "${KEYCLOAK_CLIENT_SECRET}"
    realm: myrealm
    server_url: https://keycloak.example.com
    callback_path: /callback
    scope: "openid profile email"
```

**Note:** MXCP auto-constructs the OAuth URLs from `server_url` and `realm`:
- Authorization: `{server_url}/realms/{realm}/protocol/openid-connect/auth`
- Token: `{server_url}/realms/{realm}/protocol/openid-connect/token`

### 3. Available Scopes

| Scope | Access |
|-------|--------|
| `openid` | OpenID Connect authentication |
| `profile` | User profile information |
| `email` | User email address |
| `roles` | User roles from Keycloak |
| `offline_access` | Enable refresh tokens |

## Token Persistence

MXCP stores OAuth tokens for session continuity:

```yaml
auth:
  provider: github
  persistence:
    type: sqlite
    path: ~/.mxcp/oauth.db
```

Tokens are:
- Stored securely in SQLite
- Refreshed automatically when expired
- Cleared on logout

## User Context

After authentication, user information is available in policies:

```yaml
policies:
  input:
    - condition: "!user.email.endsWith('@yourcompany.com')"
      action: deny
      reason: "Only company emails allowed"

    - condition: "user.role != 'admin'"
      action: deny
      reason: "Admin role required"
```

### Available User Fields

| Field | Source | Description |
|-------|--------|-------------|
| `user.id` | OAuth provider | Unique user identifier |
| `user.email` | OAuth provider | User's email address |
| `user.name` | OAuth provider | Display name |
| `user.role` | `--user-context` or custom mapping | User role for access control |
| `user.permissions` | `--user-context` or custom mapping | List of permissions |
| `user.groups` | OAuth provider (if supported) | Group memberships |

**Note:** Fields like `role` and `permissions` are not provided by most OAuth providers. Use `--user-context` for testing or implement custom role mapping in your application.

## Stateless Mode

For serverless deployments without session state:

```yaml
transport:
  http:
    stateless: true  # No session storage
```

In stateless mode:
- Each request must include auth token
- No session cookies
- Tokens validated on every request

## Reverse Proxy Configuration

When running behind a reverse proxy, configure MXCP to trust forwarded headers.

### Transport Configuration

Configure trust_proxy in your transport settings:

```yaml
transport:
  http:
    host: 0.0.0.0
    port: 8000
    trust_proxy: true  # Trust X-Forwarded-Proto headers
```

When `trust_proxy: true`:
- OAuth callback URLs use the scheme from `X-Forwarded-Proto`
- Redirect URIs are constructed correctly for HTTPS
- Required when running behind load balancers or reverse proxies

### nginx

Basic configuration:

```nginx
location / {
    proxy_pass http://localhost:8000;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}
```

Complete SSL configuration:

```nginx
server {
    listen 80;
    server_name api.example.com;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name api.example.com;

    ssl_certificate /path/to/certificate.crt;
    ssl_certificate_key /path/to/private.key;

    # Security headers
    add_header Strict-Transport-Security "max-age=31536000" always;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

### Traefik

```yaml
http:
  routers:
    mxcp:
      rule: "Host(`mxcp.example.com`)"
      service: mxcp
      tls:
        certResolver: letsencrypt
  services:
    mxcp:
      loadBalancer:
        servers:
          - url: "http://localhost:8000"
```

## Testing Authentication

### Without Authentication

Test endpoints without auth:

```bash
mxcp run tool my_tool --param key=value
```

### With User Context

Test with simulated user:

```bash
mxcp run tool my_tool \
  --param key=value \
  --user-context '{"role": "admin", "email": "admin@example.com"}'
```

### HTTP Testing

Start authenticated server:

```bash
mxcp serve --transport streamable-http --port 8000
```

Visit `http://localhost:8000` to trigger OAuth flow.

## Troubleshooting

### "Invalid redirect_uri"
- Ensure callback URL matches exactly in provider settings
- Check for trailing slashes

### "Token expired"
- Enable token persistence for auto-refresh
- Check token expiration settings

### "User not authorized"
- Verify scopes include required permissions
- Check policy conditions

### "Connection refused to provider"
- Verify auth_url and token_url are correct
- Check network connectivity

## Security Best Practices

### 1. Use HTTPS in Production
```yaml
transport:
  http:
    host: 0.0.0.0
    port: 443
```

### 2. Secure Client Secrets
```yaml
client_secret: "vault://secret/oauth#github_secret"
```

### 3. Limit Scopes
Request only necessary scopes.

### 4. Rotate Secrets
Regularly rotate OAuth client secrets.

### 5. Monitor Auth Logs
```bash
mxcp log --since 24h | grep -i auth
```

## Advanced Features

### Dynamic Client Registration (RFC 7591)

MXCP implements RFC 7591 Dynamic Client Registration. Clients can register themselves at runtime:

```bash
curl -X POST http://localhost:8000/register \
  -H "Content-Type: application/json" \
  -d '{
    "client_name": "My Application",
    "redirect_uris": ["https://myapp.example.com/oauth/callback"],
    "grant_types": ["authorization_code"],
    "scope": "mxcp:access"
  }'
```

Response:
```json
{
  "client_id": "generated-client-id",
  "client_secret": "generated-client-secret",
  "client_id_issued_at": 1640995200,
  "client_secret_expires_at": 0,
  "redirect_uris": ["https://myapp.example.com/oauth/callback"],
  "grant_types": ["authorization_code"],
  "scope": "mxcp:access"
}
```

### Authorization Configuration

Configure scope-based authorization to control endpoint access:

```yaml
auth:
  provider: github
  authorization:
    required_scopes:
      - "mxcp:access"
      - "mxcp:admin"
```

**Configuration Options:**
- `required_scopes: []` - Authentication only (no scope requirements)
- `required_scopes: ["mxcp:access"]` - Require basic access
- Multiple scopes - User must have ALL listed scopes

### User Token Access in SQL

When authentication is enabled, SQL queries can access user information:

```sql
-- Get the user's OAuth provider token
SELECT get_user_external_token() as token;

-- Get user information
SELECT get_username() as username;
SELECT get_user_provider() as provider;
SELECT get_user_email() as email;

-- Access request headers
SELECT get_request_header('X-Custom-Header') as custom_header;
SELECT get_request_headers_json() as all_headers;
```

**Use Cases:**

Making authenticated API calls from SQL:
```sql
SELECT *
FROM read_json_auto(
    'https://api.github.com/user/repos',
    headers = MAP {
        'Authorization': 'Bearer ' || get_user_external_token(),
        'User-Agent': 'MXCP'
    }
);
```

User-specific data filtering:
```sql
SELECT *
FROM user_documents
WHERE created_by = get_username();
```

**Function Behavior:**
- When authentication is disabled: Functions return NULL
- When user is not authenticated: Functions return NULL
- When user is authenticated: Functions return actual user data

**Note:** These functions only work when running through `mxcp serve`. Direct CLI execution via `mxcp run` does not have access to these functions.

### Pre-Configured OAuth Clients

Define static clients in configuration:

```yaml
auth:
  provider: github
  clients:
    - client_id: "my-app-client"
      client_secret: "${CLIENT_SECRET}"
      name: "My Application"
      redirect_uris:
        - "https://myapp.example.com/callback"
      scopes:
        - "mxcp:access"
```

**Client Configuration Options:**
- `client_id` (required): Unique identifier
- `name` (required): Human-readable name
- `client_secret` (optional): Secret for confidential clients
- `redirect_uris` (optional): Allowed redirect URIs
- `grant_types` (optional): Allowed grant types (default: `["authorization_code"]`)
- `scopes` (optional): Allowed scopes (default: `["mxcp:access"]`)

## Production Checklist

- [ ] Enable OAuth persistence for session continuity
- [ ] Set file permissions (600) on OAuth database
- [ ] Use environment variables for secrets
- [ ] Configure HTTPS for all redirect URIs
- [ ] Limit OAuth scopes to minimum required
- [ ] Remove development clients from production config
- [ ] Enable audit logging for authentication events
- [ ] Set up monitoring for auth-related errors

## Next Steps

- [Policies](/security/policies) - Configure access control
- [Auditing](/security/auditing) - Track authentication events
- [Configuration](/operations/configuration) - More configuration options
