# MXCP Auth Refactor Guide

Use this as the implementation playbook to rebuild auth cleanly.

## Goals
- Single, clear OAuth flow (provider callback to MXCP, then MXCP redirects to client).
- Separation of concerns: adapters (IdP), sessions/tokens, storage, middleware/context, FastMCP bridge.
- Correctness first: PKCE enforced, state one-time use, expiry/revocation honored everywhere.
- Safe storage: hash MXCP tokens, encrypt provider tokens, deterministic schema.
- Observable and testable: unit + flow tests for every public path.

## Core flows
1) **/authorize (client → MXCP)**
   - Validate client_id/redirect_uri/scope.
   - Create OAuth state (one-time, expiring) with: client_id, client redirect_uri, MXCP callback URL, scopes, PKCE challenge.
   - Build provider authorize URL using MXCP callback URL (not the client redirect) and state.
   - Redirect client to provider authorize URL.

2) **Callback (provider → MXCP callback)**
   - Validate `state` (consume once) and required params (`code`, optional `code_verifier`).
   - PKCE: verify code_verifier against stored challenge when present.
   - Exchange code with provider adapter using MXCP callback URL.
   - Create Session (mxcp_token opaque, hashed; store provider tokens, scopes, expiry).
   - Issue MXCP auth code (short-lived, one-time) mapped to session_id.
   - Redirect to client redirect_uri with `code` (MXCP auth code) and original `state`.

3) **Token exchange (client → MXCP)**
   - Validate MXCP auth code (one-time, not expired); return MXCP access token (+ optional refresh) with scopes/expiry.

4) **Protected resource/middleware**
   - Validate MXCP access token (expiry + revocation) via session lookup.
   - Provide provider access token and user info to the request context (no extra session lookup if verifier already loaded it).

## Components & contracts
- **ProviderAdapter (IdP client)**: build_authorize_url(redirect_uri, state, scopes, code_challenge); exchange_code(code, redirect_uri, code_verifier); refresh_token; fetch_user_info; revoke_token. Surface ProviderError with status.
- **SessionManager**: owns sessions (mxcp_token hash → Session), auth codes, OAuth states. Mutations under one lock; avoid holding lock during storage I/O. Expose: create_session, get_session, delete_session, create/consume_state, store/consume_auth_code. Avoid duplicating expiry rules already enforced by the store.
- **TokenStore** (authority for expiry/one-time use): async protocol; default SQLite impl. Hash MXCP tokens, encrypt provider tokens. Schema versioned; WAL recommended. Persist sessions, auth codes (and optionally state) so restarts/HA don’t drop in-flight flows. Expose store/load/consume auth code with expiry (one-time); if persisting state, store/consume with expiry. `cleanup_expired_*` should return identifiers removed so caches (if added) can evict reliably.
- **FastMCP bridge (OAuthAuthorizationServerProvider)**: implements authorize/callback/token endpoints. Authorize must use MXCP callback URL; PKCE enforced; returns provider authorize URL. load/exchange access token should carry enough context (client_id, scopes, expires_at, provider token if safe) so middleware needn’t re-fetch.
- **Middleware**: uses context token from verifier; if provider token/user context is already present, avoid redundant session lookups unless needed. Fetch user info via adapter; set UserContext; enforce scopes if needed.
- **Config models**: AuthConfig, ProviderConfig, PersistenceConfig; validated early. Avoid dict `.get` on models—use attributes/model_dump.

## Security/robustness
- PKCE required for public clients; verify on code exchange.
- State and auth codes are one-time and expiring; consume on use.
- Tokens: MXCP access tokens are opaque; hash before storage. Provider tokens encrypted if key provided; fail closed on bad key.
- Callback vs client redirect URLs never conflated. MXCP callback is what IdP calls; client redirect is final hop.
- Logging: no tokens/PII; only operational info.

## Async + Pydantic v2 conventions
- Everything public-facing is async: ProviderAdapter, SessionManager, TokenStore, FastMCP bridge; avoid blocking the event loop (only wrap true sync work in run_in_executor).
- Use asyncio locks carefully: never hold them across awaits to storage; stage then persist.
- Pydantic v2: use model attributes or `model_dump(exclude_none=True)` instead of `.get` on models; config models should forbid extras; when converting to dicts, be explicit about fields.
- Validation: prefer `Model.model_validate(data)` for inbound config; make defaults and frozen/extra behavior explicit via `ConfigDict`.
- Tests for async code should use `pytest.mark.asyncio` (and `uv run pytest`).

## ProviderAdapter API (explicit)
- `provider_name: str` property.
- `build_authorize_url(redirect_uri, state, scopes, code_challenge, code_challenge_method, extra_params) -> str`.
- `exchange_code(code, redirect_uri, code_verifier) -> GrantResult`.
- `refresh_token(refresh_token, scopes) -> GrantResult`.
- `fetch_user_info(access_token) -> UserInfo`.
- `revoke_token(token, token_type_hint=None) -> bool`.
- Errors: raise `ProviderError(error, error_description, status_code)`; callers surface status appropriately.

## Test/dummy provider (required for flow tests)
- Implement a pure in-process dummy ProviderAdapter with deterministic behavior (no network):
  - `build_authorize_url` returns a fake URL embedding `state` so tests can assert it.
  - `exchange_code` accepts a known code (e.g., `TEST_CODE_OK`, optionally with a matching PKCE verifier) and returns fixed `GrantResult` (access token, optional refresh, scopes, user_id); rejects anything else to test error paths.
  - `fetch_user_info` returns a fixed `UserInfo` when the access token matches the issued one; raises ProviderError otherwise.
  - `refresh_token` can return a rotated token for refresh-path tests or raise NotImplemented if unused.
  - `revoke_token` returns True.
- Use this dummy to drive end-to-end tests without a real IdP: client hits `/authorize`, follows redirect URL, then calls MXCP callback directly with `code`+`state` (no external callback server). The dummy’s `exchange_code` returns tokens without outbound calls.
- For browser-like redirect tests, you may add a tiny fake IdP HTTP endpoint that just redirects to MXCP callback with `code`/`state`, but keep this optional.

## Concurrency
- Use a single connection + executor OR a pool; don’t mix single worker + global lock for no gain. If pooling, one connection per worker with WAL.
- Don’t hold asyncio locks across await of storage I/O; stage data then write.

## Suggested build order (start with no cache)
1) Define contracts: TokenStore API (sessions + auth codes/states), Session/SessionManager shapes, ProviderAdapter protocol, config models.
2) Implement SQLite TokenStore as the reference (no cache). Unit-test store/load/delete, cleanup/expiry, auth code/state one-time use, restart resilience, encryption on/off.
3) Implement ProviderAdapter + dummy provider (deterministic, no network). Test that known code → GrantResult/user info and PKCE/error paths behave.
4) Implement SessionManager on top of the store (no in-memory cache yet). Test create/get/delete, state/auth-code lifecycle, expiry using the SQLite store and dummy provider in flow tests.
5) Wire FastMCP bridge and middleware; run end-to-end flows with the dummy provider (avoid redundant session lookups if verifier already supplies provider token/context).
6) Only if needed, add an optional caching layer as a thin decorator over TokenStore (same API, cache-aside, store authoritative for expiry).

## Testing checklist
- Unit: SessionManager (state/auth-code lifecycle, expiry, hashing), TokenStore (store/load/delete/cleanup, encryption on/off), ProviderAdapter stubs (PKCE enforced), FastMCPAuthProvider (authorize builds correct URL; callback exchange; token exchange), Middleware (context set, failure paths).
- Flow tests: full authorize → callback → token → protected endpoint for each provider stub; PKCE happy/sad; expired state/auth code; revoked/expired token rejection; double-use of state/auth code.
- Regression for callback URL wiring (IdP calls MXCP callback, MXCP redirects to client).

## Implementation tips
- Keep imports at top; avoid in-function unless optional deps.
- Keep auth modes explicit: issuer vs verifier; disabled short-circuits.
- Make defaults explicit (token lifetimes, state TTL, auth code TTL).
- Surface clear errors to clients (400 for bad state/code, 401/403 for auth failures).
- Document public interfaces with docstrings; avoid example files elsewhere.

## Phased hardening plan

### Phase 1: Minimal safety rails before wiring
- Client registry + redirect validation (patterns) and bind auth codes to client_id + redirect_uri + PKCE.
- Enforce PKCE end-to-end (provider sees the challenge), align access-token TTL to provider `expires_in`, and handle invalid/expired provider tokens deterministically (fail fast vs fallback).
- Single-use state/auth codes with TTL; clear OAuth error semantics on bad client/redirect/code/PKCE.
- Small tests: allow/deny redirect patterns; wrong client/redirect/PKCE rejected; happy path with dummy provider.
- Default behavior: if no client registry or redirect patterns are configured, allow all redirects (backward compatible); set a registry or allowed patterns to enable enforcement.

### Phase 2: End-to-end smoke with one real provider
- Wire to server/SDK paths; run authorize → callback → token → protected call with a single provider (e.g., GitHub).
- Keep provider tokens internal; return user info via verifier path so middleware needn’t re-fetch.
- Validate issuer-mode flow under real HTTP routing and confirm TTL alignment works in practice.

### Phase 3: Full hardening and ergonomics
- Consent/CSRF/anti–confused-deputy interstitial (approve/deny memory, CSP).
- Revocation (local + upstream when available) and refresh-token rotation once refresh is added.
- Pluggable async storage with per-entry TTLs; improved error UX; optional user-info caching policy in verifier.
- Broader tests: consent paths, revocation, rotation, TTL eviction, and multi-provider coverage.
