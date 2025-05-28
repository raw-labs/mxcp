# Authentication

MXCP supports OAuth authentication to protect your endpoints and tools. When authentication is enabled, all tools, resources, prompts, and built-in SQL features require valid authentication tokens.

## Configuration

Authentication is configured in your user configuration file (`~/.mxcp/config.yml`) under the `auth` section.

### Disable Authentication (Default)

By default, authentication is disabled:

```yaml
auth:
  provider: none
```

### GitHub OAuth

To enable GitHub OAuth authentication:

```yaml
auth:
  provider: github
  github:
    client_id: "${GITHUB_CLIENT_ID}"
    client_secret: "${GITHUB_CLIENT_SECRET}"
    scope: "user:email"
    callback_path: "/github/callback"
    auth_url: "https://github.com/login/oauth/authorize"
    token_url: "https://github.com/login/oauth/access_token"
```

## OAuth Client Registration

MXCP supports multiple ways for OAuth clients to register and authenticate:

### 1. Pre-registered Clients (Recommended for Development)

You can pre-register OAuth clients in your configuration file. This is the most straightforward approach for development and testing:

```yaml
auth:
  provider: github
  
  # Pre-registered OAuth clients
  clients:
    # MCP CLI client (public client)
    - client_id: "aa27466a-fd71-4c2a-9ecf-8b5db5d34384"
      name: "MCP CLI Development Client"
      redirect_uris:
        - "http://127.0.0.1:49153/oauth/callback"
        - "http://localhost:49153/oauth/callback"
      scopes:
        - "mxcp:access"
    
    # Custom application (confidential client)
    - client_id: "my-custom-app-client-id"
      client_secret: "${MY_APP_CLIENT_SECRET}"
      name: "My Custom Application"
      redirect_uris:
        - "https://myapp.example.com/oauth/callback"
      grant_types:
        - "authorization_code"
        - "refresh_token"
      scopes:
        - "mxcp:access"
        - "mxcp:admin"
  
  github:
    # ... GitHub configuration
```

**Client Configuration Options:**
- `client_id` (required): Unique identifier for the client
- `name` (required): Human-readable name for the client
- `client_secret` (optional): Secret for confidential clients (omit for public clients)
- `redirect_uris` (optional): Allowed redirect URIs (defaults to MCP CLI callback)
- `grant_types` (optional): Allowed OAuth grant types (defaults to `["authorization_code"]`)
- `scopes` (optional): Allowed OAuth scopes (defaults to `["mxcp:access"]`)

### 2. Dynamic Client Registration (RFC 7591)

MXCP implements RFC 7591 Dynamic Client Registration. Clients can register themselves at runtime by making a POST request to `/register`:

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

The server will respond with client credentials:

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

### 3. Production Recommendations

For production deployments:

1. **Remove development clients**: Don't include test/development client IDs in production configs
2. **Use environment variables**: Store client secrets in environment variables, not config files
3. **Limit redirect URIs**: Only include production callback URLs
4. **Scope restrictions**: Use minimal required scopes
5. **HTTPS only**: Ensure all redirect URIs use HTTPS in production

Example production configuration:

```yaml
auth:
  provider: github
  
  clients:
    - client_id: "${PROD_CLIENT_ID}"
      client_secret: "${PROD_CLIENT_SECRET}"
      name: "Production Application"
      redirect_uris:
        - "https://myapp.example.com/oauth/callback"
      scopes:
        - "mxcp:access"
  
  github:
    client_id: "${GITHUB_CLIENT_ID}"
    client_secret: "${GITHUB_CLIENT_SECRET}"
    # ... other GitHub config
```

#### GitHub OAuth Setup

1. **Create a GitHub OAuth App**:
   - Go to GitHub Settings > Developer settings > OAuth Apps
   - Click "New OAuth App"
   - Set the Authorization callback URL to: `http://localhost:8000/github/callback` (adjust host/port as needed)

2. **Set Environment Variables**:
   ```bash
   export GITHUB_CLIENT_ID="your_github_client_id"
   export GITHUB_CLIENT_SECRET="your_github_client_secret"
   ```

3. **Configuration Options**:
   - `client_id`: Your GitHub OAuth app client ID
   - `client_secret`: Your GitHub OAuth app client secret
   - `scope`: OAuth scope to request (default: "user:email")
   - `callback_path`: Callback path for OAuth flow (default: "/github/callback")
   - `auth_url`: GitHub authorization URL
   - `token_url`: GitHub token exchange URL

Example MXCP configuration with GitHub OAuth authentication:

```yaml
mxcp: "1.0.0"

# Authentication configuration
auth:
  provider: github
  github:
    client_id: "${GITHUB_CLIENT_ID}"
    client_secret: "${GITHUB_CLIENT_SECRET}"
    scope: "user:email"
    callback_path: "/github/callback"
    auth_url: "https://github.com/login/oauth/authorize"
    token_url: "https://github.com/login/oauth/access_token"

# Transport configuration
transport:
  provider: streamable-http
  http:
    port: 8000
    host: localhost

# Project configuration
projects:
  my-project:
    profiles:
      dev:
        secrets: []
        plugin:
          config: {} 
```

## How It Works

When authentication is enabled:

1. **Server Startup**: The MXCP server initializes with OAuth support
2. **Client Registration**: MCP clients can register with the OAuth server
3. **Authorization Flow**: Clients are redirected to GitHub for authentication
4. **Token Exchange**: GitHub auth codes are exchanged for access tokens
5. **Protected Access**: All endpoints require valid tokens

## Protected Features

When authentication is enabled, the following features require authentication:

- **Custom Endpoints**: All tools, resources, and prompts defined in your YAML files
- **SQL Tools**: Built-in DuckDB querying and schema exploration tools

## User Information Logging

When OAuth authentication is enabled, MXCP automatically logs detailed user information for each authenticated request, including:

- Username and user ID
- OAuth provider (e.g., GitHub)
- User's display name and email (when available)

This information appears in the server logs whenever an authenticated user executes any tool, resource, or prompt.

## Security Considerations

- **Environment Variables**: Store sensitive credentials in environment variables, not in config files
- **HTTPS**: Use HTTPS in production environments
- **Scope Limitation**: Request only the minimum required OAuth scopes
- **Token Expiration**: Tokens have a default expiration of 1 hour

## Troubleshooting

### Common Issues

1. **Invalid Client Configuration**:
   ```
   ValueError: GitHub OAuth configuration is incomplete
   ```
   - Ensure all required GitHub configuration fields are provided

2. **Environment Variables Not Set**:
   ```
   ValueError: Environment variable GITHUB_CLIENT_ID is not set
   ```
   - Set the required environment variables before starting the server

3. **Callback URL Mismatch**:
   ```
   HTTPException: Invalid state parameter
   ```
   - Ensure the callback URL in your GitHub OAuth app matches the configured callback_path

### Debug Logging

Enable debug logging to troubleshoot authentication issues:

```bash
mxcp serve --debug
```

## Future Providers

The authentication system is designed to be extensible. Future OAuth providers can be added by:

1. Implementing the `ExternalOAuthHandler` interface in a new provider file
2. Adding provider-specific configuration to the schema
3. Updating the `create_oauth_handler` factory function

Currently supported providers:
- `none` (default, no authentication)
- `github` (GitHub OAuth)

## Reverse Proxy Deployment

When deploying MXCP behind a reverse proxy (nginx, HAProxy, AWS ELB, etc.) that handles SSL/TLS termination, you need to configure the URL scheme properly for OAuth callbacks to work correctly.

### The Problem

OAuth providers require HTTPS callback URLs in production. When MXCP runs behind a reverse proxy with SSL termination:

1. **Client** → **HTTPS** → **Reverse Proxy** → **HTTP** → **MXCP**
2. MXCP sees only HTTP requests but needs to generate HTTPS callback URLs
3. Without proper configuration, OAuth flows fail with "CSRF detected" or "invalid callback URL" errors

### Solution Options

MXCP provides three ways to handle this:

#### Option 1: Explicit Scheme Configuration (Recommended)

Set the scheme explicitly in your transport configuration:

```yaml
transport:
  provider: streamable-http
  http:
    port: 8000
    host: "0.0.0.0"
    scheme: "https"  # Force HTTPS for all generated URLs
```

#### Option 2: Automatic Proxy Header Detection

Enable proxy header trust to automatically detect scheme from `X-Forwarded-Proto`:

```yaml
transport:
  provider: streamable-http
  http:
    port: 8000
    host: "0.0.0.0"
    trust_proxy: true  # Trust X-Forwarded-Proto and X-Forwarded-Scheme headers
```

Your reverse proxy must set the appropriate headers:

```nginx
# nginx configuration
proxy_set_header X-Forwarded-Proto $scheme;
proxy_set_header X-Forwarded-Host $host;
proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
```

#### Option 3: Complete Base URL Override

Specify the complete external URL:

```yaml
transport:
  provider: streamable-http
  http:
    base_url: "https://api.example.com"  # Complete external URL
```

### Example nginx Configuration

Here's a complete nginx configuration for SSL termination with MXCP:

```nginx
server {
    listen 80;
    server_name api.example.com;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name api.example.com;
    
    ssl_certificate /path/to/ssl/certificate.crt;
    ssl_certificate_key /path/to/ssl/private.key;
    
    # Security headers
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    add_header X-Frame-Options DENY always;
    add_header X-Content-Type-Options nosniff always;
    
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-Host $host;
        proxy_set_header X-Forwarded-Port $server_port;
        
        # WebSocket support (if needed)
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

### OAuth Client Configuration

Update your OAuth client redirect URIs to use HTTPS:

```yaml
auth:
  provider: github
  clients:
    - client_id: "${PROD_CLIENT_ID}"
      client_secret: "${PROD_CLIENT_SECRET}"
      name: "Production Application"
      redirect_uris:
        - "https://api.example.com/github/callback"  # HTTPS callback
      scopes:
        - "mxcp:access"
```

### Troubleshooting

**"CSRF detected" errors**: Usually indicates scheme mismatch. Check that:
- Your transport configuration specifies `scheme: "https"` or `trust_proxy: true`
- Your reverse proxy sets `X-Forwarded-Proto: https` header
- OAuth client redirect URIs use HTTPS

**"Invalid callback URL" errors**: OAuth provider rejects the callback URL. Verify:
- Callback URLs in OAuth provider settings match your configuration
- URLs use HTTPS in production environments
- No port numbers in URLs when using standard ports (80/443)

## Configuration

Authentication is configured in your user configuration file (`~/.mxcp/config.yml`) under the `auth` section. 