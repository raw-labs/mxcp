# Rethinking mxcp authentication implementation
_Exported on 12/5/2025 at 11:17:41 GMT+1 from Cursor (2.1.48)_

---

**User**

Can you help me rethink about our auth implementation in mxcp?



There are a few concerns:

1) The auth SDK handles 'redirects' a bit weird

2) The notion of 'mxcp scopes' is not clear; or even why it's needed

3) we don't implement refreshing tokens

4) we don't support any proxy mode

5) the way we store tokens is rather insecure and not under any api (sqlite db?)

6) i think our generic ouath class does too much.



First, on weird redirects and oauth (points 1 and 6):



In our implementation, mxcp registers an OAuth callback which URL is advertised and eventually Google triggers the execution of that callback when it has generated its access token. In the code, the callback is technically defined in mcp.py, as a function doing nothing but calling on_callback, which is entirely defined in the provider's code (google.py, keycloak.py). Also the HTTP path is a property of the provider's code.

  # Use custom_route to register the callback

        @self.mcp.custom_route(callback_path, methods=["GET"])  # type: ignore[misc]

        async def oauth_callback(request: Any) -> Any:

            if self.oauth_handler is None or self.oauth_server is None:

                raise RuntimeError("OAuth not configured")

            return await self.oauth_handler.on_callback(request, self.oauth_server)

 In mcp.py:

self.oauth_handler (the provider specific object) is created using a helper function that has the if/then/else to choose between google or github. That permits to access its on_callback function to call it within the actual callback

But authentication in FastMCP needs a self.oauth_server, which is constructed from self.oauth_handler (meaning oauth_handler is a parameter of an oauth_server __init__)

the callback (see above) calls self.oauth_handler.on_callback(..., self.oauth_server). Here self.oauth_server is a parameter of that oauth_handler method).

on the side of that, auth_middleware (not needed by FastMCP, but we use it to protect tools using authentication), is built by passing both oauth_handler and oauth_server as arguments.

So I found suspicious the fact that pretty much each object is passed as a parameter of the other and that mcp.py needs to access all levels (especially the callback in the provider). And when I was trying to implement refresh token, the tangling become more annoying, I can try to recover why.

 

If the "oauth_server" object (the one passed to FastMCP, so we have to stick to it) would be the one owning the callback, one could instead expect the provider to remain hidden inside and only expose a "token_decode" method (called by the common callback):

mcp.py wouldn't need to peek at the provider. I'm thinking it wouldn't even need to allocate it (?) Instead of allocating the oauth_provider and pass it to the constructor of oauth_server, it'd pass the config. The server would allocate it privately.

auth_middleware (I haven't thought much what its role is here) could probably be contructed from the oauth_server only, and oauth_server would be the one calling the provider. But I even sometime wonder why it's separate from oauth_server, since it's the one having to trigger the google token renewal,

mcp.py would register a HTTP callback that calls the shared oauth_server's on_callback. That on_callback would call its internal provider's "decode" to extract auth info, and would handle the persistency, it would know how to map an MCP token to a provider token. Provider wouldn't be responsible to call persistency through the oauth_server passed as argument (the most weird part),

also I believe the callback path could be the same regardless of the external provider no? We're pretending to be the authorization provider, why should we have a callback that says "google".



(This all makes me think the generic oath classes does too much)



2) notion of scopes 



I think we have some mxcp:... scope. That's because we are also an authorization server? But should we? And which ones? Configurable? Why?  I mean, people build endpoints using mxcp. I guess they could configure the yaml files for the endpoints and add rules - in yaml or CEL policy enforcement - which the scopes allowed. But then we must request these scopes? I'm very confused here. Relates Perhaps to proxies - below.



3) refresh tokens



we don't have it at all. need some generic engine and great auth SDK for that as well



4) proxies



I think we would need to run in proxy mode where there's an nginx in the front doing oauth, and resolving that to headers, which we then receive. So we'd run auth in proxy mode. e.g this is silly and wrong but like this:

# Hypothetical config



auth:

  provider: proxy  # Trust headers from reverse proxy

  proxy:

    user_id_header: "X-User-ID"

    username_header: "X-User-Name"

    email_header: "X-User-Email"

    token_header: "X-Access-Token"  # For passthrough to upstream APIs



smtg like this? not correct. we need to build - and expand?!-  our 'user context'  right, to make sure even CEL sees it. (And where are the scopes?)



finally, 5) the way we store tokens is rather insecure and not under any api (sqlite db?)

well, yeah. could use an sdk.



LOTS TO THINK ABOUT

---

**Cursor**

## Auth Rethink

### Where the current stack falls down
- **Callback ownership** – `mcp.py` wires routes per provider and reaches into the handler just to bounce the request back, so every layer knows about every other layer.  
```1968:1976:src/mxcp/server/interfaces/server/mcp.py
        @self.mcp.custom_route(callback_path, methods=["GET"])
        async def oauth_callback(request: Any) -> Any:
            if self.oauth_handler is None or self.oauth_server is None:
                raise RuntimeError("OAuth not configured")
            return await self.oauth_handler.on_callback(request, self.oauth_server)
```
- **“MXCP scopes” are decorative** – we read `required_scopes` from config, surface them through FastMCP, and expose them in `.well-known`, but nothing enforces them afterward.  
```481:497:src/mxcp/server/interfaces/server/mcp.py
            auth_authorization = auth_config.authorization
            required_scopes = auth_authorization.required_scopes if auth_authorization else []
            ...
            self.auth_settings = AuthSettings(
                issuer_url=...,
                client_registration_options=...,
                required_scopes=required_scopes if required_scopes else None,
            )
```
- **Generic OAuth server tightly couples everything** – `GeneralOAuthAuthorizationServer` both drives the IdP flow and stores tokens, while the middleware pokes at its private `_token_mapping` to rehydrate user context.  
```413:509:src/mxcp/sdk/auth/base.py
        self._tokens[token] = access_token
        if external_token:
            self._token_mapping[token] = external_token
        if self.persistence:
            await self.persistence.store_token(...)
```
```103:121:src/mxcp/sdk/auth/middleware.py
                external_token = self.oauth_server._token_mapping.get(access_token.token)
                if not external_token:
                    logger.warning("No external token mapping found")
                    return None
                user_context = await self.oauth_handler.get_user_context(external_token)
```
- **Refresh tokens not implemented** – grant handlers explicitly return `None`/`NotImplemented`, so we can’t renew provider tokens or issue long-lived MXCP tokens.  
```684:690:src/mxcp/sdk/auth/base.py
    async def load_refresh_token(...):
        return None
    async def exchange_refresh_token(...):
        raise NotImplementedError
```
- **Persistence is just plaintext SQLite in `~/.mxcp/oauth.db` with direct SQL and no envelope encryption or access API.**  
```260:288:src/mxcp/sdk/auth/persistence.py
                INSERT OR REPLACE INTO access_tokens
                (token, client_id, external_token, scopes, expires_at, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
```
- **No proxy / header-trust mode** – the SDK only understands “talk to IdP yourself”, leaving no path for deployments behind SSO-aware reverse proxies.

### Proposed architecture

- **Collapse everything behind an `AuthService` interface.** `mcp.py` should only do:
  ```python
  self.auth = AuthService.from_config(profile.auth, transport=http_config)
  self.auth.register_fastmcp(self.mcp)
  self.auth_middleware = self.auth.build_middleware()
  ```
  Internally, `AuthService` owns the provider adapter, callback path, persistence, CEL integration, etc. FastMCP only ever sees a single callback like `/auth/oauth/callback`.

- **Provider adapters become thin.** Define a `BaseProviderAdapter` that exposes:
  - `build_authorize_url(request: AuthorizationRequest) -> str`
  - `exchange_code(code, state) -> ExternalGrantResult` (access token, refresh token, expiry, raw profile)
  - `refresh(grant: RefreshGrant) -> ExternalGrantResult`
  - `fetch_user_context(token) -> UserContextModel`
  The AuthService instantiates the adapter from config; providers never register routes or touch persistence directly.

- **Session + token store split.**
  - `TokenStore` (pluggable backends) stores hashed MXCP access tokens, refresh tokens, and encrypted provider credentials. Default backend can remain SQLite but must encrypt blobs (Fernet/Keychain) and expose CRUD via the store instead of raw SQL.
  - `SessionCache` (in-memory) tracks active sessions for quick lookups.
  - `TokenCodec` issues MXCP tokens (e.g., signed JWT with `session_id` only). Middleware decodes the JWT, resolves the session via `TokenStore`, and never reads `_token_mapping` directly.

- **Refresh-token pipeline.**
  - Extend `ExternalGrantResult` to include `refresh_token` and provider expiry.
  - Persist refresh tokens encrypted.
  - Expose RFC-compliant `/auth/token` endpoint that handles `refresh_token` grant.
  - When a client refreshes, AuthService calls `adapter.refresh()`, rotates provider tokens, and updates the session.
  - Introduce background janitor to prune expired refresh tokens.

- **Authorization scope model.**
  - Distinguish between `provider_scopes` (what we request from Google, etc.) and `mxcp_scopes` (internal entitlements). Add `mxcp_scopes: set[str]` to `UserContextModel`.
  - Populate `mxcp_scopes` via config (e.g., map IdP groups to scopes or accept them from proxy headers).
  - Have `AuthenticationMiddleware` attach the scopes to `UserContext`, and let CEL/policy modules check them (`user_context.mxcp_scopes.contains("admin")`).
  - FastMCP `AuthSettings` should advertise only the MXCP scopes we actually enforce.

- **Proxy / header-trust mode.**
  - Add `provider: proxy` configuration:
    ```yaml
    auth:
      provider: proxy
      proxy:
        user_id_header: X-User-ID
        username_header: X-User-Name
        email_header: X-User-Email
        scope_header: X-MXCP-Scopes
        token_header: X-Access-Token   # optional passthrough
        signature:
          header: X-Auth-Signature
          secret_env: MXCP_PROXY_SHARED_SECRET
    ```
  - Implement `ProxyAuthHandler` that validates the signature (HMAC or mTLS), builds `UserContext`, and optionally stores/passes through the upstream token.
  - `AuthService` still exposes the same middleware interface, so endpoints don’t care whether we authenticated ourselves or trusted headers.

- **Re-scope responsibilities.**
  - `GeneralOAuthAuthorizationServer` should be broken into `AuthorizationRouter` (owns routes + FastMCP integration) and `OAuthSessionManager` (stores sessions/tokens). Providers only talk to `OAuthSessionManager`.
  - `AuthenticationMiddleware` should depend on `AuthService.decode_token` and never see provider adapters or persistence details. That also makes it easier to plug in proxy mode or future SSO types.

- **Security upgrades.**
  - Hash MXCP access tokens before storing, just like API keys.
  - Encrypt provider tokens/refresh tokens at rest. Expose a `SecretProvider` abstraction so teams can swap in Keychain, HashiCorp Vault, etc.
  - Add configurable token lifetimes + idle timeout enforcement in `SessionManager`.

### Practical next steps
1. **Introduce `AuthService` skeleton** (no behavior change) and refactor `mcp.py` to call it; move callback registration inside the service and collapse to a single `/auth/oauth/callback`.
2. **Extract `OAuthSessionManager` and `TokenStore`**, migrate existing SQLite logic into it, and update middleware to use `AuthService.decode_token`.
3. **Extend provider adapters + persistence schema** to record refresh tokens and provider expirations, then implement `/auth/token` refresh flow end-to-end.
4. **Add proxy handler + config**, plumbing scope headers into `UserContext`.
5. **Rework `UserContextModel` / CEL integration** to carry `mxcp_scopes` and enforce them consistently.

Once these pieces are in place we can iterate on niceties (per-provider scope presets, richer audit events, tests) without fighting the current tangle. Let me know which slice you want to tackle first and I can help break it into implementation tickets.

```python
        @self.mcp.custom_route(callback_path, methods=["GET"])
        async def oauth_callback(request: Any) -> Any:
            if self.oauth_handler is None or self.oauth_server is None:
                raise RuntimeError("OAuth not configured")
            return await self.oauth_handler.on_callback(request, self.oauth_server)
```

```python
            auth_authorization = auth_config.authorization
            required_scopes = auth_authorization.required_scopes if auth_authorization else []
            ...
            self.auth_settings = AuthSettings(
                issuer_url=...,
                client_registration_options=...,
                required_scopes=required_scopes if required_scopes else None,
            )
```

```python
        self._tokens[token] = access_token
        if external_token:
            self._token_mapping[token] = external_token
        if self.persistence:
            await self.persistence.store_token(...)
```

```python
                external_token = self.oauth_server._token_mapping.get(access_token.token)
                if not external_token:
                    logger.warning("No external token mapping found")
                    return None
                user_context = await self.oauth_handler.get_user_context(external_token)
```

```python
    async def load_refresh_token(...):
        return None
    async def exchange_refresh_token(...):
        raise NotImplementedError
```

```python
                INSERT OR REPLACE INTO access_tokens
                (token, client_id, external_token, scopes, expires_at, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
```

```python
  self.auth = AuthService.from_config(profile.auth, transport=http_config)
  self.auth.register_fastmcp(self.mcp)
  self.auth_middleware = self.auth.build_middleware()
```

```yaml
    auth:
      provider: proxy
      proxy:
        user_id_header: X-User-ID
        username_header: X-User-Name
        email_header: X-User-Email
        scope_header: X-MXCP-Scopes
        token_header: X-Access-Token   # optional passthrough
        signature:
          header: X-Auth-Signature
          secret_env: MXCP_PROXY_SHARED_SECRET
```

---

**User**

where are "mxcp scopes" defined? why have them? per endpoint or server? (thought fastmcp only supports for whole server, but we could support more fine-grained). But why have them? a central location in our config defining them? is that even normal? and in passthrough/proxy mode we just could use whatever the user happens to have in their idp. I'm confused why have them why need them. Seems super complex mapping e.g. mapping idp stuff to own scopes? Is that normal? mandatory?

are u considering the split SDK vs non-SDK? 'cause lots of this oauth stuff would ideally be mxcp.sdk, well typed and mostly independent to rest of code.

BTw ,we need acess to upstream token (e.g. google) so that we can reach google services.

expand.

maybe write a complete markdown with the entire proposal

---

**Cursor**

## Auth Proposal

### MXCP Scopes Today

- Defined in user config under `profiles.<name>.auth.authorization.required_scopes` and surfaced via Pydantic’s `UserAuthorizationConfigModel`.  
```304:377:src/mxcp/server/core/config/models.py
class UserAuthorizationConfigModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    required_scopes: list[str] = Field(default_factory=list)
...
class UserAuthConfigModel(BaseModel):
    ...
    authorization: UserAuthorizationConfigModel | None = None
```
- `RAWMCP` simply forwards that list when wiring FastMCP (auth applies to the whole server run).  
```481:497:src/mxcp/server/interfaces/server/mcp.py
auth_authorization = auth_config.authorization
required_scopes = auth_authorization.required_scopes if auth_authorization else []
...
self.auth_settings = AuthSettings(..., required_scopes=required_scopes or None)
```
- We also echo them in the well-known metadata endpoint, but never re-check them after the OAuth handshake.

### Why Have MXCP Scopes?

| Goal | Reality | Recommendation |
| --- | --- | --- |
| Identify coarse-grained entitlements independent of IdP naming | Config-only list that isn’t enforced | Either enforce them (map IdP claims → internal scopes and check during request) or remove them to avoid false sense of security |
| Allow downstream CEL/policy rules to read “mxcp scopes” | Not reachable; `UserContextModel` lacks `scopes` | Add `mxcp_scopes` to user context when enforcement matters |
| Advertise scopes to FastMCP clients | Works (single global scope set) | Keep for compatibility only if we truly need MCP clients to pre-negotiate scopes |

Having project-defined scopes is normal when you want stability even if the IdP’s taxonomy changes. It becomes complex only if we insist on building our own abstraction yet never use it. Possible strategies:

1. **Global-required-only (minimal)** – drop the concept entirely and rely on IdP scopes/claims or proxy headers. Simplest for proxy/passthrough deployments.
2. **Server-wide entitlement list** – keep `required_scopes` but actually enforce them during middleware checks by mapping IdP scopes/groups (or proxy headers) to MXCP scopes. Works fine when FastMCP only supports server-level scopes.
3. **Endpoint-level policy** – let CEL or YAML policy tell what’s needed per endpoint/tool. We don’t need FastMCP scopes for that; just ensure `UserContext` has either raw IdP claims or resolved MXCP scopes.

Given FastMCP currently accepts only server-level scopes, I’d lean toward Option 2 or removing them until we plumb real enforcement.

### Mapping IdP Claims → MXCP Scopes

- Not mandatory, but common: define a mapping block (`group -> mxcp scope`) so all providers feed into the same authorization vocabulary.
- For proxy mode, we trust headers (optionally signed). Whatever scopes/roles the proxy asserts become the `mxcp_scopes`.
- Store both `provider_scopes` (what we asked Google for) and `mxcp_scopes` (internal). CEL policies read the latter.

### Access to Upstream Tokens

- `UserContextModel` already has `external_token` but we don’t persist/refresh it properly.
- Requirements:
  - Persist provider refresh/access tokens securely so backend code can call Google APIs on behalf of the user.
  - Provide helper APIs in `mxcp.sdk` to fetch an up-to-date provider token (refresh as needed) inside endpoint execution.
  - In proxy mode, allow passthrough header (`X-Access-Token`) or opaque session secret the proxy can redeem.

### SDK vs Server Split

Most of the auth logic should live under `mxcp.sdk.auth` so plugin authors and other runtimes can reuse it:

- **SDK responsibilities**  
  - Provider adapters (Google, Keycloak, proxy, etc.)  
  - Token/session store interfaces + default implementations  
  - Middleware + user-context utilities  
  - Public APIs to obtain provider tokens, refresh, and inspect scopes

- **Server responsibilities**  
  - Load config, instantiate `AuthService` from SDK, register FastMCP routes, and pass middleware into endpoint wrappers.  
  - Hook persistence paths, secrets, and policy engines defined by the deployment.

Keeping the SDK clean lets us embed the same auth stack into CLI, admin API, or other transports without duplicating logic.

### Expanded Proposal (Markdown)

```
# MXCP Authentication Redesign

## 1. Goals
- Single `AuthService` entry point for FastMCP servers and any other transports
- Secure token/session storage with refresh support and provider-token access
- Optional proxy/header mode
- Clear scope/entitlement story consumable by CEL and tools
- All reusable pieces live in `mxcp.sdk.auth`

## 2. Architecture
1. **AuthService**
   - `from_config(config, transport)` factory
   - Registers `/auth/oauth/callback`, `/auth/token`, and metadata routes
   - Owns `ProviderAdapter`, `SessionManager`, `TokenStore`, and `PolicyMapper`
   - Exposes `build_middleware()` returning the decorator used by endpoints
2. **ProviderAdapter Interface**
   - `build_authorize_url(request: AuthorizationRequest)`  
   - `exchange_code(code, state) -> ExternalGrantResult`  
   - `refresh(grant) -> ExternalGrantResult`  
   - `fetch_user_context(access_token) -> UserContextModel`
3. **Session + Token Layer**
   - `SessionManager` issues signed MXCP access tokens (JWT with session ID) and stores session state + encrypted provider tokens via `TokenStore`
   - `TokenStore` default backend: SQLite with hashed MXCP tokens + encrypted provider tokens (pluggable secret providers)
4. **Scopes & Policy Mapper**
   - Reads IdP claims (scopes, groups, custom attributes) or proxy headers
   - Produces `user_context.mxcp_scopes`
   - FastMCP-required scopes = union of all enforced scopes (or empty if we disable)
   - CEL policies use `user_context.mxcp_scopes`
5. **Proxy Handler**
   - Config example:
     ```yaml
     auth:
       provider: proxy
       proxy:
         user_id_header: X-User-ID
         username_header: X-User-Name
         email_header: X-User-Email
         scope_header: X-MXCP-Scopes
         signature:
           header: X-Auth-Signature
           secret_env: MXCP_PROXY_SECRET
     ```
   - Validates signature/mTLS, constructs `UserContext`, optional upstream token passthrough
6. **Middleware**
   - Verifies MXCP JWT → session lookup → ensures scopes/policies → sets `UserContext` and provides helper to fetch provider token (auto-refresh)

## 3. Token Refresh Flow
1. User completes OAuth → `AuthService` stores provider access+refresh tokens encrypted
2. Client exchanges auth code at `/auth/token` → receives MXCP access+refresh tokens
3. When MXCP refresh token hits `/auth/token` again:
   - SessionManager validates it
   - ProviderAdapter.refresh obtains new provider token(s)
   - Store updates
   - New MXCP access token returned

## 4. Endpoint/Policy Integration
- Execution context gains helper `auth_context.get_provider_token("google")`
- CEL policy functions:
  - `user_has_scope("mxcp.admin")`
  - `user_has_provider_scope("https://www.googleapis.com/auth/calendar")`
- Optionally support endpoint-level annotations referencing scopes

## 5. Migration Plan
1. Introduce AuthService and rewire `mcp.py` without behavior change
2. Extract SessionManager/TokenStore; switch middleware to JWT-based sessions
3. Implement refresh token support end-to-end
4. Add proxy handler and scope mapper
5. Update docs/tests/examples, especially to show how to access provider tokens inside tools
```

Let me know if you want this broken into implementation tickets or expanded with diagrams—happy to dive deeper.

```python
class UserAuthorizationConfigModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    required_scopes: list[str] = Field(default_factory=list)
...
class UserAuthConfigModel(BaseModel):
    ...
    authorization: UserAuthorizationConfigModel | None = None
```

```python
auth_authorization = auth_config.authorization
required_scopes = auth_authorization.required_scopes if auth_authorization else []
...
self.auth_settings = AuthSettings(..., required_scopes=required_scopes or None)
```

```plaintext
# MXCP Authentication Redesign

## 1. Goals
- Single `AuthService` entry point for FastMCP servers and any other transports
- Secure token/session storage with refresh support and provider-token access
- Optional proxy/header mode
- Clear scope/entitlement story consumable by CEL and tools
- All reusable pieces live in `mxcp.sdk.auth`

## 2. Architecture
1. **AuthService**
   - `from_config(config, transport)` factory
   - Registers `/auth/oauth/callback`, `/auth/token`, and metadata routes
   - Owns `ProviderAdapter`, `SessionManager`, `TokenStore`, and `PolicyMapper`
   - Exposes `build_middleware()` returning the decorator used by endpoints
2. **ProviderAdapter Interface**
   - `build_authorize_url(request: AuthorizationRequest)`  
   - `exchange_code(code, state) -> ExternalGrantResult`  
   - `refresh(grant) -> ExternalGrantResult`  
   - `fetch_user_context(access_token) -> UserContextModel`
3. **Session + Token Layer**
   - `SessionManager` issues signed MXCP access tokens (JWT with session ID) and stores session state + encrypted provider tokens via `TokenStore`
   - `TokenStore` default backend: SQLite with hashed MXCP tokens + encrypted provider tokens (pluggable secret providers)
4. **Scopes & Policy Mapper**
   - Reads IdP claims (scopes, groups, custom attributes) or proxy headers
   - Produces `user_context.mxcp_scopes`
   - FastMCP-required scopes = union of all enforced scopes (or empty if we disable)
   - CEL policies use `user_context.mxcp_scopes`
5. **Proxy Handler**
   - Config example:
    
     auth:
       provider: proxy
       proxy:
         user_id_header: X-User-ID
         username_header: X-User-Name
         email_header: X-User-Email
         scope_header: X-MXCP-Scopes
         signature:
           header: X-Auth-Signature
           secret_env: MXCP_PROXY_SECRET
        - Validates signature/mTLS, constructs `UserContext`, optional upstream token passthrough
6. **Middleware**
   - Verifies MXCP JWT → session lookup → ensures scopes/policies → sets `UserContext` and provides helper to fetch provider token (auto-refresh)

## 3. Token Refresh Flow
1. User completes OAuth → `AuthService` stores provider access+refresh tokens encrypted
2. Client exchanges auth code at `/auth/token` → receives MXCP access+refresh tokens
3. When MXCP refresh token hits `/auth/token` again:
   - SessionManager validates it
   - ProviderAdapter.refresh obtains new provider token(s)
   - Store updates
   - New MXCP access token returned

## 4. Endpoint/Policy Integration
- Execution context gains helper `auth_context.get_provider_token("google")`
- CEL policy functions:
  - `user_has_scope("mxcp.admin")`
  - `user_has_provider_scope("https://www.googleapis.com/auth/calendar")`
- Optionally support endpoint-level annotations referencing scopes

## 5. Migration Plan
1. Introduce AuthService and rewire `mcp.py` without behavior change
2. Extract SessionManager/TokenStore; switch middleware to JWT-based sessions
3. Implement refresh token support end-to-end
4. Add proxy handler and scope mapper
5. Update docs/tests/examples, especially to show how to access provider tokens inside tools
```

```plaintext
   - Validates signature/mTLS, constructs `UserContext`, optional upstream token passthrough
6. **Middleware**
   - Verifies MXCP JWT → session lookup → ensures scopes/policies → sets `UserContext` and provides helper to fetch provider token (auto-refresh)

## 3. Token Refresh Flow
1. User completes OAuth → `AuthService` stores provider access+refresh tokens encrypted
2. Client exchanges auth code at `/auth/token` → receives MXCP access+refresh tokens
3. When MXCP refresh token hits `/auth/token` again:
   - SessionManager validates it
   - ProviderAdapter.refresh obtains new provider token(s)
   - Store updates
   - New MXCP access token returned

## 4. Endpoint/Policy Integration
- Execution context gains helper `auth_context.get_provider_token("google")`
- CEL policy functions:
  - `user_has_scope("mxcp.admin")`
  - `user_has_provider_scope("https://www.googleapis.com/auth/calendar")`
- Optionally support endpoint-level annotations referencing scopes

## 5. Migration Plan
1. Introduce AuthService and rewire `mcp.py` without behavior change
2. Extract SessionManager/TokenStore; switch middleware to JWT-based sessions
3. Implement refresh token support end-to-end
4. Add proxy handler and scope mapper
5. Update docs/tests/examples, especially to show how to access provider tokens inside tools
```

---

**User**

again, not clear to me how to 'map idp claims to internal scopes'...

---

**Cursor**

Think of it as a translation table that turns whatever the IdP gives us (scopes, groups, custom claims) into the smaller, stable vocabulary MXCP actually understands. One practical way to do it:

- Add a config block alongside `auth.authorization.required_scopes`, e.g.

```
auth:
  provider: google
  authorization:
    required_scopes: ["mxcp.admin", "mxcp.viewer"]
    claim_mappings:
      google_scopes:
        "https://www.googleapis.com/auth/calendar": ["mxcp.viewer"]
        "https://www.googleapis.com/auth/admin.directory.user.readonly": ["mxcp.admin"]
      groups:
        "admins@company.com": ["mxcp.admin"]
        "readers@company.com": ["mxcp.viewer"]
```

- During authentication the provider adapter already fetches the user profile and any scopes/groups. Feed that data to a `ScopeMapper`:

```python
provider_claims = {
    "google_scopes": user_info.scopes,
    "groups": user_info.raw_profile.get("groups", []),
}
mxcp_scopes = scope_mapper.resolve(provider_claims)
# returns e.g. {"mxcp.viewer", "mxcp.admin"}
```

- Store `mxcp_scopes` in `UserContextModel`. Middleware can now enforce the required scopes, CEL policies can reference `user_context.mxcp_scopes`, and FastMCP’s global “required scopes” list stays consistent even if Google scope names change later.

So “mapping IdP claims to internal scopes” just means: look at whatever the IdP says about the user (scopes they granted, groups they belong to, custom attributes), run it through a configurable mapping table, and emit MXCP-native scope strings. It isn’t mandatory—if we don’t need that abstraction we can drop it—but it’s a common pattern when you want a stable permission vocabulary across multiple providers or proxy mode.

```plaintext
auth:
  provider: google
  authorization:
    required_scopes: ["mxcp.admin", "mxcp.viewer"]
    claim_mappings:
      google_scopes:
        "https://www.googleapis.com/auth/calendar": ["mxcp.viewer"]
        "https://www.googleapis.com/auth/admin.directory.user.readonly": ["mxcp.admin"]
      groups:
        "admins@company.com": ["mxcp.admin"]
        "readers@company.com": ["mxcp.viewer"]
```

```python
provider_claims = {
    "google_scopes": user_info.scopes,
    "groups": user_info.raw_profile.get("groups", []),
}
mxcp_scopes = scope_mapper.resolve(provider_claims)
# returns e.g. {"mxcp.viewer", "mxcp.admin"}
```

---

**User**

So in our endpoint yamls, user would put whatever 'scopes' they'd want. In the config file, we'd list what these are, and then we have the mapping. Is it necessary to list what those are? we dynamically read from endpoint files? we dont care and let them map to strings? U said "Authorization: required_scopes:". Are those the ones necessary to access the server? And the others are per endpoint? Note mxcp is a system itself that lets people build servers in a way with their own 'entitlements' that they define.

---

**Cursor**

- `auth.authorization.required_scopes` in `mxcp-site.yml` is the **server‑level contract** we already expose to FastMCP—any client connecting must request *at least* those scopes to even hit our tools. Today it’s a list of strings we read from config (see `UserAuthorizationConfigModel` and how `RAWMCP` forwards it); nothing is enforced per endpoint yet.
- Endpoint YAMLs can (and should) declare their own entitlements, e.g. inside the tool definition:  
  ```yaml
  annotations:
    scopes:
      - mxcp.customers.read
      - mxcp.billing.write
  ```  
  These are arbitrary strings defined by the builder; we don’t need to pre‑register them anywhere. At load time we gather every scope referenced across endpoints so we can (a) validate spelling/duplicates if desired and (b) feed policy engines.
- In config you only *have* to list the scopes that are globally required (`required_scopes`). Everything else can be discovered from endpoints or policy rules. Listing them centrally is optional but can help with documentation (e.g. `authorization.known_scopes` just to keep humans honest); enforcement can rely on the discovered ones.
- The IdP‑to‑MXCP mapping simply translates whatever claims we get (IdP scopes, groups, proxy headers) into those user‑defined strings. If an endpoint references `mxcp.billing.write`, the mapper needs to know which IdP claim implies that entitlement; config is the natural place for that mapping.
- So the flow is:
  1. Server config declares `required_scopes` (global gate) and optionally the mapping from IdP claims → MXCP scope strings.
  2. Endpoint YAMLs name whatever scopes they need; we index them dynamically.
  3. At runtime middleware computes the user’s `mxcp_scopes` from the mapper and enforces both the global list and any endpoint‑specific requirements before execution.
- Because MXCP is an app platform, giving builders the freedom to mint their own entitlement names is expected. The “central listing” is only necessary if you want validation/tooling; technically we can accept arbitrary strings as long as the mapper can produce them from IdP data (or they’re injected via proxy mode).

```yaml
  annotations:
    scopes:
      - mxcp.customers.read
      - mxcp.billing.write
```

---

**User**

I guess we don't truly need the 'central listing'. We can later on have admin tools to inspect that. Can you create a plan for how to implement all this? Everything. Including all the proxy system.

---

**Cursor**

### Auth Overhaul Implementation Plan

#### Phase 0 – Discovery & Guardrails
- Document current auth surfaces (FastMCP routes, middleware, persistence paths, config schema, endpoint annotations).  
- Freeze CLI/SDK contracts to avoid surprises; add high-level ADR describing target architecture.  
- Add small telemetry hook to count current use of `required_scopes` and persistence backends (helps assess break risk).

#### Phase 1 – AuthService Skeleton (no behavior change)
- Introduce `mxcp.sdk.auth.service.AuthService` with:
  - `from_config(auth_config, transport_config, site_config)` factory.
  - `register_routes(fastmcp)` to install existing callback + well-known endpoints.
  - `build_middleware()` returning the current `AuthenticationMiddleware`.
- Refactor `RAWMCP` to instantiate `AuthService` instead of juggling handler/server/middleware directly.
- Add exhaustive tests around service instantiation so future refactors don’t regress.

#### Phase 2 – Session & Token Infrastructure
- Create `mxcp.sdk.auth.sessions` package:
  - `SessionManager` issuing MXCP access tokens (JWT or opaque random IDs) and refresh tokens.
  - `TokenStore` interface with default SQLite backend (reuse existing file path) but:
    - Hash MXCP tokens before storage.
    - Encrypt provider tokens/refresh tokens via `SecretBox` abstraction (Fernet, Keychain, env-provided key).
  - Background cleanup job for expired sessions/tokens.
- Update middleware to:
  - Extract bearer token → verify via `SessionManager` → hydrate `UserContext`.
  - Remove direct access to `GeneralOAuthAuthorizationServer._token_mapping`.
- Adjust provider callbacks to store grants via `SessionManager` instead of manipulating `_tokens`.

#### Phase 3 – Provider Adapter Refactor & Refresh Support
- Define `ProviderAdapter` protocol (`authorize`, `exchange_code`, `refresh`, `fetch_user_context`).
- Convert existing providers (Google, Keycloak, GitHub, etc.) to adapters that only talk to the IdP.
- Implement refresh path:
  - Store provider refresh tokens encrypted.
  - Add `/auth/token` endpoint supporting `authorization_code` and `refresh_token` grants (RFC 6749).
  - Wire `SessionManager` to call `adapter.refresh()` when MXCP refresh tokens are used.
- Provide SDK helper `get_provider_token(provider_name, user_context)` that refreshes as needed; expose to endpoint runtime via execution context.

#### Phase 4 – Scope & Mapping Layer
- Extend `UserContextModel` with `mxcp_scopes: set[str]` and `provider_scopes: set[str]`.
- Add `ScopeMapper`:
  - Reads mapping config (`authorization.claim_mappings`), plus supports default strategies (e.g., pass-through IdP scopes, group-to-scope mapping, regex).
  - Given provider claims (scopes, groups, proxy headers) returns MXCP scopes.
- Update middleware to enforce:
  - Global `required_scopes`.
  - Per-endpoint scopes (read from YAML annotations or policy metadata) before dispatch.
- Surface `user_context.mxcp_scopes` in CEL and logging.

#### Phase 5 – Endpoint & Policy Integration
- Extend endpoint models to accept `annotations.scopes` (if not already).
- Loader indexes all scopes referenced by endpoints; optional validation warns on orphan scopes.
- Modify execution wrapper to pass endpoint-specific scope requirements to middleware (e.g., `auth_middleware.require_scopes(scopes)` decorator or per-call parameter).
- Update CEL policies to leverage new context (helper functions `user_has_scope`, etc.).

#### Phase 6 – Proxy / Header Mode
- Add `proxy` provider config in SDK models (`ProxyAuthConfigModel` with header names, signature settings, optional mTLS requirement).
- Implement `ProxyAuthAdapter`:
  - Validates incoming headers (HMAC, shared secret, or TLS client cert).
  - Constructs `UserContextModel`, including upstream token if provided.
  - Runs through `ScopeMapper` using header values (e.g., `X-MXCP-Scopes` or claims JSON).
- Allow `AuthService` to run purely in proxy mode (no OAuth routes) or hybrid (OAuth + proxy fallback).
- Provide sample `nginx`/Envoy snippet in docs showing expected headers/signature.

#### Phase 7 – Persistence Hardening & Secret Management
- Pluggable `SecretProvider` abstraction (env key, Keychain, Vault, AWS KMS).  
- Ensure token store never leaves plaintext tokens on disk; add rotation tooling.
- Add admin CLI (`mxcp auth list-sessions`, `mxcp auth revoke --session`) interacting with `SessionManager`.

#### Phase 8 – Observability & Admin Tools
- Emit metrics for login attempts, scope resolutions, refresh success/failure, proxy validations.
- Add admin endpoint / CLI to inspect configured scopes, mappings, and active sessions (read-only).
- Build automated tests covering each provider path, scope enforcement, proxy signature failures, refresh flows.

#### Phase 9 – Documentation & Examples
- Update docs/guides/authentication.md with:
  - New config schema (claim mappings, proxy provider, secret storage).
  - How endpoint YAML scopes interact with IdP mappings.
  - How to fetch provider tokens inside tools.
- Provide example site config + endpoint set demonstrating Google, Keycloak, and proxy scenarios.

#### Phase 10 – Rollout & Migration
- Ship feature-flagged or profile-gated versions (e.g., `auth.mode = legacy|v2`) to allow gradual migration.
- Offer migration script to convert existing SQLite DB to hashed/encrypted format.
- Communicate breaking changes (new config fields required, token revocation semantics, etc.).

Let me know if you want this broken into tickets or if we should prioritize one slice (e.g., refresh support) before tackling proxy mode.

---

**User**

Please write the plan as a markdown file. Skip the telemetry. Also, "from_config(auth_config, transport_config, site_config) factory.

" is this safe? site_config I think its NOT an sdk concept? make sure. We have a strict split between SDK and non-SDK. No need for code sniuppets in plan markdown file.

---

**Cursor**

Let me check the SDK vs server split to ensure the plan respects it.

You're right. `SiteConfigModel` is defined in `mxcp.server.core.config.models`, not in the SDK. The SDK's `AuthService.from_config()` should only accept SDK-level models like `AuthConfigModel` and `HttpTransportConfigModel` from `mxcp.sdk.auth.models`. The server layer is responsible for translating its config into SDK types before calling the factory.

Let me write the plan:

```markdown
# MXCP Authentication Redesign Plan

## Overview

This document outlines the implementation plan for overhauling MXCP's authentication system. The goals are:

- Single `AuthService` entry point for all transports
- Secure token and session storage with refresh support
- Access to upstream provider tokens for calling external APIs
- Proxy/header-trust mode for deployments behind SSO-aware reverse proxies
- Clear scope and entitlement model consumable by CEL policies and endpoint annotations
- Strict separation between SDK (reusable, well-typed) and server (config loading, FastMCP wiring)

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

## Target Architecture

### SDK Layer (`mxcp.sdk.auth`)

The SDK provides reusable, well-typed components independent of server configuration:

- **AuthService**: Main entry point; owns provider adapter, session manager, scope mapper
- **ProviderAdapter**: Protocol for IdP integrations (Google, Keycloak, GitHub, proxy, etc.)
- **SessionManager**: Issues and validates MXCP tokens; manages session lifecycle
- **TokenStore**: Persistence interface for sessions, tokens, and encrypted provider credentials
- **ScopeMapper**: Translates IdP claims to MXCP entitlements
- **SecretProvider**: Abstraction for encryption keys (env, Keychain, Vault, KMS)
- **AuthMiddleware**: Request authentication and scope enforcement

### Server Layer (`mxcp.server`)

The server translates config, instantiates SDK components, and wires FastMCP:

- Loads `UserAuthConfigModel` from site/user config
- Converts to SDK models (`AuthConfigModel`, `HttpTransportConfigModel`)
- Instantiates `AuthService` and registers routes with FastMCP
- Passes middleware to endpoint wrappers
- Hooks persistence paths and secret providers based on deployment config

---

## Implementation Phases

### Phase 1: AuthService Skeleton

**Goal**: Introduce `AuthService` abstraction without changing behavior.

**Tasks**:
1. Create `mxcp.sdk.auth.service` module with `AuthService` class
2. Define `from_config(auth_config, transport_config)` factory accepting only SDK models
3. Add `register_routes(fastmcp)` method that installs existing callback and well-known endpoints
4. Add `build_middleware()` method returning current `AuthenticationMiddleware`
5. Refactor `RAWMCP` to instantiate `AuthService` instead of managing handler/server/middleware directly
6. Server layer responsible for translating `UserAuthConfigModel` to SDK models before calling factory
7. Add comprehensive tests for service instantiation and route registration

**Outcome**: Single entry point for auth; internal structure unchanged.

---

### Phase 2: Session and Token Infrastructure

**Goal**: Proper session management with secure token storage.

**Tasks**:
1. Create `mxcp.sdk.auth.sessions` package with:
   - `SessionManager` class for issuing MXCP access and refresh tokens
   - `Session` dataclass holding session ID, user context, provider grants, expiry
2. Create `mxcp.sdk.auth.storage` package with:
   - `TokenStore` protocol defining CRUD operations
   - `SqliteTokenStore` implementation (default backend)
   - Hash MXCP tokens before storage (one-way)
   - Encrypt provider tokens and refresh tokens at rest
3. Define `SecretProvider` protocol for encryption key management:
   - `EnvSecretProvider` (reads key from environment variable)
   - Future: Keychain, Vault, KMS implementations
4. Update middleware to:
   - Extract bearer token and verify via `SessionManager`
   - Hydrate `UserContext` from session without accessing private mappings
5. Update provider callbacks to store grants via `SessionManager`
6. Add background cleanup job for expired sessions and tokens
7. Migrate existing SQLite schema; provide data migration tooling

**Outcome**: Clean session abstraction; encrypted storage; no private field access.

---

### Phase 3: Provider Adapter Refactor

**Goal**: Thin provider adapters that only talk to IdPs.

**Tasks**:
1. Define `ProviderAdapter` protocol with methods:
   - `build_authorize_url(request)` returning authorization URL
   - `exchange_code(code, state)` returning `ExternalGrantResult`
   - `refresh(grant)` returning `ExternalGrantResult`
   - `fetch_user_context(access_token)` returning `UserContextModel`
2. Define `ExternalGrantResult` dataclass with:
   - Access token, refresh token, expiry timestamp
   - Raw profile data, provider scopes
3. Convert existing providers (Google, Keycloak, GitHub, Atlassian, Salesforce) to adapters:
   - Remove route registration logic
   - Remove persistence calls
   - Remove state storage (move to `SessionManager`)
4. Update `AuthService` to:
   - Own single callback route (e.g., `/auth/oauth/callback`)
   - Dispatch to appropriate adapter based on session state
   - Store grants via `SessionManager`
5. Add tests for each provider adapter in isolation

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

**Outcome**: Long-lived sessions; provider tokens stay fresh; endpoints can call external APIs.

---

### Phase 5: Scope and Mapping Layer

**Goal**: Translate IdP claims to MXCP entitlements; enforce per endpoint.

**Tasks**:
1. Extend `UserContextModel` with:
   - `mxcp_scopes: set[str]` for internal entitlements
   - `provider_scopes: set[str]` for raw IdP scopes
2. Create `ScopeMapper` class:
   - Accepts mapping configuration (claim type → scope mappings)
   - Given provider claims (scopes, groups, custom attributes) returns MXCP scopes
   - Supports multiple strategies: direct passthrough, group mapping, regex patterns
3. Define mapping config schema in SDK models:
   - `ClaimMappingConfigModel` with source type, claim name, scope mappings
4. Update `AuthService` to run `ScopeMapper` after authentication
5. Update middleware to:
   - Check global `required_scopes` from config
   - Accept endpoint-specific scope requirements as parameter
   - Reject requests missing required scopes
6. Surface `user_context.mxcp_scopes` to CEL policy engine
7. Add tests for mapping scenarios: groups to scopes, passthrough, multiple claims

**Outcome**: Stable MXCP entitlement vocabulary; enforceable per endpoint.

---

### Phase 6: Endpoint and Policy Integration

**Goal**: Per-endpoint scope requirements; CEL integration.

**Tasks**:
1. Extend endpoint YAML schema to accept scope annotations:
   - Under `annotations.scopes` list required MXCP scopes
2. Update endpoint loader to index all referenced scopes across endpoints
3. Update execution wrapper to:
   - Read endpoint scope requirements from definition
   - Pass requirements to middleware for enforcement
4. Add CEL helper functions:
   - `user_has_scope(scope_name)` checking `user_context.mxcp_scopes`
   - `user_has_provider_scope(scope_name)` checking raw provider scopes
5. Update policy enforcer to leverage new context fields
6. Optional: Add validation warning for undefined scopes in endpoints
7. Add tests for endpoint-level scope enforcement and CEL integration

**Outcome**: Builders define scopes per endpoint; policies can reference them.

---

### Phase 7: Proxy and Header Mode

**Goal**: Support deployments behind SSO-aware reverse proxies.

**Tasks**:
1. Define `ProxyAuthConfigModel` in SDK with:
   - Header names for user ID, username, email, scopes
   - Optional upstream token header for passthrough
   - Signature validation settings (header name, secret env, algorithm)
   - Optional mTLS requirement flag
2. Implement `ProxyAuthAdapter`:
   - Reads configured headers from request
   - Validates signature (HMAC) or mTLS if configured
   - Constructs `UserContextModel` from headers
   - Extracts upstream token if present
3. Integrate with `ScopeMapper`:
   - Scope header value parsed and mapped to MXCP scopes
   - Alternatively, accept pre-mapped scopes directly from proxy
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

**Goal**: Production-grade secure storage.

**Tasks**:
1. Implement additional `SecretProvider` backends:
   - macOS Keychain
   - HashiCorp Vault
   - AWS KMS (stretch)
2. Add token rotation tooling:
   - CLI command to rotate encryption keys
   - Automatic re-encryption of stored tokens
3. Add admin CLI commands:
   - `mxcp auth list-sessions` showing active sessions (no secrets)
   - `mxcp auth revoke --session <id>` to invalidate sessions
   - `mxcp auth cleanup` to purge expired data
4. Add audit events for:
   - Session creation and revocation
   - Token refresh attempts
   - Authentication failures
5. Add tests for key rotation and admin operations

**Outcome**: Encrypted storage with key rotation; admin visibility and control.

---

### Phase 9: Admin Tooling

**Goal**: Operational visibility into auth state.

**Tasks**:
1. Add admin API endpoints (via admin socket):
   - List active sessions (count, providers, expiry)
   - Revoke session by ID
   - View configured scopes and mappings
2. Add CLI commands wrapping admin API
3. Add health check endpoint reporting auth subsystem status
4. Document admin operations and troubleshooting procedures

**Outcome**: Operators can inspect and manage auth state.

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
3. Add migration guide for existing deployments
4. Add troubleshooting section for common issues

**Outcome**: Builders can configure any auth scenario from docs.

---

### Phase 11: Rollout and Migration

**Goal**: Safe migration path for existing users.

**Tasks**:
1. Feature flag new auth system (e.g., `auth.version: 2`)
2. Support running both systems during transition
3. Provide migration script for:
   - Converting existing SQLite data to new schema
   - Hashing existing tokens
   - Encrypting provider tokens
4. Communicate breaking changes:
   - New required config fields
   - Token format changes (existing tokens invalidated)
   - Persistence path changes if any
5. Deprecation timeline for legacy auth code

**Outcome**: Existing deployments can migrate safely.

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
- Configures persistence paths and secret providers

---

## Success Criteria

- Single `AuthService` entry point replaces current tangled architecture
- Provider tokens accessible and auto-refreshed for endpoint code
- Proxy mode working with signature validation
- Per-endpoint scope enforcement operational
- All tokens encrypted at rest
- Migration path documented and tested
- No regressions in existing OAuth flows

```

Created the plan at `docs/contributors/auth-redesign-plan.md`. Key points:

1. **SDK/Server split is strict** – `AuthService.from_config()` only accepts SDK models (`AuthConfigModel`, `HttpTransportConfigModel`). The server layer translates its config models before calling the factory.

2. **No telemetry** – removed as requested.

3. **Phases are incremental** – each phase delivers value and can be merged independently. Phase 1 changes nothing behaviorally, just introduces the abstraction.

4. **Provider token access** – Phase 4 adds `get_provider_token(user_context)` helper so endpoints can call upstream APIs (Google, etc.) with auto-refresh.

5. **Scopes are endpoint-driven** – no central registry required. Endpoints declare what they need in YAML annotations; `ScopeMapper` translates IdP claims to those strings.

6. **Proxy mode** – Phase 7 adds full support for header-trust deployments with signature validation.

Let me know if you want to adjust any phases or dive deeper into a specific section.

---

**User**

Explain this one:

@auth-redesign-plan.md (91-94) 

is this a generic feature or stricly related to token storage? explain.

btw, we do have a system that resolves secrets from 1password etc (it's a resolver around config settings) and i wonder if its supposed to be more generic and also leveraged here?

but this was about storing tokens right? that's not same as secrets?

---

**Cursor**

Good catch – let me clarify.

**What `SecretProvider` was meant for**: It's specifically about obtaining the **encryption key** used to encrypt provider tokens (Google access tokens, refresh tokens) before storing them in SQLite. It's not about storing the tokens themselves – it's about "where do I get the key to encrypt what I'm storing?"

**Tokens vs secrets**:
- **Secrets** = credentials the admin provides (Google client_secret, API keys) → resolved at config load time via your existing resolvers
- **Tokens** = what the system receives from IdPs during OAuth flows (access tokens, refresh tokens) → stored by our auth system in SQLite

The tokens need to be encrypted at rest because they grant access to user accounts. The encryption key itself needs to come from somewhere secure.

**Your existing resolver system**: You already have `mxcp.sdk.core.config.resolvers` that handles `vault://...`, `op://...`, `${ENV_VAR}` patterns for config values. We could absolutely reuse that instead of inventing a new `SecretProvider`:

```yaml
auth:
  persistence:
    type: sqlite
    path: ~/.mxcp/oauth.db
    encryption_key: "vault://secret/mxcp/token-encryption-key"
    # or: "op://vault/mxcp/encryption-key"
    # or: "${MXCP_TOKEN_ENCRYPTION_KEY}"
```

At startup, the existing resolver fetches the key, and `TokenStore` uses it for Fernet encryption of provider tokens. No new abstraction needed.

**Bottom line**: `SecretProvider` was over-engineered. We should just make `encryption_key` a config field resolved by your existing system. I'll update the plan to reflect this.

```yaml
auth:
  persistence:
    type: sqlite
    path: ~/.mxcp/oauth.db
    encryption_key: "vault://secret/mxcp/token-encryption-key"
    # or: "op://vault/mxcp/encryption-key"
    # or: "${MXCP_TOKEN_ENCRYPTION_KEY}"
```

---

**User**

Ok. So it's fernet encryption FOR sqlite implementation, but we could have others and those could store things elsewhere. IF so that makes sense.

---

**Cursor**

Exactly. The encryption is an implementation detail of the SQLite backend specifically, not a global concern.

The `TokenStore` interface just defines CRUD operations:
- `store_session(session)`
- `load_session(session_id)`
- `store_provider_token(session_id, token)`
- `delete_session(session_id)`
- etc.

Each backend handles security its own way:

| Backend | Security approach |
|---------|-------------------|
| SQLite | Fernet encryption with key from config (resolved via existing resolvers) |
| HashiCorp Vault | Stores tokens directly in Vault; Vault handles encryption |
| AWS Secrets Manager | Stores in Secrets Manager; AWS handles encryption |
| Redis (hypothetical) | Client-side encryption or rely on Redis TLS + disk encryption |

So no `SecretProvider` abstraction needed. SQLite backend just has a config field `encryption_key` that goes through the normal resolver pipeline. Other backends don't need that field at all because they delegate security to their underlying system.

I'll update the plan to remove the `SecretProvider` abstraction and clarify this.

---

**User**

update the plan then yes 

---

**Cursor**

```markdown
# MXCP Authentication Redesign Plan

## Overview

This document outlines the implementation plan for overhauling MXCP's authentication system. The goals are:

- Single `AuthService` entry point for all transports
- Secure token and session storage with refresh support
- Access to upstream provider tokens for calling external APIs
- Proxy/header-trust mode for deployments behind SSO-aware reverse proxies
- Clear scope and entitlement model consumable by CEL policies and endpoint annotations
- Strict separation between SDK (reusable, well-typed) and server (config loading, FastMCP wiring)

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
- Hooks persistence paths and secret providers based on deployment config

---

## Implementation Phases

### Phase 1: AuthService Skeleton

**Goal**: Introduce `AuthService` abstraction without changing behavior.

**Tasks**:
1. Create `mxcp.sdk.auth.service` module with `AuthService` class
2. Define `from_config(auth_config, transport_config)` factory accepting only SDK models
3. Add `register_routes(fastmcp)` method that installs existing callback and well-known endpoints
4. Add `build_middleware()` method returning current `AuthenticationMiddleware`
5. Refactor `RAWMCP` to instantiate `AuthService` instead of managing handler/server/middleware directly
6. Server layer responsible for translating `UserAuthConfigModel` to SDK models before calling factory
7. Add comprehensive tests for service instantiation and route registration

**Outcome**: Single entry point for auth; internal structure unchanged.

---

### Phase 2: Session and Token Infrastructure

**Goal**: Proper session management with secure token storage.

**Tasks**:
1. Create `mxcp.sdk.auth.sessions` package with:
   - `SessionManager` class for issuing MXCP access and refresh tokens
   - `Session` dataclass holding session ID, user context, provider grants, expiry
2. Create `mxcp.sdk.auth.storage` package with:
   - `TokenStore` protocol defining CRUD operations
   - `SqliteTokenStore` implementation (default backend)
   - Hash MXCP tokens before storage (one-way)
   - Encrypt provider tokens and refresh tokens at rest
3. Define `SecretProvider` protocol for encryption key management:
   - `EnvSecretProvider` (reads key from environment variable)
   - Future: Keychain, Vault, KMS implementations
4. Update middleware to:
   - Extract bearer token and verify via `SessionManager`
   - Hydrate `UserContext` from session without accessing private mappings
5. Update provider callbacks to store grants via `SessionManager`
6. Add background cleanup job for expired sessions and tokens
7. Migrate existing SQLite schema; provide data migration tooling

**Outcome**: Clean session abstraction; encrypted storage; no private field access.

---

### Phase 3: Provider Adapter Refactor

**Goal**: Thin provider adapters that only talk to IdPs.

**Tasks**:
1. Define `ProviderAdapter` protocol with methods:
   - `build_authorize_url(request)` returning authorization URL
   - `exchange_code(code, state)` returning `ExternalGrantResult`
   - `refresh(grant)` returning `ExternalGrantResult`
   - `fetch_user_context(access_token)` returning `UserContextModel`
2. Define `ExternalGrantResult` dataclass with:
   - Access token, refresh token, expiry timestamp
   - Raw profile data, provider scopes
3. Convert existing providers (Google, Keycloak, GitHub, Atlassian, Salesforce) to adapters:
   - Remove route registration logic
   - Remove persistence calls
   - Remove state storage (move to `SessionManager`)
4. Update `AuthService` to:
   - Own single callback route (e.g., `/auth/oauth/callback`)
   - Dispatch to appropriate adapter based on session state
   - Store grants via `SessionManager`
5. Add tests for each provider adapter in isolation

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

**Outcome**: Long-lived sessions; provider tokens stay fresh; endpoints can call external APIs.

---

### Phase 5: Scope and Mapping Layer

**Goal**: Translate IdP claims to MXCP entitlements; enforce per endpoint.

**Tasks**:
1. Extend `UserContextModel` with:
   - `mxcp_scopes: set[str]` for internal entitlements
   - `provider_scopes: set[str]` for raw IdP scopes
2. Create `ScopeMapper` class:
   - Accepts mapping configuration (claim type → scope mappings)
   - Given provider claims (scopes, groups, custom attributes) returns MXCP scopes
   - Supports multiple strategies: direct passthrough, group mapping, regex patterns
3. Define mapping config schema in SDK models:
   - `ClaimMappingConfigModel` with source type, claim name, scope mappings
4. Update `AuthService` to run `ScopeMapper` after authentication
5. Update middleware to:
   - Check global `required_scopes` from config
   - Accept endpoint-specific scope requirements as parameter
   - Reject requests missing required scopes
6. Surface `user_context.mxcp_scopes` to CEL policy engine
7. Add tests for mapping scenarios: groups to scopes, passthrough, multiple claims

**Outcome**: Stable MXCP entitlement vocabulary; enforceable per endpoint.

---

### Phase 6: Endpoint and Policy Integration

**Goal**: Per-endpoint scope requirements; CEL integration.

**Tasks**:
1. Extend endpoint YAML schema to accept scope annotations:
   - Under `annotations.scopes` list required MXCP scopes
2. Update endpoint loader to index all referenced scopes across endpoints
3. Update execution wrapper to:
   - Read endpoint scope requirements from definition
   - Pass requirements to middleware for enforcement
4. Add CEL helper functions:
   - `user_has_scope(scope_name)` checking `user_context.mxcp_scopes`
   - `user_has_provider_scope(scope_name)` checking raw provider scopes
5. Update policy enforcer to leverage new context fields
6. Optional: Add validation warning for undefined scopes in endpoints
7. Add tests for endpoint-level scope enforcement and CEL integration

**Outcome**: Builders define scopes per endpoint; policies can reference them.

---

### Phase 7: Proxy and Header Mode

**Goal**: Support deployments behind SSO-aware reverse proxies.

**Tasks**:
1. Define `ProxyAuthConfigModel` in SDK with:
   - Header names for user ID, username, email, scopes
   - Optional upstream token header for passthrough
   - Signature validation settings (header name, secret env, algorithm)
   - Optional mTLS requirement flag
2. Implement `ProxyAuthAdapter`:
   - Reads configured headers from request
   - Validates signature (HMAC) or mTLS if configured
   - Constructs `UserContextModel` from headers
   - Extracts upstream token if present
3. Integrate with `ScopeMapper`:
   - Scope header value parsed and mapped to MXCP scopes
   - Alternatively, accept pre-mapped scopes directly from proxy
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

**Goal**: Production-grade secure storage.

**Tasks**:
1. Implement additional `SecretProvider` backends:
   - macOS Keychain
   - HashiCorp Vault
   - AWS KMS (stretch)
2. Add token rotation tooling:
   - CLI command to rotate encryption keys
   - Automatic re-encryption of stored tokens
3. Add admin CLI commands:
   - `mxcp auth list-sessions` showing active sessions (no secrets)
   - `mxcp auth revoke --session <id>` to invalidate sessions
   - `mxcp auth cleanup` to purge expired data
4. Add audit events for:
   - Session creation and revocation
   - Token refresh attempts
   - Authentication failures
5. Add tests for key rotation and admin operations

**Outcome**: Encrypted storage with key rotation; admin visibility and control.

---

### Phase 9: Admin Tooling

**Goal**: Operational visibility into auth state.

**Tasks**:
1. Add admin API endpoints (via admin socket):
   - List active sessions (count, providers, expiry)
   - Revoke session by ID
   - View configured scopes and mappings
2. Add CLI commands wrapping admin API
3. Add health check endpoint reporting auth subsystem status
4. Document admin operations and troubleshooting procedures

**Outcome**: Operators can inspect and manage auth state.

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
3. Add migration guide for existing deployments
4. Add troubleshooting section for common issues

**Outcome**: Builders can configure any auth scenario from docs.

---

### Phase 11: Rollout and Migration

**Goal**: Safe migration path for existing users.

**Tasks**:
1. Feature flag new auth system (e.g., `auth.version: 2`)
2. Support running both systems during transition
3. Provide migration script for:
   - Converting existing SQLite data to new schema
   - Hashing existing tokens
   - Encrypting provider tokens
4. Communicate breaking changes:
   - New required config fields
   - Token format changes (existing tokens invalidated)
   - Persistence path changes if any
5. Deprecation timeline for legacy auth code

**Outcome**: Existing deployments can migrate safely.

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
- Configures persistence paths and secret providers

---

## Success Criteria

- Single `AuthService` entry point replaces current tangled architecture
- Provider tokens accessible and auto-refreshed for endpoint code
- Proxy mode working with signature validation
- Per-endpoint scope enforcement operational
- All tokens encrypted at rest
- Migration path documented and tested
- No regressions in existing OAuth flows


```

```markdown
# MXCP Authentication Redesign Plan

## Overview

This document outlines the implementation plan for overhauling MXCP's authentication system. The goals are:

- Single `AuthService` entry point for all transports
- Secure token and session storage with refresh support
- Access to upstream provider tokens for calling external APIs
- Proxy/header-trust mode for deployments behind SSO-aware reverse proxies
- Clear scope and entitlement model consumable by CEL policies and endpoint annotations
- Strict separation between SDK (reusable, well-typed) and server (config loading, FastMCP wiring)

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

**Goal**: Introduce `AuthService` abstraction without changing behavior.

**Tasks**:
1. Create `mxcp.sdk.auth.service` module with `AuthService` class
2. Define `from_config(auth_config, transport_config)` factory accepting only SDK models
3. Add `register_routes(fastmcp)` method that installs existing callback and well-known endpoints
4. Add `build_middleware()` method returning current `AuthenticationMiddleware`
5. Refactor `RAWMCP` to instantiate `AuthService` instead of managing handler/server/middleware directly
6. Server layer responsible for translating `UserAuthConfigModel` to SDK models before calling factory
7. Add comprehensive tests for service instantiation and route registration

**Outcome**: Single entry point for auth; internal structure unchanged.

---

### Phase 2: Session and Token Infrastructure

**Goal**: Proper session management with secure token storage.

**Tasks**:
1. Create `mxcp.sdk.auth.sessions` package with:
   - `SessionManager` class for issuing MXCP access and refresh tokens
   - `Session` dataclass holding session ID, user context, provider grants, expiry
2. Create `mxcp.sdk.auth.storage` package with:
   - `TokenStore` protocol defining CRUD operations
   - `SqliteTokenStore` implementation (default backend)
   - Hash MXCP tokens before storage (one-way)
   - Encrypt provider tokens and refresh tokens at rest
3. Define `SecretProvider` protocol for encryption key management:
   - `EnvSecretProvider` (reads key from environment variable)
   - Future: Keychain, Vault, KMS implementations
4. Update middleware to:
   - Extract bearer token and verify via `SessionManager`
   - Hydrate `UserContext` from session without accessing private mappings
5. Update provider callbacks to store grants via `SessionManager`
6. Add background cleanup job for expired sessions and tokens
7. Migrate existing SQLite schema; provide data migration tooling

**Outcome**: Clean session abstraction; encrypted storage; no private field access.

---

### Phase 3: Provider Adapter Refactor

**Goal**: Thin provider adapters that only talk to IdPs.

**Tasks**:
1. Define `ProviderAdapter` protocol with methods:
   - `build_authorize_url(request)` returning authorization URL
   - `exchange_code(code, state)` returning `ExternalGrantResult`
   - `refresh(grant)` returning `ExternalGrantResult`
   - `fetch_user_context(access_token)` returning `UserContextModel`
2. Define `ExternalGrantResult` dataclass with:
   - Access token, refresh token, expiry timestamp
   - Raw profile data, provider scopes
3. Convert existing providers (Google, Keycloak, GitHub, Atlassian, Salesforce) to adapters:
   - Remove route registration logic
   - Remove persistence calls
   - Remove state storage (move to `SessionManager`)
4. Update `AuthService` to:
   - Own single callback route (e.g., `/auth/oauth/callback`)
   - Dispatch to appropriate adapter based on session state
   - Store grants via `SessionManager`
5. Add tests for each provider adapter in isolation

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

**Outcome**: Long-lived sessions; provider tokens stay fresh; endpoints can call external APIs.

---

### Phase 5: Scope and Mapping Layer

**Goal**: Translate IdP claims to MXCP entitlements; enforce per endpoint.

**Tasks**:
1. Extend `UserContextModel` with:
   - `mxcp_scopes: set[str]` for internal entitlements
   - `provider_scopes: set[str]` for raw IdP scopes
2. Create `ScopeMapper` class:
   - Accepts mapping configuration (claim type → scope mappings)
   - Given provider claims (scopes, groups, custom attributes) returns MXCP scopes
   - Supports multiple strategies: direct passthrough, group mapping, regex patterns
3. Define mapping config schema in SDK models:
   - `ClaimMappingConfigModel` with source type, claim name, scope mappings
4. Update `AuthService` to run `ScopeMapper` after authentication
5. Update middleware to:
   - Check global `required_scopes` from config
   - Accept endpoint-specific scope requirements as parameter
   - Reject requests missing required scopes
6. Surface `user_context.mxcp_scopes` to CEL policy engine
7. Add tests for mapping scenarios: groups to scopes, passthrough, multiple claims

**Outcome**: Stable MXCP entitlement vocabulary; enforceable per endpoint.

---

### Phase 6: Endpoint and Policy Integration

**Goal**: Per-endpoint scope requirements; CEL integration.

**Tasks**:
1. Extend endpoint YAML schema to accept scope annotations:
   - Under `annotations.scopes` list required MXCP scopes
2. Update endpoint loader to index all referenced scopes across endpoints
3. Update execution wrapper to:
   - Read endpoint scope requirements from definition
   - Pass requirements to middleware for enforcement
4. Add CEL helper functions:
   - `user_has_scope(scope_name)` checking `user_context.mxcp_scopes`
   - `user_has_provider_scope(scope_name)` checking raw provider scopes
5. Update policy enforcer to leverage new context fields
6. Optional: Add validation warning for undefined scopes in endpoints
7. Add tests for endpoint-level scope enforcement and CEL integration

**Outcome**: Builders define scopes per endpoint; policies can reference them.

---

### Phase 7: Proxy and Header Mode

**Goal**: Support deployments behind SSO-aware reverse proxies.

**Tasks**:
1. Define `ProxyAuthConfigModel` in SDK with:
   - Header names for user ID, username, email, scopes
   - Optional upstream token header for passthrough
   - Signature validation settings (header name, secret env, algorithm)
   - Optional mTLS requirement flag
2. Implement `ProxyAuthAdapter`:
   - Reads configured headers from request
   - Validates signature (HMAC) or mTLS if configured
   - Constructs `UserContextModel` from headers
   - Extracts upstream token if present
3. Integrate with `ScopeMapper`:
   - Scope header value parsed and mapped to MXCP scopes
   - Alternatively, accept pre-mapped scopes directly from proxy
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

**Goal**: Production-grade secure storage.

**Tasks**:
1. Implement additional `SecretProvider` backends:
   - macOS Keychain
   - HashiCorp Vault
   - AWS KMS (stretch)
2. Add token rotation tooling:
   - CLI command to rotate encryption keys
   - Automatic re-encryption of stored tokens
3. Add admin CLI commands:
   - `mxcp auth list-sessions` showing active sessions (no secrets)
   - `mxcp auth revoke --session <id>` to invalidate sessions
   - `mxcp auth cleanup` to purge expired data
4. Add audit events for:
   - Session creation and revocation
   - Token refresh attempts
   - Authentication failures
5. Add tests for key rotation and admin operations

**Outcome**: Encrypted storage with key rotation; admin visibility and control.

---

### Phase 9: Admin Tooling

**Goal**: Operational visibility into auth state.

**Tasks**:
1. Add admin API endpoints (via admin socket):
   - List active sessions (count, providers, expiry)
   - Revoke session by ID
   - View configured scopes and mappings
2. Add CLI commands wrapping admin API
3. Add health check endpoint reporting auth subsystem status
4. Document admin operations and troubleshooting procedures

**Outcome**: Operators can inspect and manage auth state.

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
3. Add migration guide for existing deployments
4. Add troubleshooting section for common issues

**Outcome**: Builders can configure any auth scenario from docs.

---

### Phase 11: Rollout and Migration

**Goal**: Safe migration path for existing users.

**Tasks**:
1. Feature flag new auth system (e.g., `auth.version: 2`)
2. Support running both systems during transition
3. Provide migration script for:
   - Converting existing SQLite data to new schema
   - Hashing existing tokens
   - Encrypting provider tokens
4. Communicate breaking changes:
   - New required config fields
   - Token format changes (existing tokens invalidated)
   - Persistence path changes if any
5. Deprecation timeline for legacy auth code

**Outcome**: Existing deployments can migrate safely.

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
- Configures persistence paths and secret providers

---

## Success Criteria

- Single `AuthService` entry point replaces current tangled architecture
- Provider tokens accessible and auto-refreshed for endpoint code
- Proxy mode working with signature validation
- Per-endpoint scope enforcement operational
- All tokens encrypted at rest
- Migration path documented and tested
- No regressions in existing OAuth flows


```

```markdown
# MXCP Authentication Redesign Plan

## Overview

This document outlines the implementation plan for overhauling MXCP's authentication system. The goals are:

- Single `AuthService` entry point for all transports
- Secure token and session storage with refresh support
- Access to upstream provider tokens for calling external APIs
- Proxy/header-trust mode for deployments behind SSO-aware reverse proxies
- Clear scope and entitlement model consumable by CEL policies and endpoint annotations
- Strict separation between SDK (reusable, well-typed) and server (config loading, FastMCP wiring)

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

**Goal**: Introduce `AuthService` abstraction without changing behavior.

**Tasks**:
1. Create `mxcp.sdk.auth.service` module with `AuthService` class
2. Define `from_config(auth_config, transport_config)` factory accepting only SDK models
3. Add `register_routes(fastmcp)` method that installs existing callback and well-known endpoints
4. Add `build_middleware()` method returning current `AuthenticationMiddleware`
5. Refactor `RAWMCP` to instantiate `AuthService` instead of managing handler/server/middleware directly
6. Server layer responsible for translating `UserAuthConfigModel` to SDK models before calling factory
7. Add comprehensive tests for service instantiation and route registration

**Outcome**: Single entry point for auth; internal structure unchanged.

---

### Phase 2: Session and Token Infrastructure

**Goal**: Proper session management with secure token storage.

**Tasks**:
1. Create `mxcp.sdk.auth.sessions` package with:
   - `SessionManager` class for issuing MXCP access and refresh tokens
   - `Session` dataclass holding session ID, user context, provider grants, expiry
2. Create `mxcp.sdk.auth.storage` package with:
   - `TokenStore` protocol defining CRUD operations (backend-agnostic)
   - `SqliteTokenStore` implementation (default backend):
     - Hash MXCP tokens before storage (one-way)
     - Encrypt provider tokens using Fernet with key from config
     - Encryption key resolved via existing config resolvers (supports `vault://`, `op://`, `${ENV}`)
3. Update middleware to:
   - Extract bearer token and verify via `SessionManager`
   - Hydrate `UserContext` from session without accessing private mappings
4. Update provider callbacks to store grants via `SessionManager`
5. Add background cleanup job for expired sessions and tokens
6. Migrate existing SQLite schema; provide data migration tooling

**Outcome**: Clean session abstraction; encrypted storage; no private field access.

---

### Phase 3: Provider Adapter Refactor

**Goal**: Thin provider adapters that only talk to IdPs.

**Tasks**:
1. Define `ProviderAdapter` protocol with methods:
   - `build_authorize_url(request)` returning authorization URL
   - `exchange_code(code, state)` returning `ExternalGrantResult`
   - `refresh(grant)` returning `ExternalGrantResult`
   - `fetch_user_context(access_token)` returning `UserContextModel`
2. Define `ExternalGrantResult` dataclass with:
   - Access token, refresh token, expiry timestamp
   - Raw profile data, provider scopes
3. Convert existing providers (Google, Keycloak, GitHub, Atlassian, Salesforce) to adapters:
   - Remove route registration logic
   - Remove persistence calls
   - Remove state storage (move to `SessionManager`)
4. Update `AuthService` to:
   - Own single callback route (e.g., `/auth/oauth/callback`)
   - Dispatch to appropriate adapter based on session state
   - Store grants via `SessionManager`
5. Add tests for each provider adapter in isolation

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

**Outcome**: Long-lived sessions; provider tokens stay fresh; endpoints can call external APIs.

---

### Phase 5: Scope and Mapping Layer

**Goal**: Translate IdP claims to MXCP entitlements; enforce per endpoint.

**Tasks**:
1. Extend `UserContextModel` with:
   - `mxcp_scopes: set[str]` for internal entitlements
   - `provider_scopes: set[str]` for raw IdP scopes
2. Create `ScopeMapper` class:
   - Accepts mapping configuration (claim type → scope mappings)
   - Given provider claims (scopes, groups, custom attributes) returns MXCP scopes
   - Supports multiple strategies: direct passthrough, group mapping, regex patterns
3. Define mapping config schema in SDK models:
   - `ClaimMappingConfigModel` with source type, claim name, scope mappings
4. Update `AuthService` to run `ScopeMapper` after authentication
5. Update middleware to:
   - Check global `required_scopes` from config
   - Accept endpoint-specific scope requirements as parameter
   - Reject requests missing required scopes
6. Surface `user_context.mxcp_scopes` to CEL policy engine
7. Add tests for mapping scenarios: groups to scopes, passthrough, multiple claims

**Outcome**: Stable MXCP entitlement vocabulary; enforceable per endpoint.

---

### Phase 6: Endpoint and Policy Integration

**Goal**: Per-endpoint scope requirements; CEL integration.

**Tasks**:
1. Extend endpoint YAML schema to accept scope annotations:
   - Under `annotations.scopes` list required MXCP scopes
2. Update endpoint loader to index all referenced scopes across endpoints
3. Update execution wrapper to:
   - Read endpoint scope requirements from definition
   - Pass requirements to middleware for enforcement
4. Add CEL helper functions:
   - `user_has_scope(scope_name)` checking `user_context.mxcp_scopes`
   - `user_has_provider_scope(scope_name)` checking raw provider scopes
5. Update policy enforcer to leverage new context fields
6. Optional: Add validation warning for undefined scopes in endpoints
7. Add tests for endpoint-level scope enforcement and CEL integration

**Outcome**: Builders define scopes per endpoint; policies can reference them.

---

### Phase 7: Proxy and Header Mode

**Goal**: Support deployments behind SSO-aware reverse proxies.

**Tasks**:
1. Define `ProxyAuthConfigModel` in SDK with:
   - Header names for user ID, username, email, scopes
   - Optional upstream token header for passthrough
   - Signature validation settings (header name, secret env, algorithm)
   - Optional mTLS requirement flag
2. Implement `ProxyAuthAdapter`:
   - Reads configured headers from request
   - Validates signature (HMAC) or mTLS if configured
   - Constructs `UserContextModel` from headers
   - Extracts upstream token if present
3. Integrate with `ScopeMapper`:
   - Scope header value parsed and mapped to MXCP scopes
   - Alternatively, accept pre-mapped scopes directly from proxy
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

**Goal**: Production-grade secure storage.

**Tasks**:
1. Implement additional `SecretProvider` backends:
   - macOS Keychain
   - HashiCorp Vault
   - AWS KMS (stretch)
2. Add token rotation tooling:
   - CLI command to rotate encryption keys
   - Automatic re-encryption of stored tokens
3. Add admin CLI commands:
   - `mxcp auth list-sessions` showing active sessions (no secrets)
   - `mxcp auth revoke --session <id>` to invalidate sessions
   - `mxcp auth cleanup` to purge expired data
4. Add audit events for:
   - Session creation and revocation
   - Token refresh attempts
   - Authentication failures
5. Add tests for key rotation and admin operations

**Outcome**: Encrypted storage with key rotation; admin visibility and control.

---

### Phase 9: Admin Tooling

**Goal**: Operational visibility into auth state.

**Tasks**:
1. Add admin API endpoints (via admin socket):
   - List active sessions (count, providers, expiry)
   - Revoke session by ID
   - View configured scopes and mappings
3. Ensure health check endpoint reporting auth subsystem status
4. Document admin operations and troubleshooting procedures

**Outcome**: Operators can inspect and manage auth state.

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
3. Add migration guide for existing deployments
4. Add troubleshooting section for common issues

**Outcome**: Builders can configure any auth scenario from docs.

---

### Phase 11: Rollout and Migration

**Goal**: Safe migration path for existing users.

**Tasks**:
1. Feature flag new auth system (e.g., `auth.version: 2`)
2. Support running both systems during transition
3. Provide migration script for:
   - Converting existing SQLite data to new schema
   - Hashing existing tokens
   - Encrypting provider tokens
4. Communicate breaking changes:
   - New required config fields
   - Token format changes (existing tokens invalidated)
   - Persistence path changes if any
5. Deprecation timeline for legacy auth code

**Outcome**: Existing deployments can migrate safely.

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
- Configures persistence paths and secret providers

---

## Success Criteria

- Single `AuthService` entry point replaces current tangled architecture
- Provider tokens accessible and auto-refreshed for endpoint code
- Proxy mode working with signature validation
- Per-endpoint scope enforcement operational
- All tokens encrypted at rest
- Migration path documented and tested
- No regressions in existing OAuth flows


```

```markdown
# MXCP Authentication Redesign Plan

## Overview

This document outlines the implementation plan for overhauling MXCP's authentication system. The goals are:

- Single `AuthService` entry point for all transports
- Secure token and session storage with refresh support
- Access to upstream provider tokens for calling external APIs
- Proxy/header-trust mode for deployments behind SSO-aware reverse proxies
- Clear scope and entitlement model consumable by CEL policies and endpoint annotations
- Strict separation between SDK (reusable, well-typed) and server (config loading, FastMCP wiring)

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

**Goal**: Introduce `AuthService` abstraction without changing behavior.

**Tasks**:
1. Create `mxcp.sdk.auth.service` module with `AuthService` class
2. Define `from_config(auth_config, transport_config)` factory accepting only SDK models
3. Add `register_routes(fastmcp)` method that installs existing callback and well-known endpoints
4. Add `build_middleware()` method returning current `AuthenticationMiddleware`
5. Refactor `RAWMCP` to instantiate `AuthService` instead of managing handler/server/middleware directly
6. Server layer responsible for translating `UserAuthConfigModel` to SDK models before calling factory
7. Add comprehensive tests for service instantiation and route registration

**Outcome**: Single entry point for auth; internal structure unchanged.

---

### Phase 2: Session and Token Infrastructure

**Goal**: Proper session management with secure token storage.

**Tasks**:
1. Create `mxcp.sdk.auth.sessions` package with:
   - `SessionManager` class for issuing MXCP access and refresh tokens
   - `Session` dataclass holding session ID, user context, provider grants, expiry
2. Create `mxcp.sdk.auth.storage` package with:
   - `TokenStore` protocol defining CRUD operations (backend-agnostic)
   - `SqliteTokenStore` implementation (default backend):
     - Hash MXCP tokens before storage (one-way)
     - Encrypt provider tokens using Fernet with key from config
     - Encryption key resolved via existing config resolvers (supports `vault://`, `op://`, `${ENV}`)
3. Update middleware to:
   - Extract bearer token and verify via `SessionManager`
   - Hydrate `UserContext` from session without accessing private mappings
4. Update provider callbacks to store grants via `SessionManager`
5. Add background cleanup job for expired sessions and tokens
6. Migrate existing SQLite schema; provide data migration tooling

**Outcome**: Clean session abstraction; encrypted storage; no private field access.

---

### Phase 3: Provider Adapter Refactor

**Goal**: Thin provider adapters that only talk to IdPs.

**Tasks**:
1. Define `ProviderAdapter` protocol with methods:
   - `build_authorize_url(request)` returning authorization URL
   - `exchange_code(code, state)` returning `ExternalGrantResult`
   - `refresh(grant)` returning `ExternalGrantResult`
   - `fetch_user_context(access_token)` returning `UserContextModel`
2. Define `ExternalGrantResult` dataclass with:
   - Access token, refresh token, expiry timestamp
   - Raw profile data, provider scopes
3. Convert existing providers (Google, Keycloak, GitHub, Atlassian, Salesforce) to adapters:
   - Remove route registration logic
   - Remove persistence calls
   - Remove state storage (move to `SessionManager`)
4. Update `AuthService` to:
   - Own single callback route (e.g., `/auth/oauth/callback`)
   - Dispatch to appropriate adapter based on session state
   - Store grants via `SessionManager`
5. Add tests for each provider adapter in isolation

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

**Outcome**: Long-lived sessions; provider tokens stay fresh; endpoints can call external APIs.

---

### Phase 5: Scope and Mapping Layer

**Goal**: Translate IdP claims to MXCP entitlements; enforce per endpoint.

**Tasks**:
1. Extend `UserContextModel` with:
   - `mxcp_scopes: set[str]` for internal entitlements
   - `provider_scopes: set[str]` for raw IdP scopes
2. Create `ScopeMapper` class:
   - Accepts mapping configuration (claim type → scope mappings)
   - Given provider claims (scopes, groups, custom attributes) returns MXCP scopes
   - Supports multiple strategies: direct passthrough, group mapping, regex patterns
3. Define mapping config schema in SDK models:
   - `ClaimMappingConfigModel` with source type, claim name, scope mappings
4. Update `AuthService` to run `ScopeMapper` after authentication
5. Update middleware to:
   - Check global `required_scopes` from config
   - Accept endpoint-specific scope requirements as parameter
   - Reject requests missing required scopes
6. Surface `user_context.mxcp_scopes` to CEL policy engine
7. Add tests for mapping scenarios: groups to scopes, passthrough, multiple claims

**Outcome**: Stable MXCP entitlement vocabulary; enforceable per endpoint.

---

### Phase 6: Endpoint and Policy Integration

**Goal**: Per-endpoint scope requirements; CEL integration.

**Tasks**:
1. Extend endpoint YAML schema to accept scope annotations:
   - Under `annotations.scopes` list required MXCP scopes
2. Update endpoint loader to index all referenced scopes across endpoints
3. Update execution wrapper to:
   - Read endpoint scope requirements from definition
   - Pass requirements to middleware for enforcement
4. Add CEL helper functions:
   - `user_has_scope(scope_name)` checking `user_context.mxcp_scopes`
   - `user_has_provider_scope(scope_name)` checking raw provider scopes
5. Update policy enforcer to leverage new context fields
6. Optional: Add validation warning for undefined scopes in endpoints
7. Add tests for endpoint-level scope enforcement and CEL integration

**Outcome**: Builders define scopes per endpoint; policies can reference them.

---

### Phase 7: Proxy and Header Mode

**Goal**: Support deployments behind SSO-aware reverse proxies.

**Tasks**:
1. Define `ProxyAuthConfigModel` in SDK with:
   - Header names for user ID, username, email, scopes
   - Optional upstream token header for passthrough
   - Signature validation settings (header name, secret env, algorithm)
   - Optional mTLS requirement flag
2. Implement `ProxyAuthAdapter`:
   - Reads configured headers from request
   - Validates signature (HMAC) or mTLS if configured
   - Constructs `UserContextModel` from headers
   - Extracts upstream token if present
3. Integrate with `ScopeMapper`:
   - Scope header value parsed and mapped to MXCP scopes
   - Alternatively, accept pre-mapped scopes directly from proxy
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
1. Implement additional `TokenStore` backends (each handles its own security):
   - `VaultTokenStore`: Stores tokens directly in HashiCorp Vault (Vault handles encryption)
   - `AwsSecretsManagerTokenStore`: Stores in AWS Secrets Manager (stretch goal)
2. For SQLite backend, add key rotation tooling:
   - CLI command to rotate encryption keys
   - Automatic re-encryption of stored tokens
3. Add admin CLI commands:
   - `mxcp auth list-sessions` showing active sessions (no secrets)
   - `mxcp auth revoke --session <id>` to invalidate sessions
   - `mxcp auth cleanup` to purge expired data
4. Add audit events for:
   - Session creation and revocation
   - Token refresh attempts
   - Authentication failures
5. Add tests for each backend and admin operations

**Outcome**: Multiple storage backends; admin visibility and control.

---

### Phase 9: Admin Tooling

**Goal**: Operational visibility into auth state.

**Tasks**:
1. Add admin API endpoints (via admin socket):
   - List active sessions (count, providers, expiry)
   - Revoke session by ID
   - View configured scopes and mappings
3. Ensure health check endpoint reports auth subsystem status(?)
4. Document admin operations and troubleshooting procedures

**Outcome**: Operators can inspect and manage auth state.

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
3. Add migration guide for existing deployments
4. Add troubleshooting section for common issues

**Outcome**: Builders can configure any auth scenario from docs.

---

### Phase 11: Rollout and Migration

**Goal**: Safe migration path for existing users.

**Tasks**:
1. Feature flag new auth system (e.g., `auth.version: 2`)
2. Support running both systems during transition
3. Provide migration script for:
   - Converting existing SQLite data to new schema
   - Hashing existing tokens
   - Encrypting provider tokens
4. Communicate breaking changes:
   - New required config fields
   - Token format changes (existing tokens invalidated)
   - Persistence path changes if any
5. Deprecation timeline for legacy auth code

**Outcome**: Existing deployments can migrate safely.

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
- Configures persistence paths and secret providers

---

## Success Criteria

- Single `AuthService` entry point replaces current tangled architecture
- Provider tokens accessible and auto-refreshed for endpoint code
- Proxy mode working with signature validation
- Per-endpoint scope enforcement operational
- All tokens encrypted at rest
- Migration path documented and tested
- No regressions in existing OAuth flows


```

```markdown
# MXCP Authentication Redesign Plan

## Overview

This document outlines the implementation plan for overhauling MXCP's authentication system. The goals are:

- Single `AuthService` entry point for all transports
- Secure token and session storage with refresh support
- Access to upstream provider tokens for calling external APIs
- Proxy/header-trust mode for deployments behind SSO-aware reverse proxies
- Clear scope and entitlement model consumable by CEL policies and endpoint annotations
- Strict separation between SDK (reusable, well-typed) and server (config loading, FastMCP wiring)

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

**Goal**: Introduce `AuthService` abstraction without changing behavior.

**Tasks**:
1. Create `mxcp.sdk.auth.service` module with `AuthService` class
2. Define `from_config(auth_config, transport_config)` factory accepting only SDK models
3. Add `register_routes(fastmcp)` method that installs existing callback and well-known endpoints
4. Add `build_middleware()` method returning current `AuthenticationMiddleware`
5. Refactor `RAWMCP` to instantiate `AuthService` instead of managing handler/server/middleware directly
6. Server layer responsible for translating `UserAuthConfigModel` to SDK models before calling factory
7. Add comprehensive tests for service instantiation and route registration

**Outcome**: Single entry point for auth; internal structure unchanged.

---

### Phase 2: Session and Token Infrastructure

**Goal**: Proper session management with secure token storage.

**Tasks**:
1. Create `mxcp.sdk.auth.sessions` package with:
   - `SessionManager` class for issuing MXCP access and refresh tokens
   - `Session` dataclass holding session ID, user context, provider grants, expiry
2. Create `mxcp.sdk.auth.storage` package with:
   - `TokenStore` protocol defining CRUD operations (backend-agnostic)
   - `SqliteTokenStore` implementation (default backend):
     - Hash MXCP tokens before storage (one-way)
     - Encrypt provider tokens using Fernet with key from config
     - Encryption key resolved via existing config resolvers (supports `vault://`, `op://`, `${ENV}`)
3. Update middleware to:
   - Extract bearer token and verify via `SessionManager`
   - Hydrate `UserContext` from session without accessing private mappings
4. Update provider callbacks to store grants via `SessionManager`
5. Add background cleanup job for expired sessions and tokens
6. Migrate existing SQLite schema; provide data migration tooling

**Outcome**: Clean session abstraction; encrypted storage; no private field access.

---

### Phase 3: Provider Adapter Refactor

**Goal**: Thin provider adapters that only talk to IdPs.

**Tasks**:
1. Define `ProviderAdapter` protocol with methods:
   - `build_authorize_url(request)` returning authorization URL
   - `exchange_code(code, state)` returning `ExternalGrantResult`
   - `refresh(grant)` returning `ExternalGrantResult`
   - `fetch_user_context(access_token)` returning `UserContextModel`
2. Define `ExternalGrantResult` dataclass with:
   - Access token, refresh token, expiry timestamp
   - Raw profile data, provider scopes
3. Convert existing providers (Google, Keycloak, GitHub, Atlassian, Salesforce) to adapters:
   - Remove route registration logic
   - Remove persistence calls
   - Remove state storage (move to `SessionManager`)
4. Update `AuthService` to:
   - Own single callback route (e.g., `/auth/oauth/callback`)
   - Dispatch to appropriate adapter based on session state
   - Store grants via `SessionManager`
5. Add tests for each provider adapter in isolation

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

**Outcome**: Long-lived sessions; provider tokens stay fresh; endpoints can call external APIs.

---

### Phase 5: Scope and Mapping Layer

**Goal**: Translate IdP claims to MXCP entitlements; enforce per endpoint.

**Tasks**:
1. Extend `UserContextModel` with:
   - `mxcp_scopes: set[str]` for internal entitlements
   - `provider_scopes: set[str]` for raw IdP scopes
2. Create `ScopeMapper` class:
   - Accepts mapping configuration (claim type → scope mappings)
   - Given provider claims (scopes, groups, custom attributes) returns MXCP scopes
   - Supports multiple strategies: direct passthrough, group mapping, regex patterns
3. Define mapping config schema in SDK models:
   - `ClaimMappingConfigModel` with source type, claim name, scope mappings
4. Update `AuthService` to run `ScopeMapper` after authentication
5. Update middleware to:
   - Check global `required_scopes` from config
   - Accept endpoint-specific scope requirements as parameter
   - Reject requests missing required scopes
6. Surface `user_context.mxcp_scopes` to CEL policy engine
7. Add tests for mapping scenarios: groups to scopes, passthrough, multiple claims

**Outcome**: Stable MXCP entitlement vocabulary; enforceable per endpoint.

---

### Phase 6: Endpoint and Policy Integration

**Goal**: Per-endpoint scope requirements; CEL integration.

**Tasks**:
1. Extend endpoint YAML schema to accept scope annotations:
   - Under `annotations.scopes` list required MXCP scopes
2. Update endpoint loader to index all referenced scopes across endpoints
3. Update execution wrapper to:
   - Read endpoint scope requirements from definition
   - Pass requirements to middleware for enforcement
4. Add CEL helper functions:
   - `user_has_scope(scope_name)` checking `user_context.mxcp_scopes`
   - `user_has_provider_scope(scope_name)` checking raw provider scopes
5. Update policy enforcer to leverage new context fields
6. Optional: Add validation warning for undefined scopes in endpoints
7. Add tests for endpoint-level scope enforcement and CEL integration

**Outcome**: Builders define scopes per endpoint; policies can reference them.

---

### Phase 7: Proxy and Header Mode

**Goal**: Support deployments behind SSO-aware reverse proxies.

**Tasks**:
1. Define `ProxyAuthConfigModel` in SDK with:
   - Header names for user ID, username, email, scopes
   - Optional upstream token header for passthrough
   - Signature validation settings (header name, secret env, algorithm)
   - Optional mTLS requirement flag
2. Implement `ProxyAuthAdapter`:
   - Reads configured headers from request
   - Validates signature (HMAC) or mTLS if configured
   - Constructs `UserContextModel` from headers
   - Extracts upstream token if present
3. Integrate with `ScopeMapper`:
   - Scope header value parsed and mapped to MXCP scopes
   - Alternatively, accept pre-mapped scopes directly from proxy
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
1. Implement additional `TokenStore` backends (each handles its own security):
   - `VaultTokenStore`: Stores tokens directly in HashiCorp Vault (Vault handles encryption)
   - `AwsSecretsManagerTokenStore`: Stores in AWS Secrets Manager (stretch goal)
2. For SQLite backend, add key rotation tooling:
   - CLI command to rotate encryption keys
   - Automatic re-encryption of stored tokens
3. Add admin CLI commands:
   - `mxcp auth list-sessions` showing active sessions (no secrets)
   - `mxcp auth revoke --session <id>` to invalidate sessions
   - `mxcp auth cleanup` to purge expired data
4. Add audit events for:
   - Session creation and revocation
   - Token refresh attempts
   - Authentication failures
5. Add tests for each backend and admin operations

**Outcome**: Multiple storage backends; admin visibility and control.

---

### Phase 9: Admin Tooling

**Goal**: Operational visibility into auth state.

**Tasks**:
1. Add admin API endpoints (via admin socket):
   - List active sessions (count, providers, expiry)
   - Revoke session by ID
   - View configured scopes and mappings
2. Ensure health check endpoint reports auth subsystem status(?)

**Outcome**: Operators can inspect and manage auth state.

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
3. Add migration guide for existing deployments
4. Add troubleshooting section for common issues

**Outcome**: Builders can configure any auth scenario from docs.

---

### Phase 11: Rollout and Migration

**Goal**: Safe migration path for existing users.

**Tasks**:
1. Feature flag new auth system (e.g., `auth.version: 2`)
2. Support running both systems during transition
3. Provide migration script for:
   - Converting existing SQLite data to new schema
   - Hashing existing tokens
   - Encrypting provider tokens
4. Communicate breaking changes:
   - New required config fields
   - Token format changes (existing tokens invalidated)
   - Persistence path changes if any
5. Deprecation timeline for legacy auth code

**Outcome**: Existing deployments can migrate safely.

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
- All tokens encrypted at rest
- Migration path documented and tested
- No regressions in existing OAuth flows


```

```markdown
# MXCP Authentication Redesign Plan

## Overview

This document outlines the implementation plan for overhauling MXCP's authentication system. The goals are:

- Single `AuthService` entry point for all transports
- Secure token and session storage with refresh support
- Access to upstream provider tokens for calling external APIs
- Proxy/header-trust mode for deployments behind SSO-aware reverse proxies
- Clear scope and entitlement model consumable by CEL policies and endpoint annotations
- Strict separation between SDK (reusable, well-typed) and server (config loading, FastMCP wiring)

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

**Goal**: Introduce `AuthService` abstraction without changing behavior.

**Tasks**:
1. Create `mxcp.sdk.auth.service` module with `AuthService` class
2. Define `from_config(auth_config, transport_config)` factory accepting only SDK models
3. Add `register_routes(fastmcp)` method that installs existing callback and well-known endpoints
4. Add `build_middleware()` method returning current `AuthenticationMiddleware`
5. Refactor `RAWMCP` to instantiate `AuthService` instead of managing handler/server/middleware directly
6. Server layer responsible for translating `UserAuthConfigModel` to SDK models before calling factory
7. Add comprehensive tests for service instantiation and route registration

**Outcome**: Single entry point for auth; internal structure unchanged.

---

### Phase 2: Session and Token Infrastructure

**Goal**: Proper session management with secure token storage.

**Tasks**:
1. Create `mxcp.sdk.auth.sessions` package with:
   - `SessionManager` class for issuing MXCP access and refresh tokens
   - `Session` dataclass holding session ID, user context, provider grants, expiry
2. Create `mxcp.sdk.auth.storage` package with:
   - `TokenStore` protocol defining CRUD operations (backend-agnostic)
   - `SqliteTokenStore` implementation (default backend):
     - Hash MXCP tokens before storage (one-way)
     - Encrypt provider tokens using Fernet with key from config
     - Encryption key resolved via existing config resolvers (supports `vault://`, `op://`, `${ENV}`)
3. Update middleware to:
   - Extract bearer token and verify via `SessionManager`
   - Hydrate `UserContext` from session without accessing private mappings
4. Update provider callbacks to store grants via `SessionManager`
5. Add background cleanup job for expired sessions and tokens
6. Migrate existing SQLite schema; provide data migration tooling

**Outcome**: Clean session abstraction; encrypted storage; no private field access.

---

### Phase 3: Provider Adapter Refactor

**Goal**: Thin provider adapters that only talk to IdPs.

**Tasks**:
1. Define `ProviderAdapter` protocol with methods:
   - `build_authorize_url(request)` returning authorization URL
   - `exchange_code(code, state)` returning `ExternalGrantResult`
   - `refresh(grant)` returning `ExternalGrantResult`
   - `fetch_user_context(access_token)` returning `UserContextModel`
2. Define `ExternalGrantResult` dataclass with:
   - Access token, refresh token, expiry timestamp
   - Raw profile data, provider scopes
3. Convert existing providers (Google, Keycloak, GitHub, Atlassian, Salesforce) to adapters:
   - Remove route registration logic
   - Remove persistence calls
   - Remove state storage (move to `SessionManager`)
4. Update `AuthService` to:
   - Own single callback route (e.g., `/auth/oauth/callback`)
   - Dispatch to appropriate adapter based on session state
   - Store grants via `SessionManager`
5. Add tests for each provider adapter in isolation

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

**Outcome**: Long-lived sessions; provider tokens stay fresh; endpoints can call external APIs.

---

### Phase 5: Scope and Mapping Layer

**Goal**: Translate IdP claims to MXCP entitlements; enforce per endpoint.

**Tasks**:
1. Extend `UserContextModel` with:
   - `mxcp_scopes: set[str]` for internal entitlements
   - `provider_scopes: set[str]` for raw IdP scopes
2. Create `ScopeMapper` class:
   - Accepts mapping configuration (claim type → scope mappings)
   - Given provider claims (scopes, groups, custom attributes) returns MXCP scopes
   - Supports multiple strategies: direct passthrough, group mapping, regex patterns
3. Define mapping config schema in SDK models:
   - `ClaimMappingConfigModel` with source type, claim name, scope mappings
4. Update `AuthService` to run `ScopeMapper` after authentication
5. Update middleware to:
   - Check global `required_scopes` from config
   - Accept endpoint-specific scope requirements as parameter
   - Reject requests missing required scopes
6. Surface `user_context.mxcp_scopes` to CEL policy engine
7. Add tests for mapping scenarios: groups to scopes, passthrough, multiple claims

**Outcome**: Stable MXCP entitlement vocabulary; enforceable per endpoint.

---

### Phase 6: Endpoint and Policy Integration

**Goal**: Per-endpoint scope requirements; CEL integration.

**Tasks**:
1. Extend endpoint YAML schema to accept scope annotations:
   - Under `annotations.scopes` list required MXCP scopes
2. Update endpoint loader to index all referenced scopes across endpoints
3. Update execution wrapper to:
   - Read endpoint scope requirements from definition
   - Pass requirements to middleware for enforcement
4. Add CEL helper functions:
   - `user_has_scope(scope_name)` checking `user_context.mxcp_scopes`
   - `user_has_provider_scope(scope_name)` checking raw provider scopes
5. Update policy enforcer to leverage new context fields
6. Optional: Add validation warning for undefined scopes in endpoints
7. Add tests for endpoint-level scope enforcement and CEL integration

**Outcome**: Builders define scopes per endpoint; policies can reference them.

---

### Phase 7: Proxy and Header Mode

**Goal**: Support deployments behind SSO-aware reverse proxies.

**Tasks**:
1. Define `ProxyAuthConfigModel` in SDK with:
   - Header names for user ID, username, email, scopes
   - Optional upstream token header for passthrough
   - Signature validation settings (header name, secret env, algorithm)
   - Optional mTLS requirement flag
2. Implement `ProxyAuthAdapter`:
   - Reads configured headers from request
   - Validates signature (HMAC) or mTLS if configured
   - Constructs `UserContextModel` from headers
   - Extracts upstream token if present
3. Integrate with `ScopeMapper`:
   - Scope header value parsed and mapped to MXCP scopes
   - Alternatively, accept pre-mapped scopes directly from proxy
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
1. Implement additional `TokenStore` backends (each handles its own security):
   - `VaultTokenStore`: Stores tokens directly in HashiCorp Vault (Vault handles encryption)
   - `AwsSecretsManagerTokenStore`: Stores in AWS Secrets Manager (stretch goal)
2. For SQLite backend, add key rotation tooling:
   - CLI command to rotate encryption keys
   - Automatic re-encryption of stored tokens
3. Add admin CLI commands:
   - `mxcp auth list-sessions` showing active sessions (no secrets)
   - `mxcp auth revoke --session <id>` to invalidate sessions
   - `mxcp auth cleanup` to purge expired data
4. Add audit events for:
   - Session creation and revocation
   - Token refresh attempts
   - Authentication failures
5. Add tests for each backend and admin operations

**Outcome**: Multiple storage backends; admin visibility and control.

---

### Phase 9: Admin Tooling

**Goal**: Operational visibility into auth state.

**Tasks**:
1. Add admin API endpoints (via admin socket):
   - List active sessions (count, providers, expiry)
   - Revoke session by ID
   - View configured scopes and mappings
2. Ensure health check endpoint reports auth subsystem status(?)

**Outcome**: Operators can inspect and manage auth state.

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
3. Add migration guide for existing deployments
4. Add troubleshooting section for common issues

**Outcome**: Builders can configure any auth scenario from docs.

---

### Phase 11: Rollout and Migration

**Goal**: Safe migration path for existing users.

**Tasks**:
1. Feature flag new auth system (e.g., `auth.version: 2`)
2. Support running both systems during transition
3. Provide migration script for:
   - Converting existing SQLite data to new schema
   - Hashing existing tokens
   - Encrypting provider tokens
4. Communicate breaking changes:
   - New required config fields
   - Token format changes (existing tokens invalidated)
   - Persistence path changes if any
5. Deprecation timeline for legacy auth code

**Outcome**: Existing deployments can migrate safely.

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


```

Updated the plan. Key changes:

1. **Removed `SecretProvider`** from Target Architecture – no longer a separate abstraction

2. **Phase 2** now clarifies that encryption is per-backend:
   - `SqliteTokenStore` uses Fernet with encryption key from config
   - Key resolved via existing resolvers (`vault://`, `op://`, `${ENV}`)

3. **Phase 8** now focuses on alternative `TokenStore` backends:
   - `VaultTokenStore` stores directly in Vault (Vault handles encryption)
   - `AwsSecretsManagerTokenStore` as stretch goal
   - Key rotation tooling only applies to SQLite backend

4. **Success Criteria** updated to reflect "secured at rest" via encryption OR delegated backends

---

**User**

does the plan - and your understanding - make clear that we do have an sdk auth and existing implementation that we will need to refactor/

---

**Cursor**

You're right – the plan reads a bit like greenfield development when in reality we have substantial existing code in `mxcp.sdk.auth` that needs to be refactored:

**Existing SDK auth code**:
- `base.py` – `ExternalOAuthHandler` protocol, `GeneralOAuthAuthorizationServer`
- `middleware.py` – `AuthenticationMiddleware`
- `persistence.py` – `SQLiteAuthPersistence`, `TokenStore` abstractions
- `providers/` – Google, Keycloak, GitHub, Atlassian, Salesforce handlers
- `models.py` – `UserContextModel`, config models, etc.
- `context.py` – user context thread-local management

The plan should make clear we're:
1. **Keeping** the provider implementations (refactoring them into thinner adapters)
2. **Evolving** persistence (already SQLite-based, adding encryption + alternative backends)
3. **Extracting** `SessionManager` from the tangled `GeneralOAuthAuthorizationServer`
4. **Wrapping** existing pieces with `AuthService` as the new entry point

Want me to update the plan to add a "Current SDK Auth Inventory" section that explicitly lists what exists and how each piece maps to the target architecture?

---

**User**

yes

---

**Cursor**

```markdown
# MXCP Authentication Redesign Plan

## Overview

This document outlines the implementation plan for overhauling MXCP's authentication system. The goals are:

- Single `AuthService` entry point for all transports
- Secure token and session storage with refresh support
- Access to upstream provider tokens for calling external APIs
- Proxy/header-trust mode for deployments behind SSO-aware reverse proxies
- Clear scope and entitlement model consumable by CEL policies and endpoint annotations
- Strict separation between SDK (reusable, well-typed) and server (config loading, FastMCP wiring)

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
| `models.py` | `UserContextModel`, provider configs, `StateMetaModel`, etc. | Extend `UserContextModel` with `mxcp_scopes`; add mapping config models |
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

**Goal**: Introduce `AuthService` abstraction without changing behavior.

**Tasks**:
1. Create `mxcp.sdk.auth.service` module with `AuthService` class
2. Define `from_config(auth_config, transport_config)` factory accepting only SDK models
3. Add `register_routes(fastmcp)` method that installs existing callback and well-known endpoints
4. Add `build_middleware()` method returning current `AuthenticationMiddleware`
5. Refactor `RAWMCP` to instantiate `AuthService` instead of managing handler/server/middleware directly
6. Server layer responsible for translating `UserAuthConfigModel` to SDK models before calling factory
7. Add comprehensive tests for service instantiation and route registration

**Outcome**: Single entry point for auth; internal structure unchanged.

---

### Phase 2: Session and Token Infrastructure

**Goal**: Proper session management with secure token storage.

**Tasks**:
1. Create `mxcp.sdk.auth.sessions` package with:
   - `SessionManager` class for issuing MXCP access and refresh tokens
   - `Session` dataclass holding session ID, user context, provider grants, expiry
2. Create `mxcp.sdk.auth.storage` package with:
   - `TokenStore` protocol defining CRUD operations (backend-agnostic)
   - `SqliteTokenStore` implementation (default backend):
     - Hash MXCP tokens before storage (one-way)
     - Encrypt provider tokens using Fernet with key from config
     - Encryption key resolved via existing config resolvers (supports `vault://`, `op://`, `${ENV}`)
3. Update middleware to:
   - Extract bearer token and verify via `SessionManager`
   - Hydrate `UserContext` from session without accessing private mappings
4. Update provider callbacks to store grants via `SessionManager`
5. Add background cleanup job for expired sessions and tokens
6. Migrate existing SQLite schema; provide data migration tooling

**Outcome**: Clean session abstraction; encrypted storage; no private field access.

---

### Phase 3: Provider Adapter Refactor

**Goal**: Thin provider adapters that only talk to IdPs.

**Tasks**:
1. Define `ProviderAdapter` protocol with methods:
   - `build_authorize_url(request)` returning authorization URL
   - `exchange_code(code, state)` returning `ExternalGrantResult`
   - `refresh(grant)` returning `ExternalGrantResult`
   - `fetch_user_context(access_token)` returning `UserContextModel`
2. Define `ExternalGrantResult` dataclass with:
   - Access token, refresh token, expiry timestamp
   - Raw profile data, provider scopes
3. Convert existing providers (Google, Keycloak, GitHub, Atlassian, Salesforce) to adapters:
   - Remove route registration logic
   - Remove persistence calls
   - Remove state storage (move to `SessionManager`)
4. Update `AuthService` to:
   - Own single callback route (e.g., `/auth/oauth/callback`)
   - Dispatch to appropriate adapter based on session state
   - Store grants via `SessionManager`
5. Add tests for each provider adapter in isolation

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

**Outcome**: Long-lived sessions; provider tokens stay fresh; endpoints can call external APIs.

---

### Phase 5: Scope and Mapping Layer

**Goal**: Translate IdP claims to MXCP entitlements; enforce per endpoint.

**Tasks**:
1. Extend `UserContextModel` with:
   - `mxcp_scopes: set[str]` for internal entitlements
   - `provider_scopes: set[str]` for raw IdP scopes
2. Create `ScopeMapper` class:
   - Accepts mapping configuration (claim type → scope mappings)
   - Given provider claims (scopes, groups, custom attributes) returns MXCP scopes
   - Supports multiple strategies: direct passthrough, group mapping, regex patterns
3. Define mapping config schema in SDK models:
   - `ClaimMappingConfigModel` with source type, claim name, scope mappings
4. Update `AuthService` to run `ScopeMapper` after authentication
5. Update middleware to:
   - Check global `required_scopes` from config
   - Accept endpoint-specific scope requirements as parameter
   - Reject requests missing required scopes
6. Surface `user_context.mxcp_scopes` to CEL policy engine
7. Add tests for mapping scenarios: groups to scopes, passthrough, multiple claims

**Outcome**: Stable MXCP entitlement vocabulary; enforceable per endpoint.

---

### Phase 6: Endpoint and Policy Integration

**Goal**: Per-endpoint scope requirements; CEL integration.

**Tasks**:
1. Extend endpoint YAML schema to accept scope annotations:
   - Under `annotations.scopes` list required MXCP scopes
2. Update endpoint loader to index all referenced scopes across endpoints
3. Update execution wrapper to:
   - Read endpoint scope requirements from definition
   - Pass requirements to middleware for enforcement
4. Add CEL helper functions:
   - `user_has_scope(scope_name)` checking `user_context.mxcp_scopes`
   - `user_has_provider_scope(scope_name)` checking raw provider scopes
5. Update policy enforcer to leverage new context fields
6. Optional: Add validation warning for undefined scopes in endpoints
7. Add tests for endpoint-level scope enforcement and CEL integration

**Outcome**: Builders define scopes per endpoint; policies can reference them.

---

### Phase 7: Proxy and Header Mode

**Goal**: Support deployments behind SSO-aware reverse proxies.

**Tasks**:
1. Define `ProxyAuthConfigModel` in SDK with:
   - Header names for user ID, username, email, scopes
   - Optional upstream token header for passthrough
   - Signature validation settings (header name, secret env, algorithm)
   - Optional mTLS requirement flag
2. Implement `ProxyAuthAdapter`:
   - Reads configured headers from request
   - Validates signature (HMAC) or mTLS if configured
   - Constructs `UserContextModel` from headers
   - Extracts upstream token if present
3. Integrate with `ScopeMapper`:
   - Scope header value parsed and mapped to MXCP scopes
   - Alternatively, accept pre-mapped scopes directly from proxy
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
1. Implement additional `TokenStore` backends (each handles its own security):
   - `VaultTokenStore`: Stores tokens directly in HashiCorp Vault (Vault handles encryption)
   - `AwsSecretsManagerTokenStore`: Stores in AWS Secrets Manager (stretch goal)
2. For SQLite backend, add key rotation tooling:
   - CLI command to rotate encryption keys
   - Automatic re-encryption of stored tokens
3. Add admin CLI commands:
   - `mxcp auth list-sessions` showing active sessions (no secrets)
   - `mxcp auth revoke --session <id>` to invalidate sessions
   - `mxcp auth cleanup` to purge expired data
4. Add audit events for:
   - Session creation and revocation
   - Token refresh attempts
   - Authentication failures
5. Add tests for each backend and admin operations

**Outcome**: Multiple storage backends; admin visibility and control.

---

### Phase 9: Admin Tooling

**Goal**: Operational visibility into auth state.

**Tasks**:
1. Add admin API endpoints (via admin socket):
   - List active sessions (count, providers, expiry)
   - Revoke session by ID
   - View configured scopes and mappings
2. Ensure health check endpoint reports auth subsystem status(?)

**Outcome**: Operators can inspect and manage auth state.

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
3. Add migration guide for existing deployments
4. Add troubleshooting section for common issues

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


```

```markdown
# MXCP Authentication Redesign Plan

## Overview

This document outlines the implementation plan for overhauling MXCP's authentication system. The goals are:

- Single `AuthService` entry point for all transports
- Secure token and session storage with refresh support
- Access to upstream provider tokens for calling external APIs
- Proxy/header-trust mode for deployments behind SSO-aware reverse proxies
- Clear scope and entitlement model consumable by CEL policies and endpoint annotations
- Strict separation between SDK (reusable, well-typed) and server (config loading, FastMCP wiring)

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
| `models.py` | `UserContextModel`, provider configs, `StateMetaModel`, etc. | Extend `UserContextModel` with `mxcp_scopes`; add mapping config models |
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
8. Add comprehensive tests for service instantiation and route registration

**Outcome**: Single entry point for auth; existing internals unchanged but now encapsulated.

---

### Phase 2: Session and Token Infrastructure

**Goal**: Proper session management with secure token storage.

**Tasks**:
1. Create `mxcp.sdk.auth.sessions` package with:
   - `SessionManager` class for issuing MXCP access and refresh tokens
   - `Session` dataclass holding session ID, user context, provider grants, expiry
2. Create `mxcp.sdk.auth.storage` package with:
   - `TokenStore` protocol defining CRUD operations (backend-agnostic)
   - `SqliteTokenStore` implementation (default backend):
     - Hash MXCP tokens before storage (one-way)
     - Encrypt provider tokens using Fernet with key from config
     - Encryption key resolved via existing config resolvers (supports `vault://`, `op://`, `${ENV}`)
3. Update middleware to:
   - Extract bearer token and verify via `SessionManager`
   - Hydrate `UserContext` from session without accessing private mappings
4. Update provider callbacks to store grants via `SessionManager`
5. Add background cleanup job for expired sessions and tokens
6. Migrate existing SQLite schema; provide data migration tooling

**Outcome**: Clean session abstraction; encrypted storage; no private field access.

---

### Phase 3: Provider Adapter Refactor

**Goal**: Thin provider adapters that only talk to IdPs.

**Tasks**:
1. Define `ProviderAdapter` protocol with methods:
   - `build_authorize_url(request)` returning authorization URL
   - `exchange_code(code, state)` returning `ExternalGrantResult`
   - `refresh(grant)` returning `ExternalGrantResult`
   - `fetch_user_context(access_token)` returning `UserContextModel`
2. Define `ExternalGrantResult` dataclass with:
   - Access token, refresh token, expiry timestamp
   - Raw profile data, provider scopes
3. Convert existing providers (Google, Keycloak, GitHub, Atlassian, Salesforce) to adapters:
   - Remove route registration logic
   - Remove persistence calls
   - Remove state storage (move to `SessionManager`)
4. Update `AuthService` to:
   - Own single callback route (e.g., `/auth/oauth/callback`)
   - Dispatch to appropriate adapter based on session state
   - Store grants via `SessionManager`
5. Add tests for each provider adapter in isolation

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

**Outcome**: Long-lived sessions; provider tokens stay fresh; endpoints can call external APIs.

---

### Phase 5: Scope and Mapping Layer

**Goal**: Translate IdP claims to MXCP entitlements; enforce per endpoint.

**Tasks**:
1. Extend `UserContextModel` with:
   - `mxcp_scopes: set[str]` for internal entitlements
   - `provider_scopes: set[str]` for raw IdP scopes
2. Create `ScopeMapper` class:
   - Accepts mapping configuration (claim type → scope mappings)
   - Given provider claims (scopes, groups, custom attributes) returns MXCP scopes
   - Supports multiple strategies: direct passthrough, group mapping, regex patterns
3. Define mapping config schema in SDK models:
   - `ClaimMappingConfigModel` with source type, claim name, scope mappings
4. Update `AuthService` to run `ScopeMapper` after authentication
5. Update middleware to:
   - Check global `required_scopes` from config
   - Accept endpoint-specific scope requirements as parameter
   - Reject requests missing required scopes
6. Surface `user_context.mxcp_scopes` to CEL policy engine
7. Add tests for mapping scenarios: groups to scopes, passthrough, multiple claims

**Outcome**: Stable MXCP entitlement vocabulary; enforceable per endpoint.

---

### Phase 6: Endpoint and Policy Integration

**Goal**: Per-endpoint scope requirements; CEL integration.

**Tasks**:
1. Extend endpoint YAML schema to accept scope annotations:
   - Under `annotations.scopes` list required MXCP scopes
2. Update endpoint loader to index all referenced scopes across endpoints
3. Update execution wrapper to:
   - Read endpoint scope requirements from definition
   - Pass requirements to middleware for enforcement
4. Add CEL helper functions:
   - `user_has_scope(scope_name)` checking `user_context.mxcp_scopes`
   - `user_has_provider_scope(scope_name)` checking raw provider scopes
5. Update policy enforcer to leverage new context fields
6. Optional: Add validation warning for undefined scopes in endpoints
7. Add tests for endpoint-level scope enforcement and CEL integration

**Outcome**: Builders define scopes per endpoint; policies can reference them.

---

### Phase 7: Proxy and Header Mode

**Goal**: Support deployments behind SSO-aware reverse proxies.

**Tasks**:
1. Define `ProxyAuthConfigModel` in SDK with:
   - Header names for user ID, username, email, scopes
   - Optional upstream token header for passthrough
   - Signature validation settings (header name, secret env, algorithm)
   - Optional mTLS requirement flag
2. Implement `ProxyAuthAdapter`:
   - Reads configured headers from request
   - Validates signature (HMAC) or mTLS if configured
   - Constructs `UserContextModel` from headers
   - Extracts upstream token if present
3. Integrate with `ScopeMapper`:
   - Scope header value parsed and mapped to MXCP scopes
   - Alternatively, accept pre-mapped scopes directly from proxy
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
1. Implement additional `TokenStore` backends (each handles its own security):
   - `VaultTokenStore`: Stores tokens directly in HashiCorp Vault (Vault handles encryption)
   - `AwsSecretsManagerTokenStore`: Stores in AWS Secrets Manager (stretch goal)
2. For SQLite backend, add key rotation tooling:
   - CLI command to rotate encryption keys
   - Automatic re-encryption of stored tokens
3. Add admin CLI commands:
   - `mxcp auth list-sessions` showing active sessions (no secrets)
   - `mxcp auth revoke --session <id>` to invalidate sessions
   - `mxcp auth cleanup` to purge expired data
4. Add audit events for:
   - Session creation and revocation
   - Token refresh attempts
   - Authentication failures
5. Add tests for each backend and admin operations

**Outcome**: Multiple storage backends; admin visibility and control.

---

### Phase 9: Admin Tooling

**Goal**: Operational visibility into auth state.

**Tasks**:
1. Add admin API endpoints (via admin socket):
   - List active sessions (count, providers, expiry)
   - Revoke session by ID
   - View configured scopes and mappings
2. Ensure health check endpoint reports auth subsystem status(?)

**Outcome**: Operators can inspect and manage auth state.

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
3. Add migration guide for existing deployments
4. Add troubleshooting section for common issues

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


```

```markdown
# MXCP Authentication Redesign Plan

## Overview

This document outlines the implementation plan for overhauling MXCP's authentication system. The goals are:

- Single `AuthService` entry point for all transports
- Secure token and session storage with refresh support
- Access to upstream provider tokens for calling external APIs
- Proxy/header-trust mode for deployments behind SSO-aware reverse proxies
- Clear scope and entitlement model consumable by CEL policies and endpoint annotations
- Strict separation between SDK (reusable, well-typed) and server (config loading, FastMCP wiring)

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
| `models.py` | `UserContextModel`, provider configs, `StateMetaModel`, etc. | Extend `UserContextModel` with `mxcp_scopes`; add mapping config models |
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
8. Add comprehensive tests for service instantiation and route registration

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
5. Add background cleanup job for expired sessions and tokens
6. Migrate existing SQLite schema; provide data migration tooling

**Outcome**: Session logic extracted; encrypted storage; no private field access in middleware.

---

### Phase 3: Provider Adapter Refactor

**Goal**: Thin provider adapters that only talk to IdPs.

**Tasks**:
1. Define `ProviderAdapter` protocol with methods:
   - `build_authorize_url(request)` returning authorization URL
   - `exchange_code(code, state)` returning `ExternalGrantResult`
   - `refresh(grant)` returning `ExternalGrantResult`
   - `fetch_user_context(access_token)` returning `UserContextModel`
2. Define `ExternalGrantResult` dataclass with:
   - Access token, refresh token, expiry timestamp
   - Raw profile data, provider scopes
3. Convert existing providers (Google, Keycloak, GitHub, Atlassian, Salesforce) to adapters:
   - Remove route registration logic
   - Remove persistence calls
   - Remove state storage (move to `SessionManager`)
4. Update `AuthService` to:
   - Own single callback route (e.g., `/auth/oauth/callback`)
   - Dispatch to appropriate adapter based on session state
   - Store grants via `SessionManager`
5. Add tests for each provider adapter in isolation

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

**Outcome**: Long-lived sessions; provider tokens stay fresh; endpoints can call external APIs.

---

### Phase 5: Scope and Mapping Layer

**Goal**: Translate IdP claims to MXCP entitlements; enforce per endpoint.

**Tasks**:
1. Extend `UserContextModel` with:
   - `mxcp_scopes: set[str]` for internal entitlements
   - `provider_scopes: set[str]` for raw IdP scopes
2. Create `ScopeMapper` class:
   - Accepts mapping configuration (claim type → scope mappings)
   - Given provider claims (scopes, groups, custom attributes) returns MXCP scopes
   - Supports multiple strategies: direct passthrough, group mapping, regex patterns
3. Define mapping config schema in SDK models:
   - `ClaimMappingConfigModel` with source type, claim name, scope mappings
4. Update `AuthService` to run `ScopeMapper` after authentication
5. Update middleware to:
   - Check global `required_scopes` from config
   - Accept endpoint-specific scope requirements as parameter
   - Reject requests missing required scopes
6. Surface `user_context.mxcp_scopes` to CEL policy engine
7. Add tests for mapping scenarios: groups to scopes, passthrough, multiple claims

**Outcome**: Stable MXCP entitlement vocabulary; enforceable per endpoint.

---

### Phase 6: Endpoint and Policy Integration

**Goal**: Per-endpoint scope requirements; CEL integration.

**Tasks**:
1. Extend endpoint YAML schema to accept scope annotations:
   - Under `annotations.scopes` list required MXCP scopes
2. Update endpoint loader to index all referenced scopes across endpoints
3. Update execution wrapper to:
   - Read endpoint scope requirements from definition
   - Pass requirements to middleware for enforcement
4. Add CEL helper functions:
   - `user_has_scope(scope_name)` checking `user_context.mxcp_scopes`
   - `user_has_provider_scope(scope_name)` checking raw provider scopes
5. Update policy enforcer to leverage new context fields
6. Optional: Add validation warning for undefined scopes in endpoints
7. Add tests for endpoint-level scope enforcement and CEL integration

**Outcome**: Builders define scopes per endpoint; policies can reference them.

---

### Phase 7: Proxy and Header Mode

**Goal**: Support deployments behind SSO-aware reverse proxies.

**Tasks**:
1. Define `ProxyAuthConfigModel` in SDK with:
   - Header names for user ID, username, email, scopes
   - Optional upstream token header for passthrough
   - Signature validation settings (header name, secret env, algorithm)
   - Optional mTLS requirement flag
2. Implement `ProxyAuthAdapter`:
   - Reads configured headers from request
   - Validates signature (HMAC) or mTLS if configured
   - Constructs `UserContextModel` from headers
   - Extracts upstream token if present
3. Integrate with `ScopeMapper`:
   - Scope header value parsed and mapped to MXCP scopes
   - Alternatively, accept pre-mapped scopes directly from proxy
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
1. Implement additional `TokenStore` backends (each handles its own security):
   - `VaultTokenStore`: Stores tokens directly in HashiCorp Vault (Vault handles encryption)
   - `AwsSecretsManagerTokenStore`: Stores in AWS Secrets Manager (stretch goal)
2. For SQLite backend, add key rotation tooling:
   - CLI command to rotate encryption keys
   - Automatic re-encryption of stored tokens
3. Add admin CLI commands:
   - `mxcp auth list-sessions` showing active sessions (no secrets)
   - `mxcp auth revoke --session <id>` to invalidate sessions
   - `mxcp auth cleanup` to purge expired data
4. Add audit events for:
   - Session creation and revocation
   - Token refresh attempts
   - Authentication failures
5. Add tests for each backend and admin operations

**Outcome**: Multiple storage backends; admin visibility and control.

---

### Phase 9: Admin Tooling

**Goal**: Operational visibility into auth state.

**Tasks**:
1. Add admin API endpoints (via admin socket):
   - List active sessions (count, providers, expiry)
   - Revoke session by ID
   - View configured scopes and mappings
2. Ensure health check endpoint reports auth subsystem status(?)

**Outcome**: Operators can inspect and manage auth state.

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
3. Add migration guide for existing deployments
4. Add troubleshooting section for common issues

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


```

```markdown
# MXCP Authentication Redesign Plan

## Overview

This document outlines the implementation plan for overhauling MXCP's authentication system. The goals are:

- Single `AuthService` entry point for all transports
- Secure token and session storage with refresh support
- Access to upstream provider tokens for calling external APIs
- Proxy/header-trust mode for deployments behind SSO-aware reverse proxies
- Clear scope and entitlement model consumable by CEL policies and endpoint annotations
- Strict separation between SDK (reusable, well-typed) and server (config loading, FastMCP wiring)

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
| `models.py` | `UserContextModel`, provider configs, `StateMetaModel`, etc. | Extend `UserContextModel` with `mxcp_scopes`; add mapping config models |
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
8. Add comprehensive tests for service instantiation and route registration

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
5. Add background cleanup job for expired sessions and tokens
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

**Outcome**: Long-lived sessions; provider tokens stay fresh; endpoints can call external APIs.

---

### Phase 5: Scope and Mapping Layer

**Goal**: Translate IdP claims to MXCP entitlements; enforce per endpoint.

**Tasks**:
1. Extend `UserContextModel` with:
   - `mxcp_scopes: set[str]` for internal entitlements
   - `provider_scopes: set[str]` for raw IdP scopes
2. Create `ScopeMapper` class:
   - Accepts mapping configuration (claim type → scope mappings)
   - Given provider claims (scopes, groups, custom attributes) returns MXCP scopes
   - Supports multiple strategies: direct passthrough, group mapping, regex patterns
3. Define mapping config schema in SDK models:
   - `ClaimMappingConfigModel` with source type, claim name, scope mappings
4. Update `AuthService` to run `ScopeMapper` after authentication
5. Update middleware to:
   - Check global `required_scopes` from config
   - Accept endpoint-specific scope requirements as parameter
   - Reject requests missing required scopes
6. Surface `user_context.mxcp_scopes` to CEL policy engine
7. Add tests for mapping scenarios: groups to scopes, passthrough, multiple claims

**Outcome**: Stable MXCP entitlement vocabulary; enforceable per endpoint.

---

### Phase 6: Endpoint and Policy Integration

**Goal**: Per-endpoint scope requirements; CEL integration.

**Tasks**:
1. Extend endpoint YAML schema to accept scope annotations:
   - Under `annotations.scopes` list required MXCP scopes
2. Update endpoint loader to index all referenced scopes across endpoints
3. Update execution wrapper to:
   - Read endpoint scope requirements from definition
   - Pass requirements to middleware for enforcement
4. Add CEL helper functions:
   - `user_has_scope(scope_name)` checking `user_context.mxcp_scopes`
   - `user_has_provider_scope(scope_name)` checking raw provider scopes
5. Update policy enforcer to leverage new context fields
6. Optional: Add validation warning for undefined scopes in endpoints
7. Add tests for endpoint-level scope enforcement and CEL integration

**Outcome**: Builders define scopes per endpoint; policies can reference them.

---

### Phase 7: Proxy and Header Mode

**Goal**: Support deployments behind SSO-aware reverse proxies.

**Tasks**:
1. Define `ProxyAuthConfigModel` in SDK with:
   - Header names for user ID, username, email, scopes
   - Optional upstream token header for passthrough
   - Signature validation settings (header name, secret env, algorithm)
   - Optional mTLS requirement flag
2. Implement `ProxyAuthAdapter`:
   - Reads configured headers from request
   - Validates signature (HMAC) or mTLS if configured
   - Constructs `UserContextModel` from headers
   - Extracts upstream token if present
3. Integrate with `ScopeMapper`:
   - Scope header value parsed and mapped to MXCP scopes
   - Alternatively, accept pre-mapped scopes directly from proxy
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
1. Implement additional `TokenStore` backends (each handles its own security):
   - `VaultTokenStore`: Stores tokens directly in HashiCorp Vault (Vault handles encryption)
   - `AwsSecretsManagerTokenStore`: Stores in AWS Secrets Manager (stretch goal)
2. For SQLite backend, add key rotation tooling:
   - CLI command to rotate encryption keys
   - Automatic re-encryption of stored tokens
3. Add admin CLI commands:
   - `mxcp auth list-sessions` showing active sessions (no secrets)
   - `mxcp auth revoke --session <id>` to invalidate sessions
   - `mxcp auth cleanup` to purge expired data
4. Add audit events for:
   - Session creation and revocation
   - Token refresh attempts
   - Authentication failures
5. Add tests for each backend and admin operations

**Outcome**: Multiple storage backends; admin visibility and control.

---

### Phase 9: Admin Tooling

**Goal**: Operational visibility into auth state.

**Tasks**:
1. Add admin API endpoints (via admin socket):
   - List active sessions (count, providers, expiry)
   - Revoke session by ID
   - View configured scopes and mappings
2. Ensure health check endpoint reports auth subsystem status(?)

**Outcome**: Operators can inspect and manage auth state.

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
3. Add migration guide for existing deployments
4. Add troubleshooting section for common issues

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


```

```markdown
# MXCP Authentication Redesign Plan

## Overview

This document outlines the implementation plan for overhauling MXCP's authentication system. The goals are:

- Single `AuthService` entry point for all transports
- Secure token and session storage with refresh support
- Access to upstream provider tokens for calling external APIs
- Proxy/header-trust mode for deployments behind SSO-aware reverse proxies
- Clear scope and entitlement model consumable by CEL policies and endpoint annotations
- Strict separation between SDK (reusable, well-typed) and server (config loading, FastMCP wiring)

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
| `models.py` | `UserContextModel`, provider configs, `StateMetaModel`, etc. | Extend `UserContextModel` with `mxcp_scopes`; add mapping config models |
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
8. Add comprehensive tests for service instantiation and route registration

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
5. Add background cleanup job for expired sessions and tokens
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

**Outcome**: Long-lived sessions; provider tokens stay fresh; endpoints can call external APIs.

---

### Phase 5: Scope and Mapping Layer

**Goal**: Translate IdP claims to MXCP entitlements; enforce per endpoint.

**Tasks**:
1. Extend existing `UserContextModel` (in `mxcp.sdk.auth.models`) with:
   - `mxcp_scopes: set[str]` for internal entitlements
   - `provider_scopes: set[str]` for raw IdP scopes (currently not captured)
2. Create `ScopeMapper` class:
   - Accepts mapping configuration (claim type → scope mappings)
   - Given provider claims (scopes, groups, custom attributes) returns MXCP scopes
   - Supports multiple strategies: direct passthrough, group mapping, regex patterns
3. Define mapping config schema in SDK models:
   - `ClaimMappingConfigModel` with source type, claim name, scope mappings
4. Update `AuthService` to run `ScopeMapper` after authentication
5. Update middleware to:
   - Check global `required_scopes` from config
   - Accept endpoint-specific scope requirements as parameter
   - Reject requests missing required scopes
6. Surface `user_context.mxcp_scopes` to CEL policy engine
7. Add tests for mapping scenarios: groups to scopes, passthrough, multiple claims

**Outcome**: Stable MXCP entitlement vocabulary; enforceable per endpoint.

---

### Phase 6: Endpoint and Policy Integration

**Goal**: Per-endpoint scope requirements; CEL integration.

**Tasks**:
1. Extend endpoint YAML schema to accept scope annotations:
   - Under `annotations.scopes` list required MXCP scopes
2. Update endpoint loader to index all referenced scopes across endpoints
3. Update execution wrapper to:
   - Read endpoint scope requirements from definition
   - Pass requirements to middleware for enforcement
4. Add CEL helper functions:
   - `user_has_scope(scope_name)` checking `user_context.mxcp_scopes`
   - `user_has_provider_scope(scope_name)` checking raw provider scopes
5. Update policy enforcer to leverage new context fields
6. Optional: Add validation warning for undefined scopes in endpoints
7. Add tests for endpoint-level scope enforcement and CEL integration

**Outcome**: Builders define scopes per endpoint; policies can reference them.

---

### Phase 7: Proxy and Header Mode

**Goal**: Support deployments behind SSO-aware reverse proxies.

**Tasks**:
1. Define `ProxyAuthConfigModel` in SDK with:
   - Header names for user ID, username, email, scopes
   - Optional upstream token header for passthrough
   - Signature validation settings (header name, secret env, algorithm)
   - Optional mTLS requirement flag
2. Implement `ProxyAuthAdapter`:
   - Reads configured headers from request
   - Validates signature (HMAC) or mTLS if configured
   - Constructs `UserContextModel` from headers
   - Extracts upstream token if present
3. Integrate with `ScopeMapper`:
   - Scope header value parsed and mapped to MXCP scopes
   - Alternatively, accept pre-mapped scopes directly from proxy
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
1. Implement additional `TokenStore` backends (each handles its own security):
   - `VaultTokenStore`: Stores tokens directly in HashiCorp Vault (Vault handles encryption)
   - `AwsSecretsManagerTokenStore`: Stores in AWS Secrets Manager (stretch goal)
2. For SQLite backend, add key rotation tooling:
   - CLI command to rotate encryption keys
   - Automatic re-encryption of stored tokens
3. Add admin CLI commands:
   - `mxcp auth list-sessions` showing active sessions (no secrets)
   - `mxcp auth revoke --session <id>` to invalidate sessions
   - `mxcp auth cleanup` to purge expired data
4. Add audit events for:
   - Session creation and revocation
   - Token refresh attempts
   - Authentication failures
5. Add tests for each backend and admin operations

**Outcome**: Multiple storage backends; admin visibility and control.

---

### Phase 9: Admin Tooling

**Goal**: Operational visibility into auth state.

**Tasks**:
1. Add admin API endpoints (via admin socket):
   - List active sessions (count, providers, expiry)
   - Revoke session by ID
   - View configured scopes and mappings
2. Ensure health check endpoint reports auth subsystem status(?)

**Outcome**: Operators can inspect and manage auth state.

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
3. Add migration guide for existing deployments
4. Add troubleshooting section for common issues

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


```

```markdown
# MXCP Authentication Redesign Plan

## Overview

This document outlines the implementation plan for overhauling MXCP's authentication system. The goals are:

- Single `AuthService` entry point for all transports
- Secure token and session storage with refresh support
- Access to upstream provider tokens for calling external APIs
- Proxy/header-trust mode for deployments behind SSO-aware reverse proxies
- Clear scope and entitlement model consumable by CEL policies and endpoint annotations
- Strict separation between SDK (reusable, well-typed) and server (config loading, FastMCP wiring)

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
| `models.py` | `UserContextModel`, provider configs, `StateMetaModel`, etc. | Extend `UserContextModel` with `mxcp_scopes`; add mapping config models |
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
8. Add comprehensive tests for service instantiation and route registration

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
5. Add background cleanup job for expired sessions and tokens
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

**Outcome**: Long-lived sessions; provider tokens stay fresh; endpoints can call external APIs.

---

### Phase 5: Scope and Mapping Layer

**Goal**: Translate IdP claims to MXCP entitlements; enforce per endpoint.

**Tasks**:
1. Extend existing `UserContextModel` (in `mxcp.sdk.auth.models`) with:
   - `mxcp_scopes: set[str]` for internal entitlements
   - `provider_scopes: set[str]` for raw IdP scopes (currently not captured)
2. Create `ScopeMapper` class:
   - Accepts mapping configuration (claim type → scope mappings)
   - Given provider claims (scopes, groups, custom attributes) returns MXCP scopes
   - Supports multiple strategies: direct passthrough, group mapping, regex patterns
3. Define mapping config schema in SDK models:
   - `ClaimMappingConfigModel` with source type, claim name, scope mappings
4. Update `AuthService` to run `ScopeMapper` after authentication
5. Update middleware to:
   - Check global `required_scopes` from config
   - Accept endpoint-specific scope requirements as parameter
   - Reject requests missing required scopes
6. Surface `user_context.mxcp_scopes` to CEL policy engine
7. Add tests for mapping scenarios: groups to scopes, passthrough, multiple claims

**Outcome**: Stable MXCP entitlement vocabulary; enforceable per endpoint.

---

### Phase 6: Endpoint and Policy Integration

**Goal**: Per-endpoint scope requirements; CEL integration.

**Tasks**:
1. Extend endpoint YAML schema to accept scope annotations:
   - Under `annotations.scopes` list required MXCP scopes
2. Update existing `EndpointLoader` to index all referenced scopes across endpoints
3. Update execution wrapper to:
   - Read endpoint scope requirements from definition
   - Pass requirements to middleware for enforcement
4. Add CEL helper functions:
   - `user_has_scope(scope_name)` checking `user_context.mxcp_scopes`
   - `user_has_provider_scope(scope_name)` checking raw provider scopes
5. Update policy enforcer to leverage new context fields
6. Optional: Add validation warning for undefined scopes in endpoints
7. Add tests for endpoint-level scope enforcement and CEL integration

**Outcome**: Builders define scopes per endpoint; policies can reference them.

---

### Phase 7: Proxy and Header Mode

**Goal**: Support deployments behind SSO-aware reverse proxies.

**Tasks**:
1. Define `ProxyAuthConfigModel` in SDK with:
   - Header names for user ID, username, email, scopes
   - Optional upstream token header for passthrough
   - Signature validation settings (header name, secret env, algorithm)
   - Optional mTLS requirement flag
2. Implement `ProxyAuthAdapter`:
   - Reads configured headers from request
   - Validates signature (HMAC) or mTLS if configured
   - Constructs `UserContextModel` from headers
   - Extracts upstream token if present
3. Integrate with `ScopeMapper`:
   - Scope header value parsed and mapped to MXCP scopes
   - Alternatively, accept pre-mapped scopes directly from proxy
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
1. Implement additional `TokenStore` backends (each handles its own security):
   - `VaultTokenStore`: Stores tokens directly in HashiCorp Vault (Vault handles encryption)
   - `AwsSecretsManagerTokenStore`: Stores in AWS Secrets Manager (stretch goal)
2. For SQLite backend, add key rotation tooling:
   - CLI command to rotate encryption keys
   - Automatic re-encryption of stored tokens
3. Add admin CLI commands:
   - `mxcp auth list-sessions` showing active sessions (no secrets)
   - `mxcp auth revoke --session <id>` to invalidate sessions
   - `mxcp auth cleanup` to purge expired data
4. Add audit events for:
   - Session creation and revocation
   - Token refresh attempts
   - Authentication failures
5. Add tests for each backend and admin operations

**Outcome**: Multiple storage backends; admin visibility and control.

---

### Phase 9: Admin Tooling

**Goal**: Operational visibility into auth state.

**Tasks**:
1. Add admin API endpoints (via admin socket):
   - List active sessions (count, providers, expiry)
   - Revoke session by ID
   - View configured scopes and mappings
2. Ensure health check endpoint reports auth subsystem status(?)

**Outcome**: Operators can inspect and manage auth state.

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
3. Add migration guide for existing deployments
4. Add troubleshooting section for common issues

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


```

```markdown
# MXCP Authentication Redesign Plan

## Overview

This document outlines the implementation plan for overhauling MXCP's authentication system. The goals are:

- Single `AuthService` entry point for all transports
- Secure token and session storage with refresh support
- Access to upstream provider tokens for calling external APIs
- Proxy/header-trust mode for deployments behind SSO-aware reverse proxies
- Clear scope and entitlement model consumable by CEL policies and endpoint annotations
- Strict separation between SDK (reusable, well-typed) and server (config loading, FastMCP wiring)

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
| `models.py` | `UserContextModel`, provider configs, `StateMetaModel`, etc. | Extend `UserContextModel` with `mxcp_scopes`; add mapping config models |
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
8. Add comprehensive tests for service instantiation and route registration

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
5. Add background cleanup job for expired sessions and tokens
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

**Outcome**: Long-lived sessions; provider tokens stay fresh; endpoints can call external APIs.

---

### Phase 5: Scope and Mapping Layer

**Goal**: Translate IdP claims to MXCP entitlements; enforce per endpoint.

**Tasks**:
1. Extend existing `UserContextModel` (in `mxcp.sdk.auth.models`) with:
   - `mxcp_scopes: set[str]` for internal entitlements
   - `provider_scopes: set[str]` for raw IdP scopes (currently not captured)
2. Create `ScopeMapper` class:
   - Accepts mapping configuration (claim type → scope mappings)
   - Given provider claims (scopes, groups, custom attributes) returns MXCP scopes
   - Supports multiple strategies: direct passthrough, group mapping, regex patterns
3. Define mapping config schema in SDK models:
   - `ClaimMappingConfigModel` with source type, claim name, scope mappings
4. Update `AuthService` to run `ScopeMapper` after authentication
5. Update middleware to:
   - Check global `required_scopes` from config
   - Accept endpoint-specific scope requirements as parameter
   - Reject requests missing required scopes
6. Surface `user_context.mxcp_scopes` to CEL policy engine
7. Add tests for mapping scenarios: groups to scopes, passthrough, multiple claims

**Outcome**: Stable MXCP entitlement vocabulary; enforceable per endpoint.

---

### Phase 6: Endpoint and Policy Integration

**Goal**: Per-endpoint scope requirements; CEL integration.

**Tasks**:
1. Extend endpoint YAML schema to accept scope annotations:
   - Under `annotations.scopes` list required MXCP scopes
2. Update existing `EndpointLoader` to index all referenced scopes across endpoints
3. Update execution wrapper to:
   - Read endpoint scope requirements from definition
   - Pass requirements to middleware for enforcement
4. Add CEL helper functions:
   - `user_has_scope(scope_name)` checking `user_context.mxcp_scopes`
   - `user_has_provider_scope(scope_name)` checking raw provider scopes
5. Update policy enforcer to leverage new context fields
6. Optional: Add validation warning for undefined scopes in endpoints
7. Add tests for endpoint-level scope enforcement and CEL integration

**Outcome**: Builders define scopes per endpoint; policies can reference them.

---

### Phase 7: Proxy and Header Mode

**Goal**: Support deployments behind SSO-aware reverse proxies.

**Tasks**:
1. Define `ProxyAuthConfigModel` in SDK with:
   - Header names for user ID, username, email, scopes
   - Optional upstream token header for passthrough
   - Signature validation settings (header name, secret env, algorithm)
   - Optional mTLS requirement flag
2. Implement `ProxyAuthAdapter`:
   - Reads configured headers from request
   - Validates signature (HMAC) or mTLS if configured
   - Constructs `UserContextModel` from headers
   - Extracts upstream token if present
3. Integrate with `ScopeMapper`:
   - Scope header value parsed and mapped to MXCP scopes
   - Alternatively, accept pre-mapped scopes directly from proxy
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
2. For `SqliteTokenStore`, add key rotation tooling:
   - CLI command to rotate encryption keys
   - Automatic re-encryption of stored tokens
3. Add admin CLI commands:
   - `mxcp auth list-sessions` showing active sessions (no secrets)
   - `mxcp auth revoke --session <id>` to invalidate sessions
   - `mxcp auth cleanup` to purge expired data
4. Add audit events for:
   - Session creation and revocation
   - Token refresh attempts
   - Authentication failures
5. Add tests for each backend and admin operations

**Outcome**: Multiple storage backends; admin visibility and control.

---

### Phase 9: Admin Tooling

**Goal**: Operational visibility into auth state.

**Tasks**:
1. Add admin API endpoints (via admin socket):
   - List active sessions (count, providers, expiry)
   - Revoke session by ID
   - View configured scopes and mappings
2. Ensure health check endpoint reports auth subsystem status(?)

**Outcome**: Operators can inspect and manage auth state.

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
3. Add migration guide for existing deployments
4. Add troubleshooting section for common issues

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


```

Done. The plan now includes a "Current SDK Auth Inventory" section that explicitly lists:

1. **Existing modules** and how each maps to the target architecture
2. **Existing providers** (all 5) and their refactoring path
3. **Server-side auth code** that will delegate to `AuthService`
4. **What gets created new** vs refactored

The implementation phases also now reference existing code explicitly:
- Phase 1: "wrapping existing code", "existing `GeneralOAuthAuthorizationServer`"
- Phase 2: "Extract session management from `GeneralOAuthAuthorizationServer`", "Refactor `mxcp.sdk.auth.persistence`"
- Phase 3: "evolving from existing `ExternalOAuthHandler`", "Refactor existing providers"
- Phase 5: "Extend existing `UserContextModel`"
- Phase 6: "Update existing `EndpointLoader`"

---

**User**

and is it CEL helper functions as mentioned in the plan? is that how we do things  in CEL/policy enforcement layer? we add functions to access stuff? not an object? or also we do duckdb python functions as well as mxcp.runtime functions?

remove admin CLI commands. we dont have such things. we can add things to the admin REST API we have but make sure of what is there first. but there's no admin CLI and wont be.

---

**Cursor**

```python
def _create_cel_environment(self) -> celpy.Environment:
    """Create CEL environment with custom functions."""
    # Create CEL environment with standard functions
    env = celpy.Environment()

    # Add custom functions if needed
    # For example: env.add_function("custom_func", custom_implementation)

    return env
```

I see. So:

1. **CEL** doesn't use custom functions - it uses **data objects**. The `user` context is a dictionary with `user.role`, `user.permissions`, `user.email`, etc. So to expose `mxcp_scopes`, we'd extend the user context dictionary, not add CEL functions.

2. **Admin API** exists as a REST API over Unix socket (status, reload, config, endpoints, system, audit routers). No CLI wrapper.

Let me update the plan to fix both issues:

```markdown
# MXCP Authentication Redesign Plan

## Overview

This document outlines the implementation plan for overhauling MXCP's authentication system. The goals are:

- Single `AuthService` entry point for all transports
- Secure token and session storage with refresh support
- Access to upstream provider tokens for calling external APIs
- Proxy/header-trust mode for deployments behind SSO-aware reverse proxies
- Clear scope and entitlement model consumable by CEL policies and endpoint annotations
- Strict separation between SDK (reusable, well-typed) and server (config loading, FastMCP wiring)

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
| `models.py` | `UserContextModel`, provider configs, `StateMetaModel`, etc. | Extend `UserContextModel` with `mxcp_scopes`; add mapping config models |
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
8. Add comprehensive tests for service instantiation and route registration

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
5. Add background cleanup job for expired sessions and tokens
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

**Outcome**: Long-lived sessions; provider tokens stay fresh; endpoints can call external APIs.

---

### Phase 5: Scope and Mapping Layer

**Goal**: Translate IdP claims to MXCP entitlements; enforce per endpoint.

**Tasks**:
1. Extend existing `UserContextModel` (in `mxcp.sdk.auth.models`) with:
   - `mxcp_scopes: set[str]` for internal entitlements
   - `provider_scopes: set[str]` for raw IdP scopes (currently not captured)
2. Create `ScopeMapper` class:
   - Accepts mapping configuration (claim type → scope mappings)
   - Given provider claims (scopes, groups, custom attributes) returns MXCP scopes
   - Supports multiple strategies: direct passthrough, group mapping, regex patterns
3. Define mapping config schema in SDK models:
   - `ClaimMappingConfigModel` with source type, claim name, scope mappings
4. Update `AuthService` to run `ScopeMapper` after authentication
5. Update middleware to:
   - Check global `required_scopes` from config
   - Accept endpoint-specific scope requirements as parameter
   - Reject requests missing required scopes
6. Surface `user_context.mxcp_scopes` to CEL policy engine
7. Add tests for mapping scenarios: groups to scopes, passthrough, multiple claims

**Outcome**: Stable MXCP entitlement vocabulary; enforceable per endpoint.

---

### Phase 6: Endpoint and Policy Integration

**Goal**: Per-endpoint scope requirements; CEL integration.

**Tasks**:
1. Extend endpoint YAML schema to accept scope annotations:
   - Under `annotations.scopes` list required MXCP scopes
2. Update existing `EndpointLoader` to index all referenced scopes across endpoints
3. Update execution wrapper to:
   - Read endpoint scope requirements from definition
   - Pass requirements to middleware for enforcement
4. Extend CEL user context object (in `PolicyEnforcer._user_context_to_dict`):
   - Add `user.mxcp_scopes` list for CEL expressions like `user.mxcp_scopes.exists(s, s == "admin")`
   - Add `user.provider_scopes` list for raw IdP scopes
5. Update policy enforcer to include new fields in CEL context
6. Optional: Add validation warning for undefined scopes in endpoints
7. Add tests for endpoint-level scope enforcement and CEL integration

**Outcome**: Builders define scopes per endpoint; policies can reference them.

---

### Phase 7: Proxy and Header Mode

**Goal**: Support deployments behind SSO-aware reverse proxies.

**Tasks**:
1. Define `ProxyAuthConfigModel` in SDK with:
   - Header names for user ID, username, email, scopes
   - Optional upstream token header for passthrough
   - Signature validation settings (header name, secret env, algorithm)
   - Optional mTLS requirement flag
2. Implement `ProxyAuthAdapter`:
   - Reads configured headers from request
   - Validates signature (HMAC) or mTLS if configured
   - Constructs `UserContextModel` from headers
   - Extracts upstream token if present
3. Integrate with `ScopeMapper`:
   - Scope header value parsed and mapped to MXCP scopes
   - Alternatively, accept pre-mapped scopes directly from proxy
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
2. For `SqliteTokenStore`, add key rotation tooling:
   - CLI command to rotate encryption keys
   - Automatic re-encryption of stored tokens
3. Add admin CLI commands:
   - `mxcp auth list-sessions` showing active sessions (no secrets)
   - `mxcp auth revoke --session <id>` to invalidate sessions
   - `mxcp auth cleanup` to purge expired data
4. Add audit events for:
   - Session creation and revocation
   - Token refresh attempts
   - Authentication failures
5. Add tests for each backend and admin operations

**Outcome**: Multiple storage backends; admin visibility and control.

---

### Phase 9: Admin Tooling

**Goal**: Operational visibility into auth state.

**Tasks**:
1. Add admin API endpoints (via admin socket):
   - List active sessions (count, providers, expiry)
   - Revoke session by ID
   - View configured scopes and mappings
2. Ensure health check endpoint reports auth subsystem status(?)

**Outcome**: Operators can inspect and manage auth state.

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
3. Add migration guide for existing deployments
4. Add troubleshooting section for common issues

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


```

```markdown
# MXCP Authentication Redesign Plan

## Overview

This document outlines the implementation plan for overhauling MXCP's authentication system. The goals are:

- Single `AuthService` entry point for all transports
- Secure token and session storage with refresh support
- Access to upstream provider tokens for calling external APIs
- Proxy/header-trust mode for deployments behind SSO-aware reverse proxies
- Clear scope and entitlement model consumable by CEL policies and endpoint annotations
- Strict separation between SDK (reusable, well-typed) and server (config loading, FastMCP wiring)

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
| `models.py` | `UserContextModel`, provider configs, `StateMetaModel`, etc. | Extend `UserContextModel` with `mxcp_scopes`; add mapping config models |
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
8. Add comprehensive tests for service instantiation and route registration

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
5. Add background cleanup job for expired sessions and tokens
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

**Outcome**: Long-lived sessions; provider tokens stay fresh; endpoints can call external APIs.

---

### Phase 5: Scope and Mapping Layer

**Goal**: Translate IdP claims to MXCP entitlements; enforce per endpoint.

**Tasks**:
1. Extend existing `UserContextModel` (in `mxcp.sdk.auth.models`) with:
   - `mxcp_scopes: set[str]` for internal entitlements
   - `provider_scopes: set[str]` for raw IdP scopes (currently not captured)
2. Create `ScopeMapper` class:
   - Accepts mapping configuration (claim type → scope mappings)
   - Given provider claims (scopes, groups, custom attributes) returns MXCP scopes
   - Supports multiple strategies: direct passthrough, group mapping, regex patterns
3. Define mapping config schema in SDK models:
   - `ClaimMappingConfigModel` with source type, claim name, scope mappings
4. Update `AuthService` to run `ScopeMapper` after authentication
5. Update middleware to:
   - Check global `required_scopes` from config
   - Accept endpoint-specific scope requirements as parameter
   - Reject requests missing required scopes
6. Surface `user_context.mxcp_scopes` to CEL policy engine
7. Add tests for mapping scenarios: groups to scopes, passthrough, multiple claims

**Outcome**: Stable MXCP entitlement vocabulary; enforceable per endpoint.

---

### Phase 6: Endpoint and Policy Integration

**Goal**: Per-endpoint scope requirements; CEL integration.

**Tasks**:
1. Extend endpoint YAML schema to accept scope annotations:
   - Under `annotations.scopes` list required MXCP scopes
2. Update existing `EndpointLoader` to index all referenced scopes across endpoints
3. Update execution wrapper to:
   - Read endpoint scope requirements from definition
   - Pass requirements to middleware for enforcement
4. Extend CEL user context object (in `PolicyEnforcer._user_context_to_dict`):
   - Add `user.mxcp_scopes` list for CEL expressions like `user.mxcp_scopes.exists(s, s == "admin")`
   - Add `user.provider_scopes` list for raw IdP scopes
5. Update policy enforcer to include new fields in CEL context
6. Optional: Add validation warning for undefined scopes in endpoints
7. Add tests for endpoint-level scope enforcement and CEL integration

**Outcome**: Builders define scopes per endpoint; policies can reference them.

---

### Phase 7: Proxy and Header Mode

**Goal**: Support deployments behind SSO-aware reverse proxies.

**Tasks**:
1. Define `ProxyAuthConfigModel` in SDK with:
   - Header names for user ID, username, email, scopes
   - Optional upstream token header for passthrough
   - Signature validation settings (header name, secret env, algorithm)
   - Optional mTLS requirement flag
2. Implement `ProxyAuthAdapter`:
   - Reads configured headers from request
   - Validates signature (HMAC) or mTLS if configured
   - Constructs `UserContextModel` from headers
   - Extracts upstream token if present
3. Integrate with `ScopeMapper`:
   - Scope header value parsed and mapped to MXCP scopes
   - Alternatively, accept pre-mapped scopes directly from proxy
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

### Phase 9: Admin Tooling

**Goal**: Operational visibility into auth state.

**Tasks**:
1. Add admin API endpoints (via admin socket):
   - List active sessions (count, providers, expiry)
   - Revoke session by ID
   - View configured scopes and mappings
2. Ensure health check endpoint reports auth subsystem status(?)

**Outcome**: Operators can inspect and manage auth state.

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
3. Add migration guide for existing deployments
4. Add troubleshooting section for common issues

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


```

```markdown
### Phase 9: Admin API Extensions

**Goal**: Operational visibility into auth state via existing admin REST API.

**Tasks**:
1. Add new endpoints to existing admin API (Unix socket):
   - `GET /auth/sessions` - List active sessions (count, providers, expiry)
   - `DELETE /auth/sessions/{id}` - Revoke session by ID
   - `GET /auth/config` - View configured scopes and mappings
   - `POST /auth/cleanup` - Purge expired sessions and tokens
2. Extend existing `GET /status` to include auth subsystem health
3. Document admin API auth endpoints

**Outcome**: Operators can inspect and manage auth state via admin API.
```

```markdown
# MXCP Authentication Redesign Plan

## Overview

This document outlines the implementation plan for overhauling MXCP's authentication system. The goals are:

- Single `AuthService` entry point for all transports
- Secure token and session storage with refresh support
- Access to upstream provider tokens for calling external APIs
- Proxy/header-trust mode for deployments behind SSO-aware reverse proxies
- Clear scope and entitlement model consumable by CEL policies and endpoint annotations
- Strict separation between SDK (reusable, well-typed) and server (config loading, FastMCP wiring)

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
| `models.py` | `UserContextModel`, provider configs, `StateMetaModel`, etc. | Extend `UserContextModel` with `mxcp_scopes`; add mapping config models |
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
8. Add comprehensive tests for service instantiation and route registration

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
5. Add background cleanup job for expired sessions and tokens
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

**Outcome**: Long-lived sessions; provider tokens stay fresh; endpoints can call external APIs.

---

### Phase 5: Scope and Mapping Layer

**Goal**: Translate IdP claims to MXCP entitlements; enforce per endpoint.

**Tasks**:
1. Extend existing `UserContextModel` (in `mxcp.sdk.auth.models`) with:
   - `mxcp_scopes: set[str]` for internal entitlements
   - `provider_scopes: set[str]` for raw IdP scopes (currently not captured)
2. Create `ScopeMapper` class:
   - Accepts mapping configuration (claim type → scope mappings)
   - Given provider claims (scopes, groups, custom attributes) returns MXCP scopes
   - Supports multiple strategies: direct passthrough, group mapping, regex patterns
3. Define mapping config schema in SDK models:
   - `ClaimMappingConfigModel` with source type, claim name, scope mappings
4. Update `AuthService` to run `ScopeMapper` after authentication
5. Update middleware to:
   - Check global `required_scopes` from config
   - Accept endpoint-specific scope requirements as parameter
   - Reject requests missing required scopes
6. Surface `user_context.mxcp_scopes` to CEL policy engine
7. Add tests for mapping scenarios: groups to scopes, passthrough, multiple claims

**Outcome**: Stable MXCP entitlement vocabulary; enforceable per endpoint.

---

### Phase 6: Endpoint and Policy Integration

**Goal**: Per-endpoint scope requirements; CEL integration.

**Tasks**:
1. Extend endpoint YAML schema to accept scope annotations:
   - Under `annotations.scopes` list required MXCP scopes
2. Update existing `EndpointLoader` to index all referenced scopes across endpoints
3. Update execution wrapper to:
   - Read endpoint scope requirements from definition
   - Pass requirements to middleware for enforcement
4. Extend CEL user context object (in `PolicyEnforcer._user_context_to_dict`):
   - Add `user.mxcp_scopes` list for CEL expressions like `user.mxcp_scopes.exists(s, s == "admin")`
   - Add `user.provider_scopes` list for raw IdP scopes
5. Update policy enforcer to include new fields in CEL context
6. Optional: Add validation warning for undefined scopes in endpoints
7. Add tests for endpoint-level scope enforcement and CEL integration

**Outcome**: Builders define scopes per endpoint; policies can reference them.

---

### Phase 7: Proxy and Header Mode

**Goal**: Support deployments behind SSO-aware reverse proxies.

**Tasks**:
1. Define `ProxyAuthConfigModel` in SDK with:
   - Header names for user ID, username, email, scopes
   - Optional upstream token header for passthrough
   - Signature validation settings (header name, secret env, algorithm)
   - Optional mTLS requirement flag
2. Implement `ProxyAuthAdapter`:
   - Reads configured headers from request
   - Validates signature (HMAC) or mTLS if configured
   - Constructs `UserContextModel` from headers
   - Extracts upstream token if present
3. Integrate with `ScopeMapper`:
   - Scope header value parsed and mapped to MXCP scopes
   - Alternatively, accept pre-mapped scopes directly from proxy
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
3. Add migration guide for existing deployments
4. Add troubleshooting section for common issues

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


```

```markdown
# MXCP Authentication Redesign Plan

## Overview

This document outlines the implementation plan for overhauling MXCP's authentication system. The goals are:

- Single `AuthService` entry point for all transports
- Secure token and session storage with refresh support
- Access to upstream provider tokens for calling external APIs
- Proxy/header-trust mode for deployments behind SSO-aware reverse proxies
- Clear scope and entitlement model consumable by CEL policies and endpoint annotations
- Strict separation between SDK (reusable, well-typed) and server (config loading, FastMCP wiring)

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
| `models.py` | `UserContextModel`, provider configs, `StateMetaModel`, etc. | Extend `UserContextModel` with `mxcp_scopes`; add mapping config models |
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
8. Add comprehensive tests for service instantiation and route registration

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
5. Add background cleanup job for expired sessions and tokens
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

**Outcome**: Long-lived sessions; provider tokens stay fresh; endpoints can call external APIs.

---

### Phase 5: Scope and Mapping Layer

**Goal**: Translate IdP claims to MXCP entitlements; enforce per endpoint.

**Tasks**:
1. Extend existing `UserContextModel` (in `mxcp.sdk.auth.models`) with:
   - `mxcp_scopes: set[str]` for internal entitlements
   - `provider_scopes: set[str]` for raw IdP scopes (currently not captured)
2. Create `ScopeMapper` class:
   - Accepts mapping configuration (claim type → scope mappings)
   - Given provider claims (scopes, groups, custom attributes) returns MXCP scopes
   - Supports multiple strategies: direct passthrough, group mapping, regex patterns
3. Define mapping config schema in SDK models:
   - `ClaimMappingConfigModel` with source type, claim name, scope mappings
4. Update `AuthService` to run `ScopeMapper` after authentication
5. Update middleware to:
   - Check global `required_scopes` from config
   - Accept endpoint-specific scope requirements as parameter
   - Reject requests missing required scopes
6. Surface `user_context.mxcp_scopes` to CEL policy engine
7. Add tests for mapping scenarios: groups to scopes, passthrough, multiple claims

**Outcome**: Stable MXCP entitlement vocabulary; enforceable per endpoint.

---

### Phase 6: Endpoint and Policy Integration

**Goal**: Per-endpoint scope requirements; CEL integration.

**Tasks**:
1. Extend endpoint YAML schema to accept scope annotations:
   - Under `annotations.scopes` list required MXCP scopes
2. Update existing `EndpointLoader` to index all referenced scopes across endpoints
3. Update execution wrapper to:
   - Read endpoint scope requirements from definition
   - Pass requirements to middleware for enforcement
4. Extend CEL user context object (in `PolicyEnforcer._user_context_to_dict`):
   - Add `user.mxcp_scopes` list for CEL expressions like `user.mxcp_scopes.exists(s, s == "admin")`
   - Add `user.provider_scopes` list for raw IdP scopes
5. Update policy enforcer to include new fields in CEL context
6. Optional: Add validation warning for undefined scopes in endpoints
7. Add tests for endpoint-level scope enforcement and CEL integration

**Outcome**: Builders define scopes per endpoint; policies can reference them.

---

### Phase 7: Proxy and Header Mode

**Goal**: Support deployments behind SSO-aware reverse proxies.

**Tasks**:
1. Define `ProxyAuthConfigModel` in SDK with:
   - Header names for user ID, username, email, scopes
   - Optional upstream token header for passthrough
   - Signature validation settings (header name, secret env, algorithm)
   - Optional mTLS requirement flag
2. Implement `ProxyAuthAdapter`:
   - Reads configured headers from request
   - Validates signature (HMAC) or mTLS if configured
   - Constructs `UserContextModel` from headers
   - Extracts upstream token if present
3. Integrate with `ScopeMapper`:
   - Scope header value parsed and mapped to MXCP scopes
   - Alternatively, accept pre-mapped scopes directly from proxy
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


```

Done. Updated the plan:

1. **CEL integration** – Changed from "CEL helper functions" to extending the user context object. The `PolicyEnforcer._user_context_to_dict` already builds a dict for CEL; we'll add `user.mxcp_scopes` and `user.provider_scopes` as lists that CEL expressions can query with standard list operations like `user.mxcp_scopes.exists(s, s == "admin")`.

2. **Admin tooling** – Removed all CLI references. Phase 9 now focuses on extending the existing admin REST API (Unix socket) with auth-specific endpoints:
   - `GET /auth/sessions`
   - `DELETE /auth/sessions/{id}`
   - `GET /auth/config`
   - `POST /auth/cleanup`

---

**User**

One small note: we use asyncio throughout the entire codebase only. so as we speak of background jobs, etc, it's meant to be async io. I also think that choice may be important across other decisions (locks?). Howover remember we can be serving multiple requests concurrently.

---

**Cursor**

Good point. The codebase is async-first, so:

- **Background cleanup** = `asyncio.create_task()` with periodic `await asyncio.sleep()`, not threads
- **Locks** = `asyncio.Lock` for coordinating concurrent requests (already used in `GeneralOAuthAuthorizationServer`)
- **SQLite I/O** = The existing `persistence.py` correctly uses `ThreadPoolExecutor` for blocking SQLite calls, but wraps them with async interfaces

Let me add a note about this to the plan:

```markdown
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
| `models.py` | `UserContextModel`, provider configs, `StateMetaModel`, etc. | Extend `UserContextModel` with `mxcp_scopes`; add mapping config models |
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
8. Add comprehensive tests for service instantiation and route registration

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
5. Add background cleanup job for expired sessions and tokens
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

**Outcome**: Long-lived sessions; provider tokens stay fresh; endpoints can call external APIs.

---

### Phase 5: Scope and Mapping Layer

**Goal**: Translate IdP claims to MXCP entitlements; enforce per endpoint.

**Tasks**:
1. Extend existing `UserContextModel` (in `mxcp.sdk.auth.models`) with:
   - `mxcp_scopes: set[str]` for internal entitlements
   - `provider_scopes: set[str]` for raw IdP scopes (currently not captured)
2. Create `ScopeMapper` class:
   - Accepts mapping configuration (claim type → scope mappings)
   - Given provider claims (scopes, groups, custom attributes) returns MXCP scopes
   - Supports multiple strategies: direct passthrough, group mapping, regex patterns
3. Define mapping config schema in SDK models:
   - `ClaimMappingConfigModel` with source type, claim name, scope mappings
4. Update `AuthService` to run `ScopeMapper` after authentication
5. Update middleware to:
   - Check global `required_scopes` from config
   - Accept endpoint-specific scope requirements as parameter
   - Reject requests missing required scopes
6. Surface `user_context.mxcp_scopes` to CEL policy engine
7. Add tests for mapping scenarios: groups to scopes, passthrough, multiple claims

**Outcome**: Stable MXCP entitlement vocabulary; enforceable per endpoint.

---

### Phase 6: Endpoint and Policy Integration

**Goal**: Per-endpoint scope requirements; CEL integration.

**Tasks**:
1. Extend endpoint YAML schema to accept scope annotations:
   - Under `annotations.scopes` list required MXCP scopes
2. Update existing `EndpointLoader` to index all referenced scopes across endpoints
3. Update execution wrapper to:
   - Read endpoint scope requirements from definition
   - Pass requirements to middleware for enforcement
4. Extend CEL user context object (in `PolicyEnforcer._user_context_to_dict`):
   - Add `user.mxcp_scopes` list for CEL expressions like `user.mxcp_scopes.exists(s, s == "admin")`
   - Add `user.provider_scopes` list for raw IdP scopes
5. Update policy enforcer to include new fields in CEL context
6. Optional: Add validation warning for undefined scopes in endpoints
7. Add tests for endpoint-level scope enforcement and CEL integration

**Outcome**: Builders define scopes per endpoint; policies can reference them.

---

### Phase 7: Proxy and Header Mode

**Goal**: Support deployments behind SSO-aware reverse proxies.

**Tasks**:
1. Define `ProxyAuthConfigModel` in SDK with:
   - Header names for user ID, username, email, scopes
   - Optional upstream token header for passthrough
   - Signature validation settings (header name, secret env, algorithm)
   - Optional mTLS requirement flag
2. Implement `ProxyAuthAdapter`:
   - Reads configured headers from request
   - Validates signature (HMAC) or mTLS if configured
   - Constructs `UserContextModel` from headers
   - Extracts upstream token if present
3. Integrate with `ScopeMapper`:
   - Scope header value parsed and mapped to MXCP scopes
   - Alternatively, accept pre-mapped scopes directly from proxy
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


```

```markdown
4. Update existing `AuthenticationMiddleware` to:
   - Use `SessionManager` instead of accessing `_token_mapping` directly
   - Hydrate `UserContext` from session
5. Update `GeneralOAuthAuthorizationServer` to delegate storage to `SessionManager`
6. Add async background task for expired session/token cleanup (periodic `asyncio.create_task`)
7. Migrate existing SQLite schema; provide data migration tooling
```

```markdown
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
| `models.py` | `UserContextModel`, provider configs, `StateMetaModel`, etc. | Extend `UserContextModel` with `mxcp_scopes`; add mapping config models |
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
8. Add comprehensive tests for service instantiation and route registration

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

**Outcome**: Long-lived sessions; provider tokens stay fresh; endpoints can call external APIs.

---

### Phase 5: Scope and Mapping Layer

**Goal**: Translate IdP claims to MXCP entitlements; enforce per endpoint.

**Tasks**:
1. Extend existing `UserContextModel` (in `mxcp.sdk.auth.models`) with:
   - `mxcp_scopes: set[str]` for internal entitlements
   - `provider_scopes: set[str]` for raw IdP scopes (currently not captured)
2. Create `ScopeMapper` class:
   - Accepts mapping configuration (claim type → scope mappings)
   - Given provider claims (scopes, groups, custom attributes) returns MXCP scopes
   - Supports multiple strategies: direct passthrough, group mapping, regex patterns
3. Define mapping config schema in SDK models:
   - `ClaimMappingConfigModel` with source type, claim name, scope mappings
4. Update `AuthService` to run `ScopeMapper` after authentication
5. Update middleware to:
   - Check global `required_scopes` from config
   - Accept endpoint-specific scope requirements as parameter
   - Reject requests missing required scopes
6. Surface `user_context.mxcp_scopes` to CEL policy engine
7. Add tests for mapping scenarios: groups to scopes, passthrough, multiple claims

**Outcome**: Stable MXCP entitlement vocabulary; enforceable per endpoint.

---

### Phase 6: Endpoint and Policy Integration

**Goal**: Per-endpoint scope requirements; CEL integration.

**Tasks**:
1. Extend endpoint YAML schema to accept scope annotations:
   - Under `annotations.scopes` list required MXCP scopes
2. Update existing `EndpointLoader` to index all referenced scopes across endpoints
3. Update execution wrapper to:
   - Read endpoint scope requirements from definition
   - Pass requirements to middleware for enforcement
4. Extend CEL user context object (in `PolicyEnforcer._user_context_to_dict`):
   - Add `user.mxcp_scopes` list for CEL expressions like `user.mxcp_scopes.exists(s, s == "admin")`
   - Add `user.provider_scopes` list for raw IdP scopes
5. Update policy enforcer to include new fields in CEL context
6. Optional: Add validation warning for undefined scopes in endpoints
7. Add tests for endpoint-level scope enforcement and CEL integration

**Outcome**: Builders define scopes per endpoint; policies can reference them.

---

### Phase 7: Proxy and Header Mode

**Goal**: Support deployments behind SSO-aware reverse proxies.

**Tasks**:
1. Define `ProxyAuthConfigModel` in SDK with:
   - Header names for user ID, username, email, scopes
   - Optional upstream token header for passthrough
   - Signature validation settings (header name, secret env, algorithm)
   - Optional mTLS requirement flag
2. Implement `ProxyAuthAdapter`:
   - Reads configured headers from request
   - Validates signature (HMAC) or mTLS if configured
   - Constructs `UserContextModel` from headers
   - Extracts upstream token if present
3. Integrate with `ScopeMapper`:
   - Scope header value parsed and mapped to MXCP scopes
   - Alternatively, accept pre-mapped scopes directly from proxy
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


```

Done. Added a "Design Constraints" section covering the async-first architecture:

- Multiple requests served concurrently via asyncio event loop
- Use `asyncio.Lock` for shared state coordination
- Background tasks via `asyncio.create_task()` with periodic sleep
- `ThreadPoolExecutor` only for unavoidable blocking I/O (SQLite), exposed as async interfaces
- No threading for request concurrency

Also updated Phase 2 to explicitly mention the cleanup task is async (`asyncio.create_task`).

---

**User**

are we not confusing mxcp scopes, mxcp entitlements and provider scopes? we map provider scopes to mxcp scopes. but those are same as entitlments we'd use in endpoints? do we send back the mxcp scopes and cross check on receival?

---

**Cursor**

Good catch – let me clarify the terminology:

**Provider scopes** = What the IdP understands (e.g., `https://www.googleapis.com/auth/calendar.readonly`, Keycloak roles, Google groups). We receive these during OAuth.

**MXCP scopes** = Our internal authorization vocabulary, used in endpoint YAML `annotations.scopes`. These ARE the entitlements – same thing, different name.

**The flow:**

1. User authenticates → IdP returns provider scopes/groups/claims
2. `ScopeMapper` translates provider claims → MXCP scopes (stored in session server-side)
3. We issue opaque MXCP token (`mcp_...`) to client – **no scopes embedded**
4. On each request: middleware loads session → gets `mxcp_scopes` from session → checks against endpoint requirements

**We don't send MXCP scopes to the client** – they're purely server-side enforcement. The client just holds an opaque token; the server looks up what scopes that session has.

So there's no "cross-check on receival" in the OAuth sense. It's:
- Session created → MXCP scopes computed and stored
- Request arrives → load session → enforce stored scopes

The plan should probably use consistent terminology. I'd suggest:
- **Provider scopes/claims** = what IdP gives us
- **MXCP scopes** = our internal entitlements (drop "entitlements" as separate term)

Want me to update the plan to use consistent terminology?

---

**User**

does tihs affect the proxy case at all then? so mxcp scopes never go out - they are just internal

---

**Cursor**

```yaml
scope_header: X-MXCP-Scopes
```

Correct – MXCP scopes never go to the **client**. They're purely server-side.

**Proxy mode** is still server-to-server (trusted infrastructure):

- **Option A**: Proxy passes raw IdP claims (groups, roles) → MXCP runs `ScopeMapper` to compute MXCP scopes
  ```
  X-User-Groups: admins,billing-team
  ```
  MXCP maps `admins` → `mxcp.admin`, etc.

- **Option B**: Proxy passes pre-computed MXCP scopes (proxy/SSO already did the mapping)
  ```
  X-MXCP-Scopes: admin,billing.read
  ```
  MXCP trusts these directly (signature-verified).

Either way, the client (browser, MCP client) never sees MXCP scopes. The scopes flow between trusted server-side components only.

The plan's `scope_header: X-MXCP-Scopes` implies Option B, but we could support both:
- If `scope_header` is set → trust pre-mapped scopes from proxy
- If `claim_mappings` + group/role headers are set → MXCP does the mapping

So to answer directly: **no impact on proxy case** – MXCP scopes remain internal. They just come from a different trusted source (proxy headers vs IdP response).

```plaintext
  X-User-Groups: admins,billing-team
```

```plaintext
  X-MXCP-Scopes: admin,billing.read
```

---

**User**

But when we go to google, we can ask many things. WE may get some or fewer (e.g. an mcp server in mxcp that has email and/or calendar - so some endpoints work others not). Means in the original flow we have to ask many things? how does it even work?

---

**Cursor**

Great question – this reveals two distinct concerns:

**Provider scopes** = Capability – "Can we call Google Calendar API on behalf of this user?"

**MXCP scopes** = Authorization – "Is this user allowed to invoke this endpoint?"

They're orthogonal. Here's how the flow works:

### OAuth Request
Config declares what provider scopes the server needs:
```yaml
auth:
  google:
    scope: "openid email https://www.googleapis.com/auth/calendar.readonly"
```

### What Actually Gets Granted
User might consent to only some scopes (Google allows selective consent). The token response tells us what was actually granted. We should store this in the session as `provider_scopes_granted`.

### Per-Endpoint Requirements
Endpoints could declare both:
```yaml
tool:
  name: list-calendar-events
  annotations:
    scopes: [calendar.viewer]  # MXCP authorization
    provider_scopes: [https://www.googleapis.com/auth/calendar.readonly]  # capability needed
```

### Runtime Check
1. Does user have required MXCP scopes? → 403 "Not authorized"
2. Does user have required provider scopes granted? → 403 "Missing capability" or graceful degradation

### What We Don't Do Today
We request scopes but don't track what was actually granted vs requested. The plan should include:
- Store `provider_scopes_granted` in session (from token response)
- Allow endpoints to declare required provider scopes
- Check at runtime before calling upstream APIs

This means the scope mapping is:
- IdP grants provider scopes → we store what was granted
- Optionally map to MXCP scopes for authorization
- Endpoint can require either/both

Want me to update the plan to distinguish these two concerns more clearly?

```yaml
auth:
  google:
    scope: "openid email https://www.googleapis.com/auth/calendar.readonly"
```

```yaml
tool:
  name: list-calendar-events
  annotations:
    scopes: [calendar.viewer]  # MXCP authorization
    provider_scopes: [https://www.googleapis.com/auth/calendar.readonly]  # capability needed
```

---

**User**

so, i tihnk this is user config (global). So right now we ask what we ask and i guess we fail if we dont get it all. Is that common?

auth:



  google:

    scope: "openid email https://www.googleapis.com/auth/calendar.readonly"

does it make sense to have some optional stuff that then alllows us to block just those endpoints (becuase we map google scopes to mxcp scopes and then at endpoint level we ever only mention mxcp scopes, for better governance - anyway we have a mapping layer right?)

or always ask evrything and that's it? and do tokens come anyway with 'more stuff' if we dont ask for it?

or is blocking enough, and anyway we look at other stuff in the token to distinguish?

---

**Cursor**

```yaml


auth:
  google:
    required_scopes: "openid email"  # fail auth if not granted
    optional_scopes: "https://www.googleapis.com/auth/calendar.readonly"  # nice to have
```

You're onto a cleaner model. Let me break it down:

**How it typically works:**
- You request scopes, IdP may grant all or some (Google allows selective consent)
- Tokens don't give you MORE than you asked for
- But tokens/profiles include OTHER claims beyond scopes: groups, roles, email, custom attributes

**The elegant unification via mapping layer:**

```yaml
# Config (user-level)
auth:
  google:
    required_scopes: "openid email"           # fail auth entirely if not granted
    optional_scopes: "calendar.readonly drive.readonly"  # nice to have
    
    claim_mappings:
      scopes:
        "calendar.readonly": [calendar.read]   # → MXCP scope
        "drive.readonly": [files.read]
      groups:
        "billing-team@company.com": [billing.admin]
```

```yaml
# Endpoint (only MXCP scopes, never provider-specific)
tool:
  name: list-calendar-events
  annotations:
    scopes: [calendar.read]  # MXCP scope only
```

**Flow:**
1. Request all scopes (required + optional)
2. Auth succeeds if required scopes granted (fail otherwise)
3. Check what was actually granted (required + whichever optional)
4. Mapping produces MXCP scopes from granted provider scopes + claims
5. User's `mxcp_scopes` = only what they actually have
6. Endpoint blocked if user lacks required MXCP scope

**Result:**
- User didn't grant calendar? → No `calendar.read` in their MXCP scopes → endpoint blocked
- Endpoints never mention Google/Keycloak specifics (governance/portability)
- Single abstraction layer handles everything

**Is failing on missing required scopes common?**
Yes, very common. Most apps have a minimum set they need to function. Optional scopes for enhanced features is also common (LinkedIn, Google, etc. do this).

So: **required + optional scopes in config, map everything through, endpoints only see MXCP scopes**. Clean.

Want me to update the plan with this model?

```yaml
# Config (user-level)
auth:
  google:
    required_scopes: "openid email"           # fail auth entirely if not granted
    optional_scopes: "calendar.readonly drive.readonly"  # nice to have
    
    claim_mappings:
      scopes:
        "calendar.readonly": [calendar.read]   # → MXCP scope
        "drive.readonly": [files.read]
      groups:
        "billing-team@company.com": [billing.admin]
```

```yaml
# Endpoint (only MXCP scopes, never provider-specific)
tool:
  name: list-calendar-events
  annotations:
    scopes: [calendar.read]  # MXCP scope only
```

---

**User**

Yes.

---

**Cursor**

```markdown
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

### Unified Scope Model

MXCP uses a single abstraction layer for authorization. Endpoints only reference MXCP scopes, never provider-specific scopes.

**Provider scopes** = What we request from IdP (Google, Keycloak, etc.)
- Split into `required_scopes` (fail auth if not granted) and `optional_scopes` (graceful degradation)
- Stored as `provider_scopes_granted` in session after auth

**MXCP scopes** = Internal authorization vocabulary used by endpoints and policies
- Derived from provider scopes, groups, roles, and other claims via mapping
- Endpoints only ever reference these (governance, portability)

**Flow**:
1. Auth requests required + optional provider scopes
2. Auth succeeds if required scopes granted; record what was actually granted
3. `ScopeMapper` translates granted provider scopes + claims → MXCP scopes
4. User's `mxcp_scopes` only includes what they actually have
5. Endpoint requiring `calendar.read` blocked if user didn't grant the provider scope that maps to it

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
```

**Endpoint example** (only MXCP scopes):
```yaml
tool:
  name: list-calendar-events
  annotations:
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
| `models.py` | `UserContextModel`, provider configs, `StateMetaModel`, etc. | Extend `UserContextModel` with `mxcp_scopes`; add mapping config models |
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
8. Add comprehensive tests for service instantiation and route registration

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

**Outcome**: Long-lived sessions; provider tokens stay fresh; endpoints can call external APIs.

---

### Phase 5: Scope and Mapping Layer

**Goal**: Translate IdP claims to MXCP entitlements; enforce per endpoint.

**Tasks**:
1. Extend existing `UserContextModel` (in `mxcp.sdk.auth.models`) with:
   - `mxcp_scopes: set[str]` for internal entitlements
   - `provider_scopes: set[str]` for raw IdP scopes (currently not captured)
2. Create `ScopeMapper` class:
   - Accepts mapping configuration (claim type → scope mappings)
   - Given provider claims (scopes, groups, custom attributes) returns MXCP scopes
   - Supports multiple strategies: direct passthrough, group mapping, regex patterns
3. Define mapping config schema in SDK models:
   - `ClaimMappingConfigModel` with source type, claim name, scope mappings
4. Update `AuthService` to run `ScopeMapper` after authentication
5. Update middleware to:
   - Check global `required_scopes` from config
   - Accept endpoint-specific scope requirements as parameter
   - Reject requests missing required scopes
6. Surface `user_context.mxcp_scopes` to CEL policy engine
7. Add tests for mapping scenarios: groups to scopes, passthrough, multiple claims

**Outcome**: Stable MXCP entitlement vocabulary; enforceable per endpoint.

---

### Phase 6: Endpoint and Policy Integration

**Goal**: Per-endpoint scope requirements; CEL integration.

**Tasks**:
1. Extend endpoint YAML schema to accept scope annotations:
   - Under `annotations.scopes` list required MXCP scopes
2. Update existing `EndpointLoader` to index all referenced scopes across endpoints
3. Update execution wrapper to:
   - Read endpoint scope requirements from definition
   - Pass requirements to middleware for enforcement
4. Extend CEL user context object (in `PolicyEnforcer._user_context_to_dict`):
   - Add `user.mxcp_scopes` list for CEL expressions like `user.mxcp_scopes.exists(s, s == "admin")`
   - Add `user.provider_scopes` list for raw IdP scopes
5. Update policy enforcer to include new fields in CEL context
6. Optional: Add validation warning for undefined scopes in endpoints
7. Add tests for endpoint-level scope enforcement and CEL integration

**Outcome**: Builders define scopes per endpoint; policies can reference them.

---

### Phase 7: Proxy and Header Mode

**Goal**: Support deployments behind SSO-aware reverse proxies.

**Tasks**:
1. Define `ProxyAuthConfigModel` in SDK with:
   - Header names for user ID, username, email, scopes
   - Optional upstream token header for passthrough
   - Signature validation settings (header name, secret env, algorithm)
   - Optional mTLS requirement flag
2. Implement `ProxyAuthAdapter`:
   - Reads configured headers from request
   - Validates signature (HMAC) or mTLS if configured
   - Constructs `UserContextModel` from headers
   - Extracts upstream token if present
3. Integrate with `ScopeMapper`:
   - Scope header value parsed and mapped to MXCP scopes
   - Alternatively, accept pre-mapped scopes directly from proxy
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


```

```markdown
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

### Unified Scope Model

MXCP uses a single abstraction layer for authorization. Endpoints only reference MXCP scopes, never provider-specific scopes.

**Provider scopes** = What we request from IdP (Google, Keycloak, etc.)
- Split into `required_scopes` (fail auth if not granted) and `optional_scopes` (graceful degradation)
- Stored as `provider_scopes_granted` in session after auth

**MXCP scopes** = Internal authorization vocabulary used by endpoints and policies
- Derived from provider scopes, groups, roles, and other claims via mapping
- Endpoints only ever reference these (governance, portability)

**Flow**:
1. Auth requests required + optional provider scopes
2. Auth succeeds if required scopes granted; record what was actually granted
3. `ScopeMapper` translates granted provider scopes + claims → MXCP scopes
4. User's `mxcp_scopes` only includes what they actually have
5. Endpoint requiring `calendar.read` blocked if user didn't grant the provider scope that maps to it

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
```

**Endpoint example** (only MXCP scopes):
```yaml
tool:
  name: list-calendar-events
  annotations:
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
| `models.py` | `UserContextModel`, provider configs, `StateMetaModel`, etc. | Extend `UserContextModel` with `mxcp_scopes`; add mapping config models |
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
8. Add comprehensive tests for service instantiation and route registration

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
   - Request required + optional scopes during authorization
   - Parse token response for actually granted scopes
   - Fail auth if required scopes missing; continue if optional missing
4. Create `ScopeMapper` class:
   - Reads `claim_mappings` config
   - Given granted provider scopes + claims (groups, roles) → computes MXCP scopes
   - Only maps scopes that were actually granted
5. Update `AuthService` to run `ScopeMapper` after successful auth
6. Update middleware to:
   - Check global `required_scopes` (MXCP scopes, not provider scopes)
   - Accept endpoint-specific MXCP scope requirements
   - Reject requests where user lacks required MXCP scopes
7. Add tests for: partial grant scenarios, mapping combinations, required vs optional

**Outcome**: Endpoints only reference MXCP scopes; missing provider scopes automatically block corresponding endpoints.

---

### Phase 6: Endpoint and Policy Integration

**Goal**: Per-endpoint scope requirements; CEL integration.

**Tasks**:
1. Extend endpoint YAML schema to accept scope annotations:
   - Under `annotations.scopes` list required MXCP scopes
2. Update existing `EndpointLoader` to index all referenced scopes across endpoints
3. Update execution wrapper to:
   - Read endpoint scope requirements from definition
   - Pass requirements to middleware for enforcement
4. Extend CEL user context object (in `PolicyEnforcer._user_context_to_dict`):
   - Add `user.mxcp_scopes` list for CEL expressions like `user.mxcp_scopes.exists(s, s == "admin")`
   - Add `user.provider_scopes` list for raw IdP scopes
5. Update policy enforcer to include new fields in CEL context
6. Optional: Add validation warning for undefined scopes in endpoints
7. Add tests for endpoint-level scope enforcement and CEL integration

**Outcome**: Builders define scopes per endpoint; policies can reference them.

---

### Phase 7: Proxy and Header Mode

**Goal**: Support deployments behind SSO-aware reverse proxies.

**Tasks**:
1. Define `ProxyAuthConfigModel` in SDK with:
   - Header names for user ID, username, email, scopes
   - Optional upstream token header for passthrough
   - Signature validation settings (header name, secret env, algorithm)
   - Optional mTLS requirement flag
2. Implement `ProxyAuthAdapter`:
   - Reads configured headers from request
   - Validates signature (HMAC) or mTLS if configured
   - Constructs `UserContextModel` from headers
   - Extracts upstream token if present
3. Integrate with `ScopeMapper`:
   - Scope header value parsed and mapped to MXCP scopes
   - Alternatively, accept pre-mapped scopes directly from proxy
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


```

```markdown
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

### Unified Scope Model

MXCP uses a single abstraction layer for authorization. Endpoints only reference MXCP scopes, never provider-specific scopes.

**Provider scopes** = What we request from IdP (Google, Keycloak, etc.)
- Split into `required_scopes` (fail auth if not granted) and `optional_scopes` (graceful degradation)
- Stored as `provider_scopes_granted` in session after auth

**MXCP scopes** = Internal authorization vocabulary used by endpoints and policies
- Derived from provider scopes, groups, roles, and other claims via mapping
- Endpoints only ever reference these (governance, portability)

**Flow**:
1. Auth requests required + optional provider scopes
2. Auth succeeds if required scopes granted; record what was actually granted
3. `ScopeMapper` translates granted provider scopes + claims → MXCP scopes
4. User's `mxcp_scopes` only includes what they actually have
5. Endpoint requiring `calendar.read` blocked if user didn't grant the provider scope that maps to it

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
```

**Endpoint example** (only MXCP scopes):
```yaml
tool:
  name: list-calendar-events
  annotations:
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
| `models.py` | `UserContextModel`, provider configs, `StateMetaModel`, etc. | Extend `UserContextModel` with `mxcp_scopes`; add mapping config models |
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
8. Add comprehensive tests for service instantiation and route registration

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
   - Request required + optional scopes during authorization
   - Parse token response for actually granted scopes
   - Fail auth if required scopes missing; continue if optional missing
4. Create `ScopeMapper` class:
   - Reads `claim_mappings` config
   - Given granted provider scopes + claims (groups, roles) → computes MXCP scopes
   - Only maps scopes that were actually granted
5. Update `AuthService` to run `ScopeMapper` after successful auth
6. Update middleware to:
   - Check global `required_scopes` (MXCP scopes, not provider scopes)
   - Accept endpoint-specific MXCP scope requirements
   - Reject requests where user lacks required MXCP scopes
7. Add tests for: partial grant scenarios, mapping combinations, required vs optional

**Outcome**: Endpoints only reference MXCP scopes; missing provider scopes automatically block corresponding endpoints.

---

### Phase 6: Endpoint and Policy Integration

**Goal**: Per-endpoint MXCP scope requirements; CEL integration.

**Tasks**:
1. Extend endpoint YAML schema to accept scope annotations:
   - Under `annotations.scopes` list required MXCP scopes (never provider-specific)
2. Update existing `EndpointLoader` to index all referenced MXCP scopes across endpoints
3. Update execution wrapper to:
   - Read endpoint scope requirements from definition
   - Pass requirements to middleware for enforcement
   - Block execution if user lacks required MXCP scopes
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
   - Header names for user ID, username, email, scopes
   - Optional upstream token header for passthrough
   - Signature validation settings (header name, secret env, algorithm)
   - Optional mTLS requirement flag
2. Implement `ProxyAuthAdapter`:
   - Reads configured headers from request
   - Validates signature (HMAC) or mTLS if configured
   - Constructs `UserContextModel` from headers
   - Extracts upstream token if present
3. Integrate with `ScopeMapper`:
   - Scope header value parsed and mapped to MXCP scopes
   - Alternatively, accept pre-mapped scopes directly from proxy
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


```

```markdown
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

### Unified Scope Model

MXCP uses a single abstraction layer for authorization. Endpoints only reference MXCP scopes, never provider-specific scopes.

**Provider scopes** = What we request from IdP (Google, Keycloak, etc.)
- Split into `required_scopes` (fail auth if not granted) and `optional_scopes` (graceful degradation)
- Stored as `provider_scopes_granted` in session after auth

**MXCP scopes** = Internal authorization vocabulary used by endpoints and policies
- Derived from provider scopes, groups, roles, and other claims via mapping
- Endpoints only ever reference these (governance, portability)

**Flow**:
1. Auth requests required + optional provider scopes
2. Auth succeeds if required scopes granted; record what was actually granted
3. `ScopeMapper` translates granted provider scopes + claims → MXCP scopes
4. User's `mxcp_scopes` only includes what they actually have
5. Endpoint requiring `calendar.read` blocked if user didn't grant the provider scope that maps to it

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
```

**Endpoint example** (only MXCP scopes):
```yaml
tool:
  name: list-calendar-events
  annotations:
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
| `models.py` | `UserContextModel`, provider configs, `StateMetaModel`, etc. | Extend `UserContextModel` with `mxcp_scopes`; add mapping config models |
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
8. Add comprehensive tests for service instantiation and route registration

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
   - Request required + optional scopes during authorization
   - Parse token response for actually granted scopes
   - Fail auth if required scopes missing; continue if optional missing
4. Create `ScopeMapper` class:
   - Reads `claim_mappings` config
   - Given granted provider scopes + claims (groups, roles) → computes MXCP scopes
   - Only maps scopes that were actually granted
5. Update `AuthService` to run `ScopeMapper` after successful auth
6. Update middleware to:
   - Check global `required_scopes` (MXCP scopes, not provider scopes)
   - Accept endpoint-specific MXCP scope requirements
   - Reject requests where user lacks required MXCP scopes
7. Add tests for: partial grant scenarios, mapping combinations, required vs optional

**Outcome**: Endpoints only reference MXCP scopes; missing provider scopes automatically block corresponding endpoints.

---

### Phase 6: Endpoint and Policy Integration

**Goal**: Per-endpoint MXCP scope requirements; CEL integration.

**Tasks**:
1. Extend endpoint YAML schema to accept scope annotations:
   - Under `annotations.scopes` list required MXCP scopes (never provider-specific)
2. Update existing `EndpointLoader` to index all referenced MXCP scopes across endpoints
3. Update execution wrapper to:
   - Read endpoint scope requirements from definition
   - Pass requirements to middleware for enforcement
   - Block execution if user lacks required MXCP scopes
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


```

```markdown
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

### Unified Scope Model

MXCP uses a single abstraction layer for authorization. Endpoints only reference MXCP scopes, never provider-specific scopes.

**Provider scopes** = What we request from IdP (Google, Keycloak, etc.)
- Split into `required_scopes` (fail auth if not granted) and `optional_scopes` (graceful degradation)
- Stored as `provider_scopes_granted` in session after auth

**MXCP scopes** = Internal authorization vocabulary used by endpoints and policies
- Derived from provider scopes, groups, roles, and other claims via mapping
- Endpoints only ever reference these (governance, portability)

**Flow**:
1. Auth requests required + optional provider scopes
2. Auth succeeds if required scopes granted; record what was actually granted
3. `ScopeMapper` translates granted provider scopes + claims → MXCP scopes
4. User's `mxcp_scopes` only includes what they actually have
5. Endpoint requiring `calendar.read` blocked if user didn't grant the provider scope that maps to it

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
```

**Endpoint example** (only MXCP scopes):
```yaml
tool:
  name: list-calendar-events
  annotations:
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
8. Add comprehensive tests for service instantiation and route registration

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
   - Request required + optional scopes during authorization
   - Parse token response for actually granted scopes
   - Fail auth if required scopes missing; continue if optional missing
4. Create `ScopeMapper` class:
   - Reads `claim_mappings` config
   - Given granted provider scopes + claims (groups, roles) → computes MXCP scopes
   - Only maps scopes that were actually granted
5. Update `AuthService` to run `ScopeMapper` after successful auth
6. Update middleware to:
   - Check global `required_scopes` (MXCP scopes, not provider scopes)
   - Accept endpoint-specific MXCP scope requirements
   - Reject requests where user lacks required MXCP scopes
7. Add tests for: partial grant scenarios, mapping combinations, required vs optional

**Outcome**: Endpoints only reference MXCP scopes; missing provider scopes automatically block corresponding endpoints.

---

### Phase 6: Endpoint and Policy Integration

**Goal**: Per-endpoint MXCP scope requirements; CEL integration.

**Tasks**:
1. Extend endpoint YAML schema to accept scope annotations:
   - Under `annotations.scopes` list required MXCP scopes (never provider-specific)
2. Update existing `EndpointLoader` to index all referenced MXCP scopes across endpoints
3. Update execution wrapper to:
   - Read endpoint scope requirements from definition
   - Pass requirements to middleware for enforcement
   - Block execution if user lacks required MXCP scopes
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


```

Done. Updated the plan with the unified scope model:

1. **New "Unified Scope Model" section** in Design Constraints explaining:
   - `required_scopes` vs `optional_scopes` in provider config
   - Mapping from provider scopes/claims → MXCP scopes
   - Endpoints only reference MXCP scopes
   - Missing provider scopes automatically block corresponding endpoints

2. **Phase 5 rewritten** to cover:
   - Provider config updates (`required_scopes`, `optional_scopes`, `claim_mappings`)
   - `UserContextModel` with `mxcp_scopes` + `provider_scopes_granted`
   - Auth fails if required scopes missing; continues if optional missing
   - `ScopeMapper` only maps actually granted scopes

3. **Phase 6 clarified**: Endpoints only reference MXCP scopes (never provider-specific)

4. **Phase 7 (proxy)** updated with two modes:
   - Raw claims mode: proxy sends groups/roles → MXCP maps them
   - Pre-mapped mode: proxy sends MXCP scopes directly

5. **Inventory table** updated to reflect model changes

---

**User**

can u double check if that truly is common? review this mxcp vs provider scopes stuff we just changed

---

**Cursor**

Yep, this pattern is very common in OAuth-based apps:

- **Provider scopes** are what the IdP understands and enforces when issuing tokens. They just say “Google can now call Calendar API on behalf of Alice.”
- **App-specific entitlements** sit on top and model the product’s own authorization needs. Nearly every SaaS does this—e.g. GitHub maps OAuth scopes and org memberships into its own roles (repo admin, billing manager). Microsoft and Okta call these “app roles.”
- **Why keep them separate?** Because you want a stable vocabulary across providers and proxy modes, and you may want to combine multiple IdP claims (group + scope) into one entitlement. Also, endpoints shouldn’t care whether the capability came from Google scope, Keycloak role, proxy header, or operator override.

The flow we outlined (request required + optional provider scopes, map whatever the IdP actually granted into MXCP scopes, and have endpoints reference only MXCP scopes) is the standard way to combine capability (provider scope) and authorization (app scope) without leaking provider-specific details into your endpoint schema. You’ll see the same pattern in:

- OAuth resource servers that define custom scopes and map IdP claims into them
- Zero-trust systems (e.g., BeyondCorp) that take SAML attributes and map to app roles
- Cloud providers (AWS IAM Identity Center, Azure Entra) mapping federated attributes to custom roles/scopes

So yes, “ask for capability from provider, map to app-level entitlements, enforce entitlements per endpoint” is the norm.

---

**User**

do not change spec. WHat about non-JWT tokens? any changes needed for that?

---

**Cursor**

Sticking to the existing spec: we’ll keep issuing opaque MXCP access tokens (`mcp_…`) just like today. Nothing in the plan requires switching to JWTs. The new `SessionManager` still hands out opaque tokens, stores session state server-side, and the middleware looks up sessions before enforcing scopes. Provider tokens (Google JWTs, etc.) remain as-is; we treat them as opaque blobs and store them encrypted.

So **no changes needed for non-JWT tokens**:
- MXCP tokens stay opaque strings
- Session lookup continues to happen server-side
- Refresh flow just rotates the opaque token and updates the session entry

This keeps us fully compatible with non-JWT tokens and avoids any spec change.

---

**User**

if the provider is non-jwt... how does claim mapping work? do not change

---

**Cursor**

Nothing needs to change. Claim mapping doesn’t require JWTs—it only needs the claims themselves, and we already fetch those via each provider’s API when we build `UserContextModel`.

- For JWT-based providers, scopes/groups might be in the token itself.
- For opaque-token providers (Google, Atlassian, etc.), we already call their userinfo/graph endpoints to fetch the profile and granted scopes.
- The mapping layer just consumes whatever data we put in `UserContextModel.raw_profile` and the new `provider_scopes_granted` set.

So even if the provider hands us only an opaque access token, we still do a follow-up API call (as we do today) to retrieve claims, then run them through the mapping. No spec change needed.

---

**User**

What do I request? required_scopes+optional_scopes or is there a way to imnply that some are optional? Or we ask them all, get what we get, and assess if it fits our required_scopes minimal set ourselves? IS this provider dependent or generic?

---

**Cursor**

OAuth doesn’t have a portable way to flag “optional” scopes. The practical approach is:

- **Request the union** (`required_scopes + optional_scopes`) in the authorize URL.
- The provider grants a subset. We inspect the token response/userinfo to see what was actually granted.
- If the grant is missing any `required_scopes`, we fail authentication ourselves.
- Whatever optional scopes did come back get mapped to MXCP scopes; endpoints that need them will work, others simply won’t.

A few providers have proprietary ways to mark optional scopes (e.g., Google’s incremental auth), but there’s no standard. Treating everything the same (request all, enforce required locally, degrade gracefully for optional) works for every provider we support today.

---

**User**

so perhaps this mapping code better be kept per provider anyway, because consider jwt vs opaque or optional vs required, it's provider dependent?

---

**Cursor**

No need to split the mapping code per provider. Providers differ in how we **fetch** claims (JWT vs opaque token, userinfo endpoint, etc.), but once we have the raw scopes/claims we normalize them in `UserContextModel` and run a single `ScopeMapper`. The adapter already handles provider-specific steps (state, token exchange, userinfo). That keeps the rest of the system provider-agnostic and lets proxy mode share the same mapper.

---

**User**

ok great, can u apply these clarifications to the spec?

also, instead of this:

@auth-redesign-plan.md (61-64) 

we want scopes at the tool, prompt, resource definition level e.g.

tool:

  ...

  scopes: [calendar.read]



same for prompts and resources.

---

**Cursor**

```markdown
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
```

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
8. Add comprehensive tests for service instantiation and route registration

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
   - Request required + optional scopes during authorization
   - Parse token response for actually granted scopes
   - Fail auth if required scopes missing; continue if optional missing
4. Create `ScopeMapper` class:
   - Reads `claim_mappings` config
   - Given granted provider scopes + claims (groups, roles) → computes MXCP scopes
   - Only maps scopes that were actually granted
5. Update `AuthService` to run `ScopeMapper` after successful auth
6. Update middleware to:
   - Check global `required_scopes` (MXCP scopes, not provider scopes)
   - Accept endpoint-specific MXCP scope requirements
   - Reject requests where user lacks required MXCP scopes
7. Add tests for: partial grant scenarios, mapping combinations, required vs optional

**Outcome**: Endpoints only reference MXCP scopes; missing provider scopes automatically block corresponding endpoints.

---

### Phase 6: Endpoint and Policy Integration

**Goal**: Per-endpoint MXCP scope requirements; CEL integration.

**Tasks**:
1. Extend endpoint YAML schema to accept scope annotations:
   - Under `annotations.scopes` list required MXCP scopes (never provider-specific)
2. Update existing `EndpointLoader` to index all referenced MXCP scopes across endpoints
3. Update execution wrapper to:
   - Read endpoint scope requirements from definition
   - Pass requirements to middleware for enforcement
   - Block execution if user lacks required MXCP scopes
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


```

```markdown
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
```

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
8. Add comprehensive tests for service instantiation and route registration

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
   - Request required + optional scopes during authorization
   - Parse token response for actually granted scopes
   - Fail auth if required scopes missing; continue if optional missing
4. Create `ScopeMapper` class:
   - Reads `claim_mappings` config
   - Given granted provider scopes + claims (groups, roles) → computes MXCP scopes
   - Only maps scopes that were actually granted
5. Update `AuthService` to run `ScopeMapper` after successful auth
6. Update middleware to:
   - Check global `required_scopes` (MXCP scopes, not provider scopes)
   - Accept endpoint-specific MXCP scope requirements
   - Reject requests where user lacks required MXCP scopes
7. Add tests for: partial grant scenarios, mapping combinations, required vs optional

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
   - Pass requirements to middleware for enforcement
   - Block execution if user lacks required MXCP scopes
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


```

```markdown
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
```

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
8. Add comprehensive tests for service instantiation and route registration

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
   - Request required + optional scopes during authorization
   - Parse token response for actually granted scopes
   - Fail auth if required scopes missing; continue if optional missing
4. Create `ScopeMapper` class:
   - Reads `claim_mappings` config
   - Given granted provider scopes + claims (groups, roles) → computes MXCP scopes
   - Only maps scopes that were actually granted
5. Update `AuthService` to run `ScopeMapper` after successful auth
6. Update middleware to:
   - Check global `required_scopes` (MXCP scopes, not provider scopes)
   - Accept endpoint-specific MXCP scope requirements
   - Reject requests where user lacks required MXCP scopes
7. Add tests for: partial grant scenarios, mapping combinations, required vs optional

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
   - Pass requirements to middleware for enforcement
   - Block execution if user lacks required MXCP scopes
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


```

```markdown
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
```

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
8. Add comprehensive tests for service instantiation and route registration

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
7. Add tests for: partial grant scenarios, mapping combinations, required vs optional

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
   - Pass requirements to middleware for enforcement
   - Block execution if user lacks required MXCP scopes
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


```

Done. Applied all clarifications:

1. **Opaque MXCP Tokens** – Added new section in Design Constraints confirming we keep opaque tokens (`mcp_…`), not JWTs. Server-side session lookup on each request.

2. **Flow clarified** – Now explicitly says "request the union of required + optional scopes", provider grants subset, we check required locally.

3. **Provider-agnostic mapping** – Added note that adapters handle provider-specific claim fetching (JWT vs userinfo endpoint), then a single `ScopeMapper` works for all providers and proxy mode.

4. **Scopes at definition level** – Changed from `annotations.scopes` to top-level `scopes` field:
   ```yaml
   tool:
     name: list-calendar-events
     scopes: [calendar.read]
   ```
   Phase 6 updated to reflect `tool.scopes`, `prompt.scopes`, `resource.scopes`.

5. **Phase 5 adapter tasks** – Clarified adapters normalize into `UserContextModel.provider_scopes_granted` via provider-specific means, then mapper is provider-agnostic.

```yaml
   tool:
     name: list-calendar-events
     scopes: [calendar.read]
```

---

**User**

Another case is: suppose they run Keycloak and they have Keycloak configured to also obtain Google tokens on-demand as refresh tokens (i don't recall the terminology for this setup). How it'd fit this architecture? Users get mxcp tokens still. But we'd need (on-demand during tool execution?) to go to keycloak and ask for that google token... But this seems to have to be done per tool implementation, not really a frameowrk level setup? Or am I missing something?

---

**Cursor**

Great example. In that “Keycloak as broker for Google” setup:

- MXCP still authenticates against Keycloak → user gets the usual MXCP opaque token.
- The provider adapter we plug in is the Keycloak adapter. During login it gets a Keycloak access token and refresh token (plus whatever claims Keycloak exposes).
- Keycloak knows nothing about the downstream Google APIs until you ask. To call Google, you’d use Keycloak’s token-exchange endpoint (OAuth 2.0 Token Exchange) to swap the Keycloak token for a Google token on demand.

How this fits the plan:

1. The SDK helper (`get_provider_token("keycloak", user_context, audience="google")`) can be extended to accept parameters describing the target audience/resource.
2. The Keycloak adapter implements `refresh()` and can add a method for token exchange (essentially a specialized refresh). When the helper asks for `audience="google"`, the adapter calls Keycloak’s token exchange endpoint, caches the returned Google token for that user/session, and hands it back to the tool.
3. Tools keep calling the helper; they never deal with raw Keycloak or Google APIs directly.

So you’re right: the actual “call Google” logic happens inside the tool implementation, but the plumbing (storing Keycloak refresh tokens, calling token exchange, caching the downstream Google tokens) still lives in the auth SDK’s provider adapter. The tool code just says “give me a Google-capable token via Keycloak” and the adapter handles the on-demand exchange.

---

**User**

Are you sure? Can't it be done at framework level instead?

---

**Cursor**

Yes, we can handle that at the framework level. The Keycloak adapter already owns the refresh token, so it can expose a helper like `get_provider_token(provider="keycloak", resource="google")` that performs OAuth 2.0 Token Exchange under the hood. The framework would need a bit of config telling it which downstream audience/resource to request, but once that’s configured the SDK can do the exchange, cache the Google token in the session, and hand it to tools transparently. Tool authors would just call the helper; they wouldn’t have to write token-exchange logic themselves.

---

**User**

but tools authors still need to implement security inside the tool; it can't just be in yaml files in the scopes definition, as in the earlier case? Can u find a way to support that?

---

**Cursor**

```markdown
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
```

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
8. Add comprehensive tests for service instantiation and route registration

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
   - Example: `calendar.read` → `{provider: keycloak, audience: google}`
   - AuthService uses this to know which provider tokens/token exchanges to perform automatically
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


```

We can cover the Keycloak→Google “broker” scenario entirely in the framework now:

- **Provider adapters handle token exchange.** Phase 4 now explicitly calls out OAuth 2.0 Token Exchange support (e.g., Keycloak fetching Google tokens) and caches downstream tokens per session. Tools just call a helper such as `auth_context.get_token("google")`; no custom security code needed.  
```240:258:docs/contributors/auth-redesign-plan.md
5. Expose SDK helper…
8. Add provider-specific token exchange helpers (e.g., Keycloak → Google)…
   - Cache downstream tokens per session…
   - Expose via helper so tools can request tokens by alias…
```

- **Scope requirements drive the automation.** Phase 5 introduces `scope_requirements`, a config map from MXCP scopes to the provider token (and exchange parameters) that scope implies. When an endpoint declares `scopes: [calendar.read]`, the framework knows it must obtain the Google token via Keycloak before execution.  
```269:288:docs/contributors/auth-redesign-plan.md
7. Add `scope_requirements` config mapping MXCP scopes → downstream token requirements…
```

- **Endpoint definitions stay declarative.** Endpoints now put `scopes` directly on the tool/prompt/resource definition. The execution wrapper reads those scopes, enforces them, and—thanks to the new scope requirements—fetches/exchanges the right provider tokens and injects them into the execution context before running the tool.  
```300:309:docs/contributors/auth-redesign-plan.md
1. Extend endpoint YAML schema… `tool.scopes`, `prompt.scopes`, `resource.scopes`
…
3. Update execution wrapper to… ensure necessary provider tokens are fetched/exchanged before execution; inject resolved tokens into the execution context…
```

So tool authors stay in YAML for the entitlement definition, and the framework handles the Keycloak→Google token exchange behind the scenes. The tool code simply consumes the injected token (via the helper) without implementing its own security flow.

```plaintext
5. Expose SDK helper…
8. Add provider-specific token exchange helpers (e.g., Keycloak → Google)…
   - Cache downstream tokens per session…
   - Expose via helper so tools can request tokens by alias…
```

```plaintext
7. Add `scope_requirements` config mapping MXCP scopes → downstream token requirements…
```

```plaintext
1. Extend endpoint YAML schema… `tool.scopes`, `prompt.scopes`, `resource.scopes`
…
3. Update execution wrapper to… ensure necessary provider tokens are fetched/exchanged before execution; inject resolved tokens into the execution context…
```

---

**User**

so, to understand, you are proposing in the centralized configuration, to have a 'mini-spec' that maps a scope to how to fetch it up from a provider? that's an optional special case to support this use case?

---

**Cursor**

Exactly. Think of `scope_requirements` as an optional mini-spec that tells the framework “when a tool needs MXCP scope X, here’s how to obtain the underlying provider token if extra work is required.” Most scopes just map to IdP scopes/claims via `claim_mappings`—no extra config needed.

But for special cases (Keycloak brokering Google tokens, Azure issuing downstream Microsoft Graph tokens, etc.) we add an entry:

```yaml
auth:
  scope_requirements:
    calendar.read:
      provider: keycloak
      audience: google
      resource: "https://www.googleapis.com/auth/calendar.readonly"
```

Now when an endpoint declares `scopes: [calendar.read]`, the runtime knows it must ask the Keycloak adapter to perform token exchange for Google before invoking the tool. If you don’t have such chained providers, you skip this block entirely.

```yaml
auth:
  scope_requirements:
    calendar.read:
      provider: keycloak
      audience: google
      resource: "https://www.googleapis.com/auth/calendar.readonly"
```

---

**User**

Another scenario. Suppose they use keycloak. They register an MXCP app in keycloak. Then they define mxcp-specific scopes in keycloak, and they map them to several users. My understanding - most likely wrong? - is that in our design, this requires us to configure keycloak as a provider, but because we distinguish idp scopes from mxcp tool scopes/permissions/entitlements, then those "mxcp-specific scopes added to keycloak" have to be remapped here again in our config? Seems redundant? Is that because we prioritized external scopes we cannot control vs enforcing our own?

Also, what about 'roles' in keycloak? what are those, and how are those mapped in keycloak, and how could they be mapped in our system?

---

**Cursor**

Keycloak’s custom scopes/roles fit cleanly into the mapping layer we already designed. You still configure Keycloak as the provider; whatever scopes or roles you mint there show up in the IdP claims. The `claim_mappings` block in MXCP config simply tells the ScopeMapper how to translate each string (scope, group, role) into the MXCP scope names your tools reference.

So yes, it’s “redundant” in the sense that you mention them twice—once in Keycloak, once in MXCP—but that’s what gives us portability: tools only know about MXCP scopes, while the mapping layer handles each IdP’s naming. Same mechanism works for Keycloak roles: Keycloak emits them in the `realm_access` or `resource_access` claim, we map those strings to MXCP scopes just like provider scopes. This is exactly what the plan’s mapping section calls out (`claim_mappings` turning provider scopes/groups/claims into MXCP scopes), so nothing extra is needed beyond defining those mappings.

---

**User**

in the claims mapping session I only see:

@auth-redesign-plan.md (58-63) 

so where are roles? you said they appear as claims? But which type/field in there? i see only scopes and groups.

---

**Cursor**

```markdown
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
8. Add comprehensive tests for service instantiation and route registration

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
   - Example: `calendar.read` → `{provider: keycloak, audience: google}`
   - AuthService uses this to know which provider tokens/token exchanges to perform automatically
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


```

```markdown
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
8. Add comprehensive tests for service instantiation and route registration

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
   - Example: `calendar.read` → `{provider: keycloak, audience: google}`
   - AuthService uses this to know which provider tokens/token exchanges to perform automatically
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


```

Updated the plan to show where roles fit:

- The config example now includes a `roles` mapping alongside `scopes` and `groups`, demonstrating how Keycloak realm/client roles map to MXCP scopes.  
```58:67:docs/contributors/auth-redesign-plan.md
    claim_mappings:
      scopes:
        "calendar.readonly": [calendar.read]
        ...
      groups:
        "admins@company.com": [admin]
      roles:
        "keycloak_realm:billing-manager": [billing.manage]
        ...
```

- Added a note right after the example explaining that Keycloak roles appear in claims like `realm_access.roles` and `resource_access.<client>.roles`, and the mapper can reference them via the `roles` section to translate into MXCP scopes.

```plaintext
    claim_mappings:
      scopes:
        "calendar.readonly": [calendar.read]
        ...
      groups:
        "admins@company.com": [admin]
      roles:
        "keycloak_realm:billing-manager": [billing.manage]
        ...
```

---

**User**

can we fix this poor example:

@auth-redesign-plan.md (299-300) 

perhaps with e.g. 

auth:



  scope_requirements:

    calendar.read:

      provider: keycloak

      audience: google

      resource: "https://www.googleapis.com/auth/calendar.readonly"

since it seems more correct? is that the correct syntax?

---

**Cursor**

```markdown
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
8. Add comprehensive tests for service instantiation and route registration

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
   - AuthService uses this to know which provider tokens/token exchanges to perform automatically
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


```

Updated the `scope_requirements` example in the plan to show the exact YAML structure:

```yaml
auth:
  scope_requirements:
    calendar.read:
      provider: keycloak
      audience: google
      resource: "https://www.googleapis.com/auth/calendar.readonly"
```

This lives in Phase 5 so it’s clear how MXCP scopes map to downstream token-exchange requirements.

```yaml
auth:
  scope_requirements:
    calendar.read:
      provider: keycloak
      audience: google
      resource: "https://www.googleapis.com/auth/calendar.readonly"
```

---

**User**

Is it possible to have another scenario where mxcp is registered as a keycloak app. But in this case, keycloak can generate tokens for us. Our clients can go to Keycloak and ask for an mxcp token; then our system just has to go back and validate it against keycloak. In FastMCP, there is a token verifier function we could implement for this. Does this fit the design, and if so, how? Is it covered by existing cases, or is it a new case? I thought we were generating own tokens - should we?

---

**Cursor**

That scenario (Keycloak issues the tokens, MXCP just validates them) isn’t part of the current plan, which keeps MXCP acting as its own authorization server issuing opaque tokens. But the architecture makes it easy to add:

- We’d run `AuthService` in a “resource-server mode” where it doesn’t mint MXCP tokens at all. Instead it registers a `token_verifier` with FastMCP that validates incoming Keycloak JWTs (via JWKS or token introspection) and then runs the same `ScopeMapper` + middleware pipeline.
- The Keycloak provider adapter already knows how to fetch user info and scopes; in this mode it would just skip issuing tokens and reuse the JWT claims straight from the request.
- No change to endpoint YAML or scope logic; we still map Keycloak scopes/roles into MXCP scopes and enforce them server-side.

So it’s a new mode (verification-only) but fits neatly: same `AuthService`, different configuration branch where we skip `SessionManager` issuance and wire FastMCP’s token verifier to Keycloak instead.

---

**User**

And in this mode, is still possible that the user would request an mxcp token that itself allows mxcp to access, say, a google service? (asusming their keycloak and google also support that?) Does it fit somehow to the sort of 'scope_requirements' case we also tried to support?

---

**Cursor**

Yes, it still fits. In verification-only mode we aren’t issuing MXCP tokens, but the rest of the pipeline—`ScopeMapper`, `scope_requirements`, downstream token exchange—stays exactly the same.

For example, suppose Keycloak issues JWTs with a custom scope `calendar.read`. You still map that to MXCP scope `calendar.read` via `claim_mappings`. When a tool requires `calendar.read`, the execution wrapper looks at `scope_requirements` and sees it needs a Google token. Even though the incoming token came from Keycloak, the Keycloak adapter can call its token-exchange endpoint to get a Google token (assuming Keycloak is configured as a broker). So the same `scope_requirements` mechanism kicks in: MXCP sees that this scope implies a downstream audience, asks Keycloak to exchange the user’s JWT for a Google token, and injects that token into the execution context before running the tool.

So both modes—MXCP-issued tokens and Keycloak-issued tokens—share the same higher-level logic. The only difference is who generates the primary session token; the downstream Google access still flows through the `scope_requirements` mapping.

---

**User**

Can we change the spec then to support this?  it's an important case to support.

---

**Cursor**

```markdown
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
8. Add comprehensive tests for service instantiation and route registration

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
   - AuthService uses this to know which provider tokens/token exchanges to perform automatically
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


```

```markdown
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
   - AuthService uses this to know which provider tokens/token exchanges to perform automatically
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


```

```markdown
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
   - AuthService uses this to know which provider tokens/token exchanges to perform automatically
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


```

```markdown
*** Begin Patch
*** Update File: docs/contributors/auth-redesign-plan.md
@@
    auth:
      scope_requirements:
        calendar.read:
          provider: keycloak
          audience: google
          resource: "https://www.googleapis.com/auth/calendar.readonly"
-   - AuthService uses this to know which provider tokens/token exchanges to perform automatically
+   - AuthService uses this to know which provider tokens/token exchanges to perform automatically (applies to both MXCP-issued tokens and externally issued tokens validated via verifier mode)
*** End Patch
```

```markdown
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
   - AuthService uses this to know which provider tokens/token exchanges to perform automatically
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


```

```markdown
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


```

The plan now covers the “Keycloak issues MXCP tokens” scenario explicitly:

- Added a **Token Issuance vs. Verification Modes** section describing both modes. In verifier mode we register a FastMCP `token_verifier` that validates external tokens (e.g., Keycloak JWTs) and still runs the same `ScopeMapper`, middleware, and `scope_requirements` pipeline.
- Phase 1 now includes tasks to support both modes and to wire the verifier into FastMCP.
- Phase 4’s token-exchange helpers explicitly run in both modes.
- `scope_requirements` docs now show the YAML structure and note it applies whether MXCP issues the token or just validates a Keycloak-issued one. When a tool declares `scopes: [calendar.read]`, the framework will still consult `scope_requirements`, perform the Keycloak→Google token exchange if needed, and inject the Google token into the tool’s execution context—even in verifier mode.

So yes: clients can mint MXCP tokens directly from Keycloak, MXCP will verify them, map their scopes/roles, and still fetch downstream Google tokens automatically when an endpoint’s scope requires it.

---

**User**

Can you add a final table, schema, diagram, buleet points or some high-level representation of ALL MODES we support? ALL. Just append new section at the end. (include also tools doing totally custom code with e.g. custom headers, since we happen to support that as well, even with auth off)

---

**Cursor**

```markdown
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


```

Added a final “Supported Authentication Modes” section summarizing every path:

- Issuer mode (MXCP tokens)
- Verifier mode (external IdP issues tokens)
- Proxy/header mode
- Scope requirements / downstream token exchange (works with all modes)
- Auth disabled / custom tool logic

Each entry explains how it works and common use cases, and reiterates that ScopeMapper, endpoint scopes, and optional scope requirements sit on top of every mode.

