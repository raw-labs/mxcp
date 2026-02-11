---
title: "Auth & OAuth Internals (Maintainers)"
description: "Internal OAuth architecture and invariants for maintaining MXCP issuer-mode auth."
---

This guide is for contributors who maintain or extend MXCP authentication. For user-facing setup,
see [Authentication](/security/authentication).

## Goals of this guide

It focuses on:
- **Architecture**: which components own which responsibilities
- **Security invariants**: what must not change without careful review
- **Extension points**: how to add a provider or a storage backend safely
- **Debugging**: how to diagnose common failure modes quickly

## OAuth flow overview

These are the calls involved in the OAuth flow:
* `/register`: the client registers itself with a `client_id` in an IdP. It's optional since the client can be pre-registered in the IdP, and configured in the client. (For example our MXCP server config implies we've registered it as an app in the IdP.)
* `/authorize`: the client initiates the flow. That call contains its `client_id`, a `redirect_uri` and optionally a `state` and a `code_challenge` if using PKCE.
  - `state` is eventually returned by the IdP as it redirects the browser to `redirect_uri`. The `state` lets the client confirm the data belongs to the correct request
  - For PKCE, the client generates a random `code_verifier` and derives a `code_challenge` from it. The IdP stores the challenge and later verifies it when the client sends the `code_verifier` at `/token`, proving possession of the original verifier.
  The IdP redirects the browser to the client's `redirect_uri` with a `code`
  (nothing to do with `code_challenge`) that is meant to be exchanged for the final access token by `/token`.
* `/token` is called with the authorization code (the `code` returned by the redirection that occurred during `/authorize`). The client also sends the `code_verifier` if using PKCE, which is used by the token handler to validate the call against the initial `code_challenge`. It then returns the access token.

## MXCP issuer implementation

### Scope domains (critical distinction)

MXCP issuer-mode tracks **two different scope sets**. Do not mix them:

- **Provider scopes** (MXCP ↔ upstream IdP)
  - What MXCP requests from / receives from the upstream provider token endpoint.
  - Used for provider `/token` exchange and provider refresh operations.
  - Persisted on state as `StateRecord.provider_scopes_requested` so we can pass it into
    `ProviderAdapter.exchange_code(scopes=...)` and apply correct OAuth scope fallback
    when the provider omits `scope` in its token response.
- **MXCP scopes** (MXCP ↔ OAuth/MCP client)
  - What MXCP returns to the client in token responses (`scope` field) and uses for
    MXCP authorization.
  - Derived from provider context via a **scope mapper**.
  - Persisted on session as `UserInfo.mxcp_scopes` and on auth codes as `AuthCodeRecord.mxcp_scopes`.

Today the scope mapper is intentionally a placeholder (returns an empty list) to avoid leaking
provider scope strings to clients. See `mxcp.sdk.auth.auth_service.AuthService.derive_mxcp_scopes`.

1. When the client registers dynamically (DCR, Dynamic Client Registration), it calls `/register` and sends a `client_id` it generated along with a list of its `redirect_uris`. That step binds the client (identified by `client_id`) to allowed redirect URIs.
  * During the flow, a single `redirect_uri` is used. It's chosen by the client when it calls `/authorize` and has to match one of the registered URIs. It is where the MXCP server will eventually send the MXCP _authorization code_ (`auth_code`). That authorization code is eventually turned into the MXCP access token (the one appearing in the HTTP Authorization header in the end), by a call to `/token`.
2. The client calls `/authorize` with its `client_id` and a `redirect_uri`. MXCP validates `redirect_uri` against the stored client record. From then on,
the goal of MXCP is to redirect the client's browser to the IdP's `/authorize`.
  * The `/authorize` step optionally involves a safety check using a _state_. The MCP client can add a `state` to its `/authorize` call. That state is eventually returned to the client who can use it to verify the message belongs to the particular request it initiated. It is a string it generates. MXCP stores it as `client_state`, and eventually returns it to the client like the protocol expects.
  * MXCP itself generates a `state`, another OAuth `state` string but for the MXCP/IdP side. It's stored as `state` in the code. That state is one-time and
  consumed on callback (see below).
  * In a regular OAuth flow involving a client and an IdP, the client communicates its `redirect_uri` to the IdP. The IdP eventually redirects the browser to that `redirect_uri`, passing the client's `state` and the IdP's generated `code`.
  * `code` is an IdP-generated short-lived code that can eventually be exchanged
  for an access token.
  * With MXCP in the picture, the client's call to MXCP's `/authorize` instead redirects the browser to the IdP's `/authorize`, but with MXCP's details (its `client_id`, its `state`, its `code_challenge` if the IdP supports PKCE, and with its _MXCP_ `callback_url`, the one configured with the `callback_path` config knob). Meaning the IdP's answer to the `/authorize` redirects the user's browser to the MXCP callback, with the MXCP supplied `state` and the IdP's `code`.
3. Upon getting its own callback called, MXCP will redirect the browser to the
   original client's callback:
   1. Validates the `state` (its own, now sent by the IdP). It consumes it and deletes it.
   2. Calls the IdP to exchange the `code` for an access token using the IdP's `/token` call.
   3. Fetches user info from the provider.
   4. Derives MXCP client-facing scopes using the scope mapper. Issues and persists an MXCP session (it contains the MXCP `access_token` and refresh token, the IdP's tokens, provider granted scopes, and MXCP scopes).
   5. Creates and persists an MXCP `auth_code`, which is meant to play the role of the OAuth `code` sent to the MCP client, and stores **MXCP scopes** on it.
   6. Redirects the browser to the client's `redirect_uri` with the `code` (`auth_code`) and the original client's `state` (`client_state`).
4. The client's callback is called with the client's original `state` (if it was present) and MXCP's `code`.
  * The client calls MXCP's `/token` with MXCP's auth code, its `client_id`, and `redirect_uri` (used to validate the call on the server/MXCP side) plus its PKCE `code_verifier`. MCP's token handler validates the verifier against the stored `code_challenge`, then MXCP returns the `access_token` it generated earlier, and a `refresh_token`.

## Mental model

MXCP runs OAuth in **issuer-mode**:
- **MCP clients authenticate to MXCP** using OAuth.
- **MXCP can authenticate users against an upstream IdP** (via `ProviderAdapter` — built-in adapters for GitHub, Atlassian, Salesforce, Google, Keycloak, and a generic OIDC adapter for any OIDC-compliant IdP).

The key idea is that **the IdP callback always returns to MXCP**, and then **MXCP redirects to the MCP client**.

### Core components (new stack)

- **Contracts**: `mxcp.sdk.auth.contracts`
  - Defines `ProviderAdapter`, `GrantResult`, `UserInfo`, `ProviderError`.
- **Orchestration**: `mxcp.sdk.auth.auth_service.AuthService`
  - Drives `/authorize` → callback → code issuance → token exchange.
- **Lifecycle**: `mxcp.sdk.auth.session_manager.SessionManager`
  - Creates/consumes state, issues sessions, creates auth codes.
- **Persistence**: `mxcp.sdk.auth.storage.TokenStore` + `SqliteTokenStore`
  - Source of truth for expiry + one-time use semantics and persistence across restarts.
- **Server bridge**: `mxcp.server.core.auth.issuer_provider.IssuerOAuthAuthorizationServer`
  - Adapts MXCP’s auth stack to the MCP OAuth provider interface.
- **Request auth**: `mxcp.sdk.auth.middleware.AuthenticationMiddleware`
  - Loads sessions by access token and sets user context.

### Legacy stack

The legacy handler-based stack has been removed. Only the ProviderAdapter-based issuer-mode stack is supported.

## OAuth flows (issuer-mode)

### 1) /authorize (client → MXCP)

- Input: `client_id`, `redirect_uri`, optional `state`, optional `code_challenge`.
- MXCP validates the client and redirect URI against **persisted** client registration.
- MXCP creates a **StateRecord** (one-time, expiring) to bind:
  - client_id
  - client redirect_uri
  - downstream PKCE fields (client ↔ MXCP)
  - upstream PKCE verifier (MXCP ↔ IdP), if used
  - the original client `state` (returned back to the client)
- MXCP stores the **provider scopes requested** in the StateRecord as
  `provider_scopes_requested` (provider scopes are derived from server/provider configuration;
  client-supplied OAuth scopes are ignored for upstream IdP authorization).
- The downstream `code_challenge` is stored so the MCP token handler can verify the
  client `code_verifier` during the `/token` exchange.
- MXCP redirects the browser to the IdP `/authorize`, using **MXCP callback URL**.

### 2) Callback (IdP → MXCP callback)

- Input: `code` and `state` (or `error` and `state`).
- MXCP consumes state (one-time) and exchanges provider code for provider tokens.
- Provider token exchange uses `StateRecord.provider_scopes_requested` as the requested
  provider scopes (this is important for correct OAuth behavior when the provider token
  response omits `scope`).
- MXCP issues:
  - an MXCP **session** (opaque MXCP access token + refresh token)
  - an MXCP **authorization code** bound to the session
- MXCP derives and persists **MXCP client-facing scopes** via the scope mapper:
  - stored on the session as `UserInfo.mxcp_scopes`
  - stored on the auth code as `AuthCodeRecord.mxcp_scopes`
- MXCP redirects the browser to the *client redirect_uri* with the MXCP auth code and the original client state.

### 3) /token exchange (client → MXCP)

- Input: MXCP auth code + downstream PKCE verifier.
- Token endpoint verifies PKCE (per MCP framework) and then MXCP:
  - validates code binding (client_id / redirect_uri)
  - ensures one-time use of the auth code
  - returns MXCP access token (and refresh token)
- The token response `scope` field reflects **MXCP scopes** (not provider scopes).

## Security invariants (“do not break”)

If you change code touching these rules, require a careful review.

- **State is one-time use**
  - State must be consumed (deleted) on first use.
  - Expired state must be rejected.
- **Auth codes are one-time use**
  - Auth codes must be deleted on redemption (when the `auth_code` is exchanged for an `access_token` during the call to `/token`).
  - Expired auth codes must be rejected.
- **Redirect URI binding is strict**
  - `redirect_uri` must be validated against persisted client registration.
  - Never redirect to a URI that wasn’t safely derived from stored state/client metadata.
- **Issuer-mode scopes policy**
  - OAuth client-requested scopes must **not** influence upstream IdP scopes.
  - Upstream IdP scopes come from server/provider configuration and are persisted on state as
    `StateRecord.provider_scopes_requested`.
  - When provider scope config is omitted or empty, MXCP requests no scopes upstream.
  - When a provider token response omits `scope` (allowed by OAuth), provider adapters treat the
    granted scopes as the requested provider scopes (do not interpret omission as “no scopes”).
  - Client-facing scopes returned by MXCP are **MXCP scopes** derived via the scope mapper and stored
    on sessions (`UserInfo.mxcp_scopes`) and auth codes (`AuthCodeRecord.mxcp_scopes`).
  - Refresh requests that include `scope` must follow OAuth semantics:
    - allowed: omitted (same scopes) or subset of previously-issued MXCP scopes
    - forbidden: scope expansion
- **PKCE boundaries are explicit**
  - Downstream PKCE: client ↔ MXCP token endpoint.
  - Upstream PKCE: MXCP ↔ IdP token exchange (provider capability).
- **No sensitive logging**
  - Never log tokens, secrets, emails, or user identifiers.
  - Avoid logging raw exception messages if they may contain sensitive data.
- **Session-first request auth**
  - Middleware must treat provider user-info refresh as best-effort.
  - Provider failures must never block session-based authentication.
- **Token persistence policy**
  - MXCP access tokens should be stored hashed.
  - Provider tokens should be encrypted at rest when persistence is enabled.

## Extension guide

### Add a new provider (IdP)

If the IdP is OIDC-compliant, users can use the **generic `oidc` provider** (`mxcp.sdk.auth.providers.oidc.OIDCProviderAdapter`) instead of writing a dedicated adapter. The generic adapter auto-discovers endpoints from the IdP's `.well-known/openid-configuration` document at startup via `ensure_ready()`.

For IdPs that require non-standard behavior (custom token exchange, non-OIDC user endpoints, etc.), implement `ProviderAdapter` under `mxcp.sdk.auth.providers`:
- Raise `ProviderError(error, description, status_code)` for expected failures.
- Normalize transport/network failures into `ProviderError` (do not leak HTTP client exceptions).
- Never log response bodies, tokens, secrets, or PII.

Coverage expectations:
- `tests/sdk/auth/test_<provider>_provider_adapter.py`
  - authorize URL parameter correctness
  - token error parsing (non-200, invalid JSON, OAuth error objects)
  - scope semantics (omitted/empty provider scope → no scopes requested)

### Add a new storage backend

Implement the `TokenStore` protocol:
- Enforce one-time state consumption and auth code one-time use.
- Honor TTL on reads and delete expired records.
- Ensure async safety (thread-safe if wrapping sync I/O).

Coverage expectations:
- Extend `tests/sdk/auth/test_token_store.py` for backend parity.

### Where to look
- State handling: `mxcp.sdk.auth.session_manager.SessionManager` and `mxcp.sdk.auth.storage.TokenStore`
- Auth code redemption: `mxcp.sdk.auth.auth_service.AuthService.exchange_token`
- Server bridge validation: `mxcp.server.core.auth.issuer_provider.IssuerOAuthAuthorizationServer`
- Callback route behavior: `mxcp.server.interfaces.server.mcp.RAWMCP._register_oauth_routes`
- Scope mapping placeholder: `mxcp.sdk.auth.auth_service.AuthService.derive_mxcp_scopes`
