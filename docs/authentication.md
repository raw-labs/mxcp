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