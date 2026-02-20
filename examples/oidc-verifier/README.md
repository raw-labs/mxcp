# OIDC Verifier Mode Example

This example shows how to configure MXCP in **verifier mode** for an OIDC-compliant
identity provider. In verifier mode, MXCP does **not** perform the OAuth login
flow; it validates inbound access tokens and populates user context for tools.

> Note: Verifier mode requires the corresponding implementation in MXCP. If the
> feature is not yet available, this config will not be accepted by the server.

## Prerequisites

- An OIDC-compliant IdP that supports discovery
- An OAuth client registered with your IdP
- MXCP installed (`pip install mxcp`)

## Configuration

Set environment variables used by `config.yml`:

```bash
export OIDC_CONFIG_URL="https://your-idp.example.com/.well-known/openid-configuration"
export OIDC_CLIENT_ID="your-client-id"
export OIDC_CLIENT_SECRET="your-client-secret"
```

## Run

From this directory:

```bash
mxcp serve --debug --transport streamable-http --port 8000
```

## Test Tool

The `get_user_info` tool uses the request user context:

- `get_username()`
- `get_user_email()`
- `get_user_provider()`

Call it from any MCP client that can set `Authorization: Bearer <token>` headers.
