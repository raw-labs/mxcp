# Keycloak Authentication Example

This example demonstrates how to configure MXCP with Keycloak authentication.

## Prerequisites

1. A running Keycloak server (see quick start below)
2. MXCP installed (`pip install mxcp`)

## Quick Start with Docker

Run Keycloak using Docker:

```bash
docker run -p 8080:8080 \
  -e KC_BOOTSTRAP_ADMIN_USERNAME=admin \
  -e KC_BOOTSTRAP_ADMIN_PASSWORD=admin \
  quay.io/keycloak/keycloak:latest start-dev
```

## Keycloak Setup

1. Access the admin console at http://localhost:8080/admin
2. Login with username: `admin`, password: `admin`
3. Create a new realm (or use the default `master` realm)
4. Create a new client:
   - Client ID: `mxcp-demo`
   - Client authentication: ON
   - Valid redirect URIs: `http://localhost:8000/*`
5. Copy the client secret from the Credentials tab

## Configuration

Set environment variables:

```bash
export KEYCLOAK_CLIENT_ID="mxcp-demo"
export KEYCLOAK_CLIENT_SECRET="your-client-secret"
export KEYCLOAK_REALM="master"  # or your custom realm
export KEYCLOAK_SERVER_URL="http://localhost:8080"
```

## Running the Example

1. Start the MXCP server:
   ```bash
   cd examples/keycloak
   mxcp serve --debug
   ```

2. In another terminal, connect with the MCP client:
   ```bash
   mcp connect http://localhost:8000
   ```

3. You'll be redirected to Keycloak for authentication

## Testing Tools

Once authenticated, try running these example tools:

```bash
# Get current user info
mcp run tool get_user_info

# Query data with user context
mcp run resource user_data
```

## Production Considerations

- Use HTTPS for all URLs in production
- Configure proper redirect URIs
- Set up appropriate Keycloak realm roles and permissions
- Enable refresh token rotation
- Configure session timeouts 