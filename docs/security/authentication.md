---
title: "Authentication"
description: "Configure OAuth authentication in MXCP. Support for GitHub, Atlassian, Salesforce, Google, Keycloak, and custom providers."
sidebar:
  order: 2
---

MXCP supports OAuth 2.0 authentication to control who can access your MCP server. This guide covers configuring various OAuth providers.

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
            client_id: your_client_id
            client_secret: your_client_secret
            auth_url: https://github.com/login/oauth/authorize
            token_url: https://github.com/login/oauth/access_token
```

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
            client_id: Ov23li...
            client_secret: your_client_secret
            auth_url: https://github.com/login/oauth/authorize
            token_url: https://github.com/login/oauth/access_token
            scopes:
              - read:user
              - user:email
```

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
auth:
  provider: atlassian
  atlassian:
    client_id: your_client_id
    client_secret: your_client_secret
    auth_url: https://auth.atlassian.com/authorize
    token_url: https://auth.atlassian.com/oauth/token
    audience: api.atlassian.com
    scopes:
      - read:me
      - read:jira-work
      - write:jira-work
```

### 3. Available Scopes

| Scope | Access |
|-------|--------|
| `read:me` | User profile |
| `read:jira-work` | Read Jira issues |
| `write:jira-work` | Create/update issues |
| `read:confluence-content.all` | Read Confluence pages |

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
auth:
  provider: salesforce
  salesforce:
    client_id: your_consumer_key
    client_secret: your_consumer_secret
    auth_url: https://login.salesforce.com/services/oauth2/authorize
    token_url: https://login.salesforce.com/services/oauth2/token
    scopes:
      - openid
      - profile
      - email
      - api
```

### 3. Sandbox Environment

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
auth:
  provider: google
  google:
    client_id: your_client_id.apps.googleusercontent.com
    client_secret: your_client_secret
    auth_url: https://accounts.google.com/o/oauth2/v2/auth
    token_url: https://oauth2.googleapis.com/token
    scopes:
      - openid
      - email
      - profile
```

### 3. Domain Restriction

Restrict to specific Google Workspace domain:

```yaml
google:
  # ... credentials ...
  hd: yourcompany.com  # Hosted domain
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
auth:
  provider: keycloak
  keycloak:
    client_id: mxcp-server
    client_secret: your_client_secret
    auth_url: https://keycloak.example.com/realms/myrealm/protocol/openid-connect/auth
    token_url: https://keycloak.example.com/realms/myrealm/protocol/openid-connect/token
    scopes:
      - openid
      - profile
      - email
```

## Token Persistence

MXCP stores OAuth tokens for session continuity:

```yaml
auth:
  provider: github
  token_persistence:
    enabled: true
    path: ~/.mxcp/tokens.json  # Encrypted storage
```

Tokens are:
- Encrypted at rest
- Refreshed automatically when expired
- Cleared on logout

## User Context

After authentication, user information is available in policies:

```yaml
policies:
  input:
    - condition: "user.email.endsWith('@yourcompany.com')"
      action: allow

    - condition: "user.role != 'admin'"
      action: deny
```

### Available User Fields

| Field | Description |
|-------|-------------|
| `user.id` | Unique user identifier |
| `user.email` | User's email address |
| `user.name` | Display name |
| `user.role` | User role (if configured) |
| `user.permissions` | List of permissions |
| `user.groups` | Group memberships |

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

When running behind a reverse proxy:

### nginx

```nginx
location / {
    proxy_pass http://localhost:8000;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
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

## Next Steps

- [Policies](policies) - Configure access control
- [Auditing](auditing) - Track authentication events
- [Configuration](/operations/configuration) - More configuration options
