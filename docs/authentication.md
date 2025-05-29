# Authentication

MXCP supports OAuth authentication to protect your endpoints and tools. When authentication is enabled, all tools, resources, prompts, and built-in SQL features require valid authentication tokens.

## Overview

Authentication is configured in your user configuration file (`~/.mxcp/config.yml`) under each profile's `auth` section. MXCP supports multiple OAuth providers and can be easily extended to support additional providers.

### How It Works

When authentication is enabled:

1. **Server Startup**: The MXCP server initializes with OAuth support
2. **Client Registration**: MCP clients can register with the OAuth server
3. **Authorization Flow**: Clients are redirected to the OAuth provider for authentication
4. **Token Exchange**: Provider auth codes are exchanged for access tokens
5. **Protected Access**: All endpoints require valid tokens

### Protected Features

When authentication is enabled, the following features require authentication:

- **Custom Endpoints**: All tools, resources, and prompts defined in your YAML files
- **SQL Tools**: Built-in DuckDB querying and schema exploration tools

### User Information Logging

When OAuth authentication is enabled, MXCP automatically logs detailed user information for each authenticated request, including:

- Username and user ID
- OAuth provider (e.g., GitHub, Atlassian)
- User's display name and email (when available)

This information appears in the server logs whenever an authenticated user executes any tool, resource, or prompt.

## Supported Providers

Currently supported providers:
- `none` (default, no authentication)
- `github` (GitHub OAuth)
- `atlassian` (Atlassian Cloud - JIRA & Confluence)

## Provider Configuration

### Disable Authentication (Default)

By default, authentication is disabled:

```yaml
projects:
  my_project:
    profiles:
      dev:
        auth:
          provider: none
```

### GitHub OAuth

#### Creating a GitHub OAuth App

1. **Create a GitHub OAuth App**:
   - Go to GitHub Settings > Developer settings > OAuth Apps
   - Click "New OAuth App"
   - Set the Authorization callback URL to: `http://localhost:8000/github/callback` (adjust host/port as needed)

2. **Get Your Credentials**:
   - Copy your **Client ID** and **Client Secret**
   - Store these securely as environment variables

#### Environment Variables

Set these environment variables with your GitHub OAuth credentials:

```bash
export GITHUB_CLIENT_ID="your_github_client_id"
export GITHUB_CLIENT_SECRET="your_github_client_secret"
```

#### MXCP Configuration

Configure GitHub OAuth in your profile's auth section:

```yaml
projects:
  my_project:
    profiles:
      dev:
        auth:
          provider: github
          clients:
            - client_id: "${GITHUB_CLIENT_ID}"
              client_secret: "${GITHUB_CLIENT_SECRET}"
              name: "My MXCP Application"
              redirect_uris:
                - "http://localhost:8000/github/callback"
              scopes:
                - "mxcp:access"
          github:
            client_id: "${GITHUB_CLIENT_ID}"
            client_secret: "${GITHUB_CLIENT_SECRET}"
            scope: "user:email"
            callback_path: "/github/callback"
            auth_url: "https://github.com/login/oauth/authorize"
            token_url: "https://github.com/login/oauth/access_token"
```

#### Configuration Options

- `client_id`: Your GitHub OAuth app client ID
- `client_secret`: Your GitHub OAuth app client secret
- `scope`: OAuth scope to request (default: "user:email")
- `callback_path`: Callback path for OAuth flow (default: "/github/callback")
- `auth_url`: GitHub authorization URL
- `token_url`: GitHub token exchange URL

#### Testing Your Configuration

1. Start your MXCP server:
   ```bash
   mxcp serve --debug
   ```

2. The authentication flow will begin when a client connects
3. Users will be redirected to GitHub for authorization
4. After approval, they'll be redirected back to your callback URL
5. Check the logs for successful authentication

#### Troubleshooting

**Common Issues:**

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

### Atlassian OAuth (JIRA & Confluence Cloud)

MXCP supports OAuth authentication with Atlassian Cloud products including JIRA and Confluence. This allows your MCP server to authenticate users and access Atlassian APIs on their behalf.

#### Creating an Atlassian OAuth App

Before configuring MXCP, you need to create an OAuth 2.0 (3LO) app in the Atlassian Developer Console:

**Step 1: Access the Developer Console**

1. Go to [developer.atlassian.com](https://developer.atlassian.com)
2. Sign in with your Atlassian account
3. Click your profile icon in the top-right corner
4. Select **Developer console** from the dropdown

**Step 2: Create a New App**

1. Click **Create** and select **OAuth 2.0 (3LO)**
2. Enter your app details:
   - **App name**: A descriptive name for your application
   - **Description**: Brief description of what your app does

**Step 3: Configure OAuth 2.0**

1. In your app, select **Authorization** from the left menu
2. Next to **OAuth 2.0 (3LO)**, click **Configure**
3. Set the **Callback URL** to match your MXCP server:
   - For local development: `http://localhost:8000/atlassian/callback`
   - For production: `https://your-domain.com/atlassian/callback`
4. Click **Save changes**

**Step 4: Add API Permissions**

1. Select **Permissions** from the left menu
2. Add the APIs you need:
   - **Jira platform REST API** - for JIRA access
   - **Confluence Cloud REST API** - for Confluence access
   - **User Identity API** - for user profile information
3. For each API, click **Add** and configure the required scopes.

**Step 5: Get Your Credentials**

1. Go to **Settings** in the left menu
2. Copy your **Client ID** and **Secret**
3. Store these securely as environment variables

#### Environment Variables

Set these environment variables with your Atlassian OAuth credentials:

```bash
export ATLASSIAN_CLIENT_ID="your_client_id_here"
export ATLASSIAN_CLIENT_SECRET="your_client_secret_here"
```

#### MXCP Configuration

Configure Atlassian OAuth in your profile's auth section:

```yaml
projects:
  my_project:
    profiles:
      production:
        auth:
          provider: atlassian
          clients:
            - client_id: "${ATLASSIAN_CLIENT_ID}"
              client_secret: "${ATLASSIAN_CLIENT_SECRET}"
              name: "My MXCP Application"
              redirect_uris:
                - "https://your-domain.com/atlassian/callback"
              scopes:
                - "mxcp:access"
          atlassian:
            client_id: "${ATLASSIAN_CLIENT_ID}"
            client_secret: "${ATLASSIAN_CLIENT_SECRET}"
            scope: "read:jira-work read:jira-user read:confluence-content.all read:confluence-user offline_access"
            callback_path: "/atlassian/callback"
            auth_url: "https://auth.atlassian.com/authorize"
            token_url: "https://auth.atlassian.com/oauth/token"
```

#### OAuth Scopes

Atlassian uses granular scopes to control access. Common scopes include:

**JIRA Scopes:**
- `read:jira-work` - Read issues, projects, and work items
- `write:jira-work` - Create and update issues
- `read:jira-user` - Read user information
- `manage:jira-project` - Manage projects (admin level)
- `manage:jira-configuration` - Manage JIRA configuration (admin level)

**Confluence Scopes:**
- `read:confluence-content.all` - Read all Confluence content
- `write:confluence-content` - Create and update content
- `read:confluence-user` - Read user information
- `manage:confluence-configuration` - Manage Confluence settings (admin level)

**Universal Scopes:**
- `read:me` - Read user profile information
- `offline_access` - Enable refresh tokens for long-term access

#### Accessing Multiple Sites

Atlassian OAuth grants access to all sites where your app is installed. To work with specific sites:

1. **Get accessible resources**:
   ```bash
   curl -H "Authorization: Bearer ACCESS_TOKEN" \
        https://api.atlassian.com/oauth/token/accessible-resources
   ```

2. **Use the cloud ID** in API requests:
   ```bash
   # JIRA API example
   curl -H "Authorization: Bearer ACCESS_TOKEN" \
        https://api.atlassian.com/ex/jira/{cloudid}/rest/api/2/project
   
   # Confluence API example  
   curl -H "Authorization: Bearer ACCESS_TOKEN" \
        https://api.atlassian.com/ex/confluence/{cloudid}/rest/api/space
   ```

#### Testing Your Configuration

1. Start your MXCP server:
   ```bash
   mxcp serve --debug
   ```

2. The authentication flow will begin when a client connects
3. Users will be redirected to Atlassian for authorization
4. After approval, they'll be redirected back to your callback URL
5. Check the logs for successful authentication

#### Troubleshooting

**Common Issues:**

1. **Invalid Client Configuration**:
   ```
   ValueError: Atlassian OAuth configuration is incomplete
   ```
   - Ensure `client_id` and `client_secret` are provided
   - Check that environment variables are set correctly

2. **Callback URL Mismatch**:
   ```
   HTTPException: Invalid state parameter
   ```
   - Verify the callback URL in your Atlassian app matches your MXCP configuration
   - Ensure the URL scheme (http/https) is correct

3. **Insufficient Permissions**:
   ```
   403 Forbidden
   ```
   - Check that your app has the required API permissions in the Developer Console
   - Verify the user has access to the requested resources

4. **Site Access Issues**:
   ```
   No accessible resources found
   ```
   - Ensure your app is installed on the Atlassian site
   - Check that the user has granted access to your app

**Debug Tips:**

- Enable debug logging: `mxcp serve --debug`
- Check the Atlassian Developer Console for app installation status
- Verify OAuth scopes match your API requirements
- Test with a simple scope like `read:me` first

#### Security Best Practices

- **Store credentials securely**: Use environment variables, not config files
- **Use HTTPS**: Required for production OAuth flows
- **Minimal scopes**: Request only the permissions you need
- **Token management**: Implement proper token refresh logic
- **Site validation**: Verify users have access to required Atlassian sites

## OAuth Client Registration

MXCP supports multiple ways for OAuth clients to register and authenticate:

### Pre-registered Clients (Recommended for Development)

You can pre-register OAuth clients in your configuration file. This is the most straightforward approach for development and testing:

```yaml
projects:
  my_project:
    profiles:
      dev:
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

### Dynamic Client Registration (RFC 7591)

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

### Production Recommendations

For production deployments:

1. **Remove development clients**: Don't include test/development client IDs in production configs
2. **Use environment variables**: Store client secrets in environment variables, not config files
3. **Limit redirect URIs**: Only include production callback URLs
4. **Scope restrictions**: Use minimal required scopes
5. **HTTPS only**: Ensure all redirect URIs use HTTPS in production

Example production configuration:

```yaml
projects:
  my_project:
    profiles:
      prod:
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

## Security Considerations

- **Environment Variables**: Store sensitive credentials in environment variables, not in config files
- **HTTPS**: Use HTTPS in production environments
- **Scope Limitation**: Request only the minimum required OAuth scopes
- **Token Expiration**: Tokens have a default expiration of 1 hour

## General Troubleshooting

### Debug Logging

Enable debug logging to troubleshoot authentication issues:

```bash
mxcp serve --debug
```

### Common Patterns

Most authentication issues fall into these categories:

1. **Configuration Issues**: Missing or incorrect OAuth app settings
2. **Environment Variables**: Credentials not properly set
3. **URL Mismatches**: Callback URLs don't match between provider and MXCP
4. **Permission Issues**: Insufficient scopes or user permissions
5. **Network Issues**: Connectivity problems with OAuth providers

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

## Adding New Providers

The authentication system is designed to be extensible. Future OAuth providers can be added by:

1. Implementing the `ExternalOAuthHandler` interface in a new provider file
2. Adding provider-specific configuration to the schema
3. Updating the `create_oauth_handler` factory function
4. Adding documentation following the same structure as existing providers

Each new provider should follow the same documentation structure:
- **Creating an OAuth App**: Step-by-step provider setup
- **Environment Variables**: Required credentials
- **MXCP Configuration**: Configuration examples
- **Configuration Options**: Available settings
- **Testing**: How to verify the setup
- **Troubleshooting**: Common issues and solutions 