# MXCP Authentication Redesign Plan

## Overview

This document outlines the implementation plan for overhauling MXCP's authentication system. The goals are:

- Single `AuthService` entry point for all transports
- Secure token and session storage with refresh support
- Access to upstream provider tokens for calling external APIs
- Proxy/header-trust mode for deployments behind SSO-aware reverse proxies
- Clear scope and entitlement model consumable by CEL policies and endpoint annotations
- Strict separation between SDK (reusable, well-typed) and server (config loading, FastMCP wiring)

## Design Constraints

### Async-First Architecture

The codebase uses asyncio throughout. All auth components must follow this pattern:

- **Concurrency**: Multiple requests served concurrently via asyncio event loop
- **Locks**: Use `asyncio.Lock` for coordinating concurrent access to shared state (e.g., session cache)
- **Background tasks**: Session cleanup, token refresh checks use `asyncio.create_task()` with periodic `await asyncio.sleep()`
- **Blocking I/O**: SQLite operations wrapped in `ThreadPoolExecutor` (existing pattern in `persistence.py`) but exposed as async interfaces
- **No threading for concurrency**: Thread pools only for unavoidable blocking I/O, not for request handling

### Opaque MXCP Tokens

MXCP issues opaque access tokens (`mcp_…`), not JWTs. Session state is stored server-side and looked up on each request. This keeps tokens simple and allows immediate revocation without token introspection complexity. Provider tokens (which may be JWTs or opaque depending on the IdP) are treated as opaque blobs and stored encrypted.

### Token Issuance vs. Verification Modes

`AuthService` must support two deployment modes:

- **Issuer mode** (default): MXCP acts as its own authorization server, issuing opaque tokens via `SessionManager`.
- **Verifier mode**: An external IdP (e.g., Keycloak) issues tokens; FastMCP routes provide a `token_verifier` that calls the provider adapter to validate incoming tokens (JWKS or token introspection). After verification, the same `ScopeMapper`, middleware, and `scope_requirements` pipeline runs, allowing MXCP scopes and downstream token exchange to function identically in both modes.

### Unified Scope Model

MXCP uses a single abstraction layer for authorization. Endpoints only reference MXCP scopes, never provider-specific scopes.

**Provider scopes** = What we request from IdP (Google, Keycloak, etc.)
- Split into `required_scopes` (fail auth if not granted) and `optional_scopes` (graceful degradation)
- Stored as `provider_scopes_granted` in session after auth

**MXCP scopes** = Internal authorization vocabulary used by endpoints and policies
- Derived from provider scopes, groups, roles, and other claims via mapping
- Endpoints only ever reference these (governance, portability)

**Flow**:
1. Auth requests the union of `required_scopes + optional_scopes` in the authorize URL
2. Provider grants a subset; we inspect token response / userinfo to see what was actually granted
3. If any `required_scopes` missing → fail authentication
4. `ScopeMapper` translates granted provider scopes + claims → MXCP scopes
5. User's `mxcp_scopes` only includes what they actually have
6. Endpoint requiring `calendar.read` blocked if user didn't grant the provider scope that maps to it

**Provider-agnostic mapping**: Providers differ in how we fetch claims (JWT tokens, opaque tokens with userinfo endpoint, etc.), but once the adapter normalizes claims into `UserContextModel`, a single `ScopeMapper` handles all providers. Proxy mode shares the same mapper.

**Config example**:
```yaml
auth:
  google:
    required_scopes: "openid email"
    optional_scopes: "calendar.readonly drive.readonly"
    claim_mappings:
      scopes:
        "calendar.readonly": [calendar.read]
        "drive.readonly": [files.read]
      groups:
        "admins@company.com": [admin]
      roles:
        "keycloak_realm:billing-manager": [billing.manage]
        "keycloak_resource:mxcp:report-viewer": [reports.view]
```
`claim_mappings` supports multiple claim sources. For example, Keycloak emits realm roles under `realm_access.roles` and client roles under `resource_access.<client>.roles`. When those claims arrive in `UserContextModel.raw_profile`, the mapper can reference them via the `roles` section to translate each emitted role string into the MXCP scopes used by tools.

**Endpoint example** (only MXCP scopes, at definition level):
```yaml
tool:
  name: list-calendar-events
  scopes: [calendar.read]
```

## Current Problems

### Tangled Architecture
- `mcp.py` wires OAuth callbacks per provider and reaches into handler internals
- `GeneralOAuthAuthorizationServer` handles both IdP flow orchestration and token storage
- Middleware accesses private `_token_mapping` to rehydrate user context
- Every layer knows about every other layer

### Missing Features
- No refresh token support; provider tokens expire without renewal
- No proxy/header mode for SSO-fronted deployments
- Scope enforcement is decorative; `required_scopes` are advertised but not checked post-handshake
- Provider tokens stored in plaintext SQLite with no encryption

### Unclear Scope Model
- Config defines `required_scopes` but nothing enforces them per endpoint
- No mechanism to map IdP claims (scopes, groups) to MXCP entitlements
- `UserContextModel` lacks `mxcp_scopes` field for policy consumption

---

## Current SDK Auth Inventory

The following components already exist in `mxcp.sdk.auth` and will be refactored (not rewritten from scratch):

### Existing Modules

| Module | Current Role | Target Refactoring |
|--------|--------------|-------------------|
| `base.py` | `ExternalOAuthHandler` protocol + `GeneralOAuthAuthorizationServer` | Split into `ProviderAdapter` protocol and extract session logic to `SessionManager` |
| `middleware.py` | `AuthenticationMiddleware` with `require_auth` decorator | Keep and extend; remove private field access to `_token_mapping` |
| `persistence.py` | `SQLiteAuthPersistence` + dataclasses for tokens/clients/codes | Evolve into `TokenStore` interface; add encryption to SQLite backend |
| `context.py` | Thread-local `UserContext` management (`get_user_context`, `set_user_context`) | Keep as-is; well-isolated |
| `models.py` | `UserContextModel`, provider configs, `StateMetaModel`, etc. | Extend `UserContextModel` with `mxcp_scopes`, `provider_scopes_granted`; add `required_scopes`/`optional_scopes` to provider configs; add `ClaimMappingConfigModel` |
| `url_utils.py` | `URLBuilder` for callback URL construction | Keep as-is |

### Existing Providers (`mxcp.sdk.auth.providers/`)

| Provider | Current State | Target Refactoring |
|----------|---------------|-------------------|
| `google.py` | `GoogleOAuthHandler` with full callback handling + state storage | Thin to pure IdP client; move state to `SessionManager` |
| `keycloak.py` | `KeycloakOAuthHandler` | Same pattern |
| `github.py` | `GitHubOAuthHandler` | Same pattern |
| `atlassian.py` | `AtlassianOAuthHandler` | Same pattern |
| `salesforce.py` | `SalesforceOAuthHandler` | Same pattern |

### Server-Side Auth Code (`mxcp.server`)

| Location | Current Role | Target Refactoring |
|----------|--------------|-------------------|
| `mcp.py` (`_initialize_oauth`, `_register_oauth_routes`) | Wires handler + server + middleware; registers per-provider callbacks | Delegate to `AuthService.register_routes()`; single callback path |
| `core/auth/helpers.py` | `create_oauth_handler`, `translate_auth_config` | Keep translation logic; `AuthService` factory replaces `create_oauth_handler` |

### What Gets Created New

| Component | Purpose |
|-----------|---------|
| `AuthService` | Single entry point wrapping existing pieces |
| `SessionManager` | Extracted from `GeneralOAuthAuthorizationServer`; owns session lifecycle |
| `ScopeMapper` | New; translates IdP claims to MXCP scopes |
| `ProxyAuthAdapter` | New; header-trust mode |
| Alternative `TokenStore` backends | New; Vault, AWS Secrets Manager |

---

## Target Architecture

### SDK Layer (`mxcp.sdk.auth`)

The SDK provides reusable, well-typed components independent of server configuration:

- **AuthService**: Main entry point; owns provider adapter, session manager, scope mapper
- **ProviderAdapter**: Protocol for IdP integrations (Google, Keycloak, GitHub, proxy, etc.)
- **SessionManager**: Issues and validates MXCP tokens; manages session lifecycle
- **TokenStore**: Persistence interface for sessions and tokens; each backend handles its own security
- **ScopeMapper**: Translates IdP claims to MXCP entitlements
- **AuthMiddleware**: Request authentication and scope enforcement

### Server Layer (`mxcp.server`)

The server translates config, instantiates SDK components, and wires FastMCP:

- Loads `UserAuthConfigModel` from site/user config
- Converts to SDK models (`AuthConfigModel`, `HttpTransportConfigModel`)
- Instantiates `AuthService` and registers routes with FastMCP
- Passes middleware to endpoint wrappers
- Configures persistence backend based on deployment config

---

## Implementation Phases

### Phase 1: AuthService Skeleton

**Goal**: Introduce `AuthService` abstraction wrapping existing code without changing behavior.

**Tasks**:
1. Create `mxcp.sdk.auth.service` module with `AuthService` class
2. Define `from_config(auth_config, transport_config)` factory accepting only SDK models
3. Internally instantiate existing `GeneralOAuthAuthorizationServer` and provider handlers
4. Add `register_routes(fastmcp)` method that installs existing callback and well-known endpoints
5. Add `build_middleware()` method returning existing `AuthenticationMiddleware`
6. Refactor `RAWMCP` to instantiate `AuthService` instead of managing handler/server/middleware directly
7. Move `create_oauth_handler` logic into `AuthService`; keep `translate_auth_config` in server layer
8. Support both issuer mode and verifier mode:
   - Issuer mode (current behavior) uses `SessionManager` and FastMCP auth server hooks
   - Verifier mode registers FastMCP `token_verifier` that validates external IdP/JWT tokens via provider adapter and then runs ScopeMapper/middleware
9. Add comprehensive tests for service instantiation, route registration, and token verifier wiring

**Outcome**: Single entry point for auth; existing internals unchanged but now encapsulated.

---

### Phase 2: Session and Token Infrastructure

**Goal**: Extract session management from `GeneralOAuthAuthorizationServer`; secure token storage.

**Tasks**:
1. Create `mxcp.sdk.auth.sessions` package with:
   - `SessionManager` class extracted from `GeneralOAuthAuthorizationServer` token/code handling
   - `Session` dataclass holding session ID, user context, provider grants, expiry
2. Refactor `mxcp.sdk.auth.persistence` into `mxcp.sdk.auth.storage`:
   - Rename `SQLiteAuthPersistence` to `SqliteTokenStore`
   - Define `TokenStore` protocol from existing methods (already has CRUD operations)
   - Add encryption: hash MXCP tokens (one-way), encrypt provider tokens with Fernet
   - Encryption key resolved via existing config resolvers (supports `vault://`, `op://`, `${ENV}`)
3. Update existing `AuthenticationMiddleware` to:
   - Use `SessionManager` instead of accessing `_token_mapping` directly
   - Hydrate `UserContext` from session
4. Update `GeneralOAuthAuthorizationServer` to delegate storage to `SessionManager`
5. Add async background task for expired session/token cleanup (periodic `asyncio.create_task`)
6. Migrate existing SQLite schema; provide data migration tooling

**Outcome**: Session logic extracted; encrypted storage; no private field access in middleware.

---

### Phase 3: Provider Adapter Refactor

**Goal**: Thin existing provider handlers into pure IdP clients.

**Tasks**:
1. Define `ProviderAdapter` protocol evolving from existing `ExternalOAuthHandler`:
   - Keep `build_authorize_url` (rename from `get_authorize_url`)
   - Keep `exchange_code` but return new `ExternalGrantResult`
   - Add `refresh(grant)` returning `ExternalGrantResult`
   - Keep `fetch_user_context` (rename from `get_user_context`)
2. Define `ExternalGrantResult` dataclass (extends existing `ExternalUserInfoModel`):
   - Access token, refresh token, expiry timestamp
   - Raw profile data, provider scopes
3. Refactor existing providers (Google, Keycloak, GitHub, Atlassian, Salesforce):
   - Remove `on_callback` method (move to `AuthService`)
   - Remove `_state_store` (move to `SessionManager`)
   - Remove `callback_path` property (unified in `AuthService`)
   - Keep IdP communication logic (token exchange, user info fetch)
4. Update `AuthService` to:
   - Own single callback route (e.g., `/auth/oauth/callback`)
   - Dispatch to appropriate adapter based on session state
   - Store grants via `SessionManager`
5. Deprecate `GeneralOAuthAuthorizationServer` (functionality split into `AuthService` + `SessionManager`)
6. Add tests for each provider adapter in isolation

**Outcome**: Providers are pure IdP clients; all state and persistence handled by service layer.

---

### Phase 4: Refresh Token Support

**Goal**: Full token refresh flow for both MXCP and provider tokens.

**Tasks**:
1. Extend `ExternalGrantResult` to include provider refresh token
2. Update `SessionManager` to:
   - Issue MXCP refresh tokens alongside access tokens
   - Validate refresh tokens and check expiry
   - Rotate tokens on refresh (issue new access token, optionally new refresh token)
3. Add `/auth/token` endpoint supporting:
   - `authorization_code` grant (existing flow)
   - `refresh_token` grant (new)
4. When MXCP refresh token is used:
   - `SessionManager` loads session
   - If provider token expired, call `adapter.refresh()`
   - Update stored provider tokens
   - Issue new MXCP tokens
5. Expose SDK helper for endpoints to obtain fresh provider token:
   - `get_provider_token(user_context)` checks expiry and refreshes if needed
   - Available via execution context during endpoint execution
6. Add configurable token lifetimes (access, refresh, idle timeout)
7. Add tests for complete refresh flow including provider token expiry
8. Add provider-specific token exchange helpers (e.g., Keycloak → Google):
   - Support OAuth 2.0 Token Exchange / broker APIs
   - Cache downstream tokens per session with expiry metadata
   - Expose via helper so tools can request tokens by alias (`auth_context.get_token("google")`)
   - Ensure helpers work in both issuer mode (MXCP tokens) and verifier mode (external IdP tokens)

**Outcome**: Long-lived sessions; provider tokens stay fresh; endpoints can call external APIs.

---

### Phase 5: Scope and Mapping Layer

**Goal**: Implement unified scope model with required/optional provider scopes mapped to MXCP scopes.

**Tasks**:
1. Update provider config models to support:
   - `required_scopes: str` – fail auth if not granted
   - `optional_scopes: str` – request but allow partial grant
   - `claim_mappings` – provider scopes/groups/claims → MXCP scopes
2. Extend existing `UserContextModel` (in `mxcp.sdk.auth.models`) with:
   - `mxcp_scopes: set[str]` for internal authorization
   - `provider_scopes_granted: set[str]` for tracking what IdP actually granted
3. Update provider adapters to:
   - Request union of required + optional scopes during authorization
   - Fetch granted scopes via provider-specific means (token response, userinfo endpoint, JWT claims)
   - Normalize into `UserContextModel.provider_scopes_granted`
   - Fail auth if required scopes missing; continue if optional missing
4. Create `ScopeMapper` class (provider-agnostic):
   - Reads `claim_mappings` config
   - Given normalized `UserContextModel` → computes MXCP scopes
   - Single implementation shared by all providers and proxy mode
5. Update `AuthService` to run `ScopeMapper` after successful auth
6. Update middleware to:
   - Check global `required_scopes` (MXCP scopes, not provider scopes)
   - Accept endpoint-specific MXCP scope requirements
   - Reject requests where user lacks required MXCP scopes
7. Add `scope_requirements` config mapping MXCP scopes → downstream token requirements:
   - Example:
     ```yaml
     auth:
       scope_requirements:
         calendar.read:
           provider: keycloak
           audience: google
           resource: "https://www.googleapis.com/auth/calendar.readonly"
     ```
   - AuthService uses this to know which provider tokens/token exchanges to perform automatically (works for both MXCP-issued tokens and external tokens validated via verifier mode)
8. Add tests for: partial grant scenarios, mapping combinations, required vs optional, scope requirements

**Outcome**: Endpoints only reference MXCP scopes; missing provider scopes automatically block corresponding endpoints.

---

### Phase 6: Endpoint and Policy Integration

**Goal**: Per-endpoint MXCP scope requirements; CEL integration.

**Tasks**:
1. Extend endpoint YAML schema to accept `scopes` field at definition level:
   - `tool.scopes`, `prompt.scopes`, `resource.scopes` (never provider-specific)
2. Update existing `EndpointLoader` to index all referenced MXCP scopes across endpoints
3. Update execution wrapper to:
   - Read endpoint scope requirements from definition
   - Look up scope requirements → ensure necessary provider tokens are fetched/exchanged before execution
   - Inject resolved tokens into execution context (accessible via helper) so tool code does not implement auth logic
   - Pass requirements to middleware for enforcement
   - Block execution if user lacks required MXCP scopes or framework cannot obtain required provider token
4. Extend CEL user context object (in `PolicyEnforcer._user_context_to_dict`):
   - Add `user.mxcp_scopes` list for CEL expressions like `user.mxcp_scopes.exists(s, s == "admin")`
   - Add `user.provider_scopes_granted` for advanced policies needing raw IdP info
5. Update policy enforcer to include new fields in CEL context
6. Optional: Add validation warning for scopes referenced in endpoints but not in any mapping
7. Add tests for endpoint-level scope enforcement and CEL integration

**Outcome**: Endpoints only reference MXCP scopes (portable, governed); policies can reference them.

---

### Phase 7: Proxy and Header Mode

**Goal**: Support deployments behind SSO-aware reverse proxies.

**Tasks**:
1. Define `ProxyAuthConfigModel` in SDK with:
   - Header names for user ID, username, email
   - Header for groups/roles (raw claims from proxy)
   - Optional header for pre-computed MXCP scopes (if proxy does mapping)
   - Optional upstream token header for passthrough
   - Signature validation settings (header name, secret env, algorithm)
   - Optional mTLS requirement flag
2. Implement `ProxyAuthAdapter`:
   - Reads configured headers from request
   - Validates signature (HMAC) or mTLS if configured
   - Constructs `UserContextModel` from headers
   - Extracts upstream token if present
3. Integrate with `ScopeMapper` (two modes):
   - **Raw claims mode**: Proxy sends groups/roles headers → `ScopeMapper` computes MXCP scopes
   - **Pre-mapped mode**: Proxy sends MXCP scopes header directly → trusted as-is
4. Update `AuthService` to support proxy mode:
   - No OAuth routes registered in pure proxy mode
   - Middleware extracts user context from headers via adapter
   - Optionally support hybrid mode (OAuth + proxy fallback)
5. Update config schema to support `provider: proxy`
6. Add tests for proxy authentication including signature validation failures
7. Document expected header format and provide sample nginx/Envoy configuration

**Outcome**: MXCP works behind SSO proxies; same middleware interface regardless of mode.

---

### Phase 8: Persistence Hardening

**Goal**: Production-grade secure storage with alternative backends.

**Tasks**:
1. Implement additional `TokenStore` backends alongside existing `SqliteTokenStore`:
   - `VaultTokenStore`: Stores tokens directly in HashiCorp Vault (Vault handles encryption)
   - `AwsSecretsManagerTokenStore`: Stores in AWS Secrets Manager (stretch goal)
2. For `SqliteTokenStore`, add key rotation support:
   - Config option to specify new encryption key
   - Automatic re-encryption of stored tokens on startup when key changes
3. Add audit events for:
   - Session creation and revocation
   - Token refresh attempts
   - Authentication failures
4. Add tests for each backend

**Outcome**: Multiple storage backends; audit trail for auth events.

---

### Phase 9: Admin API Extensions

**Goal**: Operational visibility into auth state via existing admin REST API.

**Tasks**:
1. Add new endpoints to existing admin API (Unix socket):
   - `GET /auth/sessions` - List active sessions (count, providers, expiry)
   - `DELETE /auth/sessions/{id}` - Revoke session by ID
   - `GET /auth/config` - View configured scopes and mappings
   - `POST /auth/cleanup` - Purge expired sessions and tokens
2. Extend existing `GET /status` to include auth subsystem health

**Outcome**: Operators can inspect and manage auth state via admin API.

---

### Phase 10: Documentation and Examples

**Goal**: Comprehensive docs for all auth scenarios.

**Tasks**:
1. Update `docs/guides/authentication.md` with:
   - New config schema (claim mappings, proxy provider, secret storage)
   - Endpoint YAML scope annotations
   - How to access provider tokens in endpoints
   - Proxy mode setup guide
2. Create example site configurations demonstrating:
   - Google OAuth with calendar scope passthrough
   - Keycloak with group-to-scope mapping
   - Proxy mode with nginx
3. Document admin API auth endpoints (session management, cleanup)
4. Add migration guide for existing deployments
5. Add troubleshooting section for common issues

**Outcome**: Builders can configure any auth scenario from docs.

---

## SDK vs Server Boundary

### SDK (`mxcp.sdk.auth`)

- All reusable auth components
- Typed config models (`AuthConfigModel`, `HttpTransportConfigModel`, etc.)
- No dependencies on server config models (`SiteConfigModel`, `UserConfigModel`)
- `AuthService.from_config()` accepts only SDK models
- Testable in isolation

### Server (`mxcp.server`)

- Loads config from YAML files
- Translates `UserAuthConfigModel` to SDK's `AuthConfigModel`
- Instantiates `AuthService` with translated config
- Registers routes with FastMCP
- Wires middleware into endpoint execution
- Configures persistence backend and paths

---

## Success Criteria

- Single `AuthService` entry point replaces current tangled architecture
- Provider tokens accessible and auto-refreshed for endpoint code
- Proxy mode working with signature validation
- Per-endpoint scope enforcement operational
- Provider tokens secured at rest (encrypted in SQLite, or delegated to Vault/cloud backends)
- Migration path documented and tested
- No regressions in existing OAuth flows

---

## Supported Authentication Modes

| Mode | Description | Typical Use Cases |
|------|-------------|-------------------|
| **Issuer Mode (default)** | MXCP issues opaque tokens via `SessionManager`, handles refresh, persistence, and downstream token exchange. | Standalone MXCP deployments needing local sessions. |
| **Verifier Mode (external IdP tokens)** | External IdP (e.g., Keycloak) issues tokens; FastMCP `token_verifier` validates them. Still runs ScopeMapper, `scope_requirements`, and downstream token exchange. | Organizations standardizing on IdP-issued JWTs; MXCP acts as resource server. |
| **Proxy/Header Mode** | Reverse proxy performs auth; MXCP trusts signed headers for user info, scopes, or roles. Supports both raw claims → mapping and pre-mapped MXCP scopes. | Nginx/Envoy SSO frontends, corporate perimeter authentication. |
| **Scope Requirements (downstream token exchange)** | Optional layer that maps MXCP scopes to downstream provider token requirements; framework performs OAuth 2.0 Token Exchange automatically (works in all auth modes). | Keycloak brokering Google APIs; Azure broker issuing Graph tokens; any chained IdP scenario. |
| **Auth Disabled / Custom Tool Logic** | Authentication disabled via config or specific tool. Tool code can implement bespoke auth (e.g., custom headers to upstream). Framework still allows manual context access. | Internal-only deployments, prototype endpoints, or special integrations requiring custom auth per tool. |

All modes share the same higher-level infrastructure:
- `ScopeMapper` translating provider claims (scopes, groups, roles) to MXCP scopes
- Endpoint-level `scopes` declarations enforced via middleware
- Optional `scope_requirements` driving downstream token exchange
- Execution context helpers (`auth_context.get_token()`) for tool code

