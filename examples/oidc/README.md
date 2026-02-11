# Generic OIDC Authentication Example

This example demonstrates how to configure MXCP with any OpenID Connect-compliant identity provider using the generic `oidc` provider type. Endpoints are auto-discovered from the provider's `.well-known/openid-configuration` document.

## Prerequisites

1. An OIDC-compliant identity provider (Keycloak, Auth0, Okta, Azure AD, etc.)
2. MXCP installed (`pip install mxcp`)

## Quick Start with Keycloak

Run Keycloak using Docker:

```bash
docker run -p 8080:8080 \
  -e KC_BOOTSTRAP_ADMIN_USERNAME=admin \
  -e KC_BOOTSTRAP_ADMIN_PASSWORD=admin \
  quay.io/keycloak/keycloak:latest start-dev
```

### Keycloak Setup

1. Access the admin console at http://localhost:8080/admin
2. Login with username: `admin`, password: `admin`
3. Create a new realm (or use the default `master` realm)
4. Create a new client:
   - Client ID: `mxcp-demo`
   - Client authentication: ON
   - Valid redirect URIs: `http://localhost:8000/*`
5. Copy the client secret from the Credentials tab
6. For automated testing, enable "Direct Access Grants" on the client

## Configuration

Set environment variables:

```bash
# The discovery URL for your OIDC provider
export OIDC_CONFIG_URL="http://localhost:8080/realms/master/.well-known/openid-configuration"
export OIDC_CLIENT_ID="mxcp-demo"
export OIDC_CLIENT_SECRET="your-client-secret"
```

## Running the Example

1. Start the MXCP server:
   ```bash
   cd examples/oidc
   mxcp serve --debug
   ```

2. In another terminal, connect with the MCP client:
   ```bash
   mcp connect http://localhost:8000
   ```

3. You'll be redirected to your OIDC provider for authentication

## End-to-End Test

An automated test script is provided that uses Keycloak's Direct Access Grants
to test the full flow without a browser:

```bash
export KEYCLOAK_SERVER_URL="http://localhost:8080"
export KEYCLOAK_REALM="master"
export KEYCLOAK_CLIENT_ID="mxcp-demo"
export KEYCLOAK_CLIENT_SECRET="your-client-secret"
export OIDC_TEST_USERNAME="testuser"
export OIDC_TEST_PASSWORD="testpassword"

python scripts/test_oidc_e2e.py
```

## Using with Other Providers

The generic OIDC provider works with any provider that supports OpenID Connect Discovery:

- **Auth0**: `https://your-tenant.auth0.com/.well-known/openid-configuration`
- **Okta**: `https://your-org.okta.com/.well-known/openid-configuration`
- **Azure AD**: `https://login.microsoftonline.com/{tenant}/v2.0/.well-known/openid-configuration`
- **Google**: `https://accounts.google.com/.well-known/openid-configuration`

### Optional Configuration

```yaml
auth:
  provider: oidc
  oidc:
    config_url: "${OIDC_CONFIG_URL}"
    client_id: "${OIDC_CLIENT_ID}"
    client_secret: "${OIDC_CLIENT_SECRET}"
    scope: "openid profile email"
    callback_path: "/oidc/callback"
    # Optional: audience for APIs (e.g. Auth0 API identifier)
    audience: "https://api.example.com"
    # Optional: extra parameters for the authorize URL
    extra_authorize_params:
      prompt: "consent"
```

## Production Considerations

- Use HTTPS for all URLs in production
- Configure proper redirect URIs in your OIDC provider
- Review the scopes you request — only request what you need
- Enable refresh token rotation if your provider supports it
- Configure session timeouts appropriately
