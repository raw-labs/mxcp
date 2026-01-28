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
   4. Issues and persists an MXCP session (it contains the MXCP `access_token`, and the IdP's refresh and access tokens).
   5. Creates and persist an MXCP `auth_code`, which is meant to play the role of the OAuth `code` sent to the MCP client.
   6. Redirects the browser to the client's `redirect_uri` with the `code` (`auth_code`) and the original client's `state` (`client_state`).
4. The client's callback is called with the client's original `state` (if it was present) and MXCP's `code`.
  * The client calls MXCP's `/token` with MXCP's auth code, its `client_id`, and `redirect_uri` (used to validate the call on the server/MXCP side) plus its PKCE `code_verifier`. MCP's token handler validates the verifier against the stored `code_challenge`, then MXCP returns the `access_token` it generated earlier, and a `refresh_token`.

## Mental model

MXCP runs OAuth in **issuer-mode**:
- **MCP clients authenticate to MXCP** using OAuth.
- **MXCP can authenticate users against an upstream IdP** (Google/Atlassian today via `ProviderAdapter`).

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
- The downstream `code_challenge` is stored so the MCP token handler can verify the
  client `code_verifier` during the `/token` exchange.
- MXCP redirects the browser to the IdP `/authorize`, using **MXCP callback URL**.

### 2) Callback (IdP → MXCP callback)

- Input: `code` and `state` (or `error` and `state`).
- MXCP consumes state (one-time) and exchanges provider code for provider tokens.
- MXCP issues:
  - an MXCP **session** (opaque MXCP access token + refresh token)
  - an MXCP **authorization code** bound to the session
- MXCP redirects the browser to the *client redirect_uri* with the MXCP auth code and the original client state.

### 3) /token exchange (client → MXCP)

- Input: MXCP auth code + downstream PKCE verifier.
- Token endpoint verifies PKCE (per MCP framework) and then MXCP:
  - validates code binding (client_id / redirect_uri)
  - ensures one-time use of the auth code
  - returns MXCP access token (and refresh token)

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
  - Upstream IdP scopes come from server/provider configuration.
  - Client-supplied scopes may be stored as metadata (DCR or `/authorize`) but are not used for IdP authorization.
  - When a provider token response omits `scope` (allowed by OAuth), MXCP treats the
    granted scopes as the configured provider scopes used at `/authorize` rather than
    interpreting the omission as “no scopes”.
- **PKCE boundaries are explicit**
  - Downstream PKCE: client ↔ MXCP token endpoint.
  - Upstream PKCE: MXCP ↔ IdP token exchange (provider capability).
- **No sensitive logging**
  - Never log tokens, secrets, emails, or user identifiers.
  - Avoid logging raw exception messages if they may contain sensitive data.
- **Token persistence policy**
  - MXCP access tokens should be stored hashed.
  - Provider tokens should be encrypted at rest when persistence is enabled.

## Extension guide

### Add a new provider (IdP)

Implement `ProviderAdapter` under `mxcp.sdk.auth.providers`:
- Raise `ProviderError(error, description, status_code)` for expected failures.
- Never log response bodies, tokens, secrets, or PII.

Coverage expectations:
- `tests/sdk/auth/test_<provider>_provider_adapter.py`
  - authorize URL parameter correctness
  - token error parsing (non-200, invalid JSON, OAuth error objects)
  - scope semantics (provider `scope` field optional)

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
