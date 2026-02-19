# Add Verifier Mode for OAuth/OIDC Tokens

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work proceeds.

This plan must be maintained in accordance with `.agent/PLANS.md` from the repository root.

## Purpose / Big Picture

MXCP currently runs OAuth in issuer mode, where MXCP acts as the IdP for MCP clients and forwards to an upstream IdP. This plan adds a new verifier mode so MXCP can accept access tokens obtained outside MXCP, validate them, and populate the same `UserInfo` context that tools already consume. After implementation, a user can configure `auth.mode: verifier`, send `Authorization: Bearer <token>` requests, and see `get_user_*` functions resolve identity without MXCP initiating OAuth redirects.

## Progress

- [x] (2026-02-19 00:00Z) Make config parsing accept `auth.mode: verifier` for OIDC via mode-specific OIDC models (Option C).
- [ ] (2026-02-18 00:00Z) Implement token validation pipeline (JWT via JWKS, optional introspection, optional userinfo enrichment).
- [ ] (2026-02-18 00:00Z) Integrate verifier mode into request auth flow and add tests.
- [x] (2026-02-18 00:00Z) Add end-to-end integration test script that uses a real Keycloak server via environment variables (implemented at `scripts/test_oidc_verifier_e2e.py`, uses MCP streamable-http client, boots `mxcp serve`, and supports `EXPECTED_MODE=none` for no-auth validation).

## Surprises & Discoveries

- Observation: MXCP streamable-http does not expose `/tools` as a simple REST endpoint; tool calls must use MCP JSON-RPC over the `/mcp/` streamable-http transport.
  Evidence: Repeated `GET /tools` returned 404 while the MCP client library (`streamablehttp_client` + `ClientSession`) successfully connected and called tools.
- Observation: Mode-based OIDC re-validation on frozen config models must use `object.__setattr__` to avoid `frozen_instance` errors.
  Evidence: `mxcp validate` failed with `Instance is frozen` until the validator used `object.__setattr__`.
- Observation: FastMCP can validate tokens using the `token_verifier` hook, but it only returns `AccessToken` (scopes/expires/client_id), not user profile data.
  Evidence: `mcp.server.auth.provider.AccessToken` lacks user fields; user context must be computed by MXCP separately.

## Decision Log

- Decision: Prefer OIDC discovery as the default source of validation endpoints, with optional overrides for userinfo and introspection.
  Rationale: Discovery is standard for OIDC but incomplete for some IdPs; overrides allow practical integration without hardcoding.
  Date/Author: 2026-02-18 / Codex
- Decision: Add an end-to-end verifier-mode test that fetches a Keycloak token via password grant and then calls an MXCP tool endpoint.
  Rationale: Verifier mode should be validated against a real OIDC server; a live Keycloak flow reduces risk of integration regressions.
  Date/Author: 2026-02-18 / Codex
- Decision: Use the MCP streamable-http client library for the e2e tool call and readiness instead of REST calls to `/tools`.
  Rationale: Streamable-http uses JSON-RPC and does not expose `/tools` as a REST endpoint; using the MCP client avoids false negatives.
  Date/Author: 2026-02-18 / Codex
- Decision: Order of work is config-first, then implementation, then e2e test run.
  Rationale: `mxcp validate` should accept verifier configs before runtime behavior lands, and the e2e test is only meaningful after implementation.
  Date/Author: 2026-02-18 / Codex
- Decision: Implement OIDC verifier config parsing via Option C (mode-specific OIDC models with re-validation).
  Rationale: Keeps existing auth shape while allowing `callback_path` to be omitted in verifier mode.
  Date/Author: 2026-02-19 / Codex
- Decision: Use `object.__setattr__` when coercing `oidc` inside `UserAuthConfigModel` validators.
  Rationale: The model is frozen; direct assignment raises `frozen_instance` errors during config validation.
  Date/Author: 2026-02-19 / Codex
- Decision: Use FastMCP's `token_verifier` for verification, and cache MXCP `UserInfo` in a request-scoped context variable for user-context construction.
  Rationale: Ensures IdP validation happens once per request while still populating tool user context.
  Date/Author: 2026-02-19 / Codex
- Decision: In issuer mode, store `UserInfo` in a request-scoped context variable during `load_access_token` and reuse it when building user context to avoid duplicate store lookups.
  Rationale: Keeps persistence via token store while avoiding redundant `SessionManager.get_session` calls in the same request.
  Date/Author: 2026-02-19 / Codex
- Decision: Use small, focused commits with one-line commit messages throughout implementation.
  Rationale: This keeps the verifier work easy to review and bisect.
  Date/Author: 2026-02-18 / Codex

## Outcomes & Retrospective

- Not started. This section will capture outcomes at milestone completion.

## Context and Orientation

MXCP authentication models live under `src/mxcp/sdk/auth/` and server config models under `src/mxcp/server/core/config/`. Provider adapters in `src/mxcp/sdk/auth/providers/` handle issuer-mode OAuth exchanges and userinfo retrieval. The normalized user context is defined in `src/mxcp/sdk/auth/contracts.py` as `UserInfo` with required fields `provider`, `user_id`, and `username`. The new generic OIDC adapter (`src/mxcp/sdk/auth/providers/oidc.py`) already performs discovery, uses `jwks_uri` for keys (in discovery payload), and uses `userinfo_endpoint` for profile data.

Verifier mode will live alongside issuer mode. It should not run the OAuth authorization code flow; instead it should validate inbound access tokens and build `UserInfo` for tool execution. Validation should support JWT (signature + standard claims) and optionally OAuth introspection for opaque tokens.

## Plan of Work

First, extend configuration to accept `auth.mode: issuer|verifier` with a default of `issuer` to preserve behavior. Add a `verifier` sub-config block that controls validation strategy, including token hint (`auto|jwt|opaque`), whether to use introspection when available, and whether to call `userinfo` to enrich identity. These new config fields must be documented in `docs/security/authentication.md` and, if needed, in an example config under `examples/`.

Second, implement verifier mode using FastMCP’s `token_verifier` hook. FastMCP will call our verifier on each request; this is the *only* place where IdP validation should occur. The verifier should return MCP’s `AccessToken` (scopes/expires/client_id) to satisfy FastMCP, and also compute MXCP `UserInfo` for tool context. Store the computed `UserInfo` in a single request-scoped context variable (`verified_user_info`); the tool wrapper will read it, set `UserContextModel`, and then clear it (no reset tokens, just set to `None`).

Third, in issuer mode, store `UserInfo` in `verified_user_info` during `IssuerOAuthAuthorizationServer.load_access_token(...)` (which already reads from the token store). The tool wrapper will set `user_context` from `verified_user_info` and then clear both `user_context` and `verified_user_info` after execution. No SessionManager lookup is needed for the same request (we keep the store for persistence across requests).

Second, implement a verifier pipeline that is provider-aware but OIDC-first. For `provider: oidc`, use discovery to fetch `jwks_uri`, `userinfo_endpoint`, and `introspection_endpoint` (if present). In verifier mode, obtain the bearer token from incoming requests, then:

- If token looks like JWT (three dot-separated segments) or the hint is `jwt`, validate signature using JWKS, and validate `iss` and `exp`. Validate `aud` only when configured in `auth.oidc.audience`.
- If token is opaque (hint `opaque`) or JWT verification is unavailable, and an introspection endpoint exists, call it with client credentials to ensure `active == true` and extract claims.
- If neither JWT validation nor introspection is available, optionally call `userinfo` if configured to do so, but treat this as a weaker verification and emit a warning log.

Third, build `UserInfo` consistently from claims and/or userinfo response. Required mapping should be: `user_id` from `sub`, `username` from `preferred_username` or `username` or `email` or fallback to `sub`. Optional mapping: `email`, `name`, `avatar_url`, and `provider_scopes_granted` from `scope` when present. Preserve raw claims in `raw_profile` for debugging.

Fourth, integrate verifier mode into the server request auth flow so that authenticated requests populate `user_info` in the context without invoking issuer-mode OAuth server code. Add unit tests for JWT validation, introspection, and userinfo enrichment, plus a minimal integration test that demonstrates `get_user_*` data is populated from an inbound token.

Fifth, add an end-to-end integration test script that uses a live Keycloak server. The script should read `KEYCLOAK_SERVER_URL`, `KEYCLOAK_REALM`, `KEYCLOAK_CLIENT_ID`, `KEYCLOAK_CLIENT_SECRET`, and test credentials supplied via `KEYCLOAK_USERNAME` and `KEYCLOAK_PASSWORD` to obtain an access token via the password grant. It should then start `mxcp serve --transport streamable-http` in a configurable project directory and call a tool via the MCP streamable-http client, including the bearer token on the MCP requests. The script should assert that the response contains the expected username/email fields (or nulls when `EXPECTED_MODE=none`). The script must shut down the spawned MXCP process on exit.

## Concrete Steps

1. Update configuration models.

   - In `src/mxcp/sdk/auth/models.py`, add `mode: Literal["issuer", "verifier"]` to `AuthConfigModel` with default `issuer`.
   - Add a `VerifierConfigModel` with fields `token_hint`, `validation`, `userinfo`, and optional endpoint overrides. Add it to `AuthConfigModel`.
   - Mirror these changes in `src/mxcp/server/core/config/models.py` under `UserAuthConfigModel`.

2. Implement token validation utilities.

   - Create a module `src/mxcp/sdk/auth/verifier.py` with helper functions to detect JWTs, fetch JWKS, validate JWTs, and call introspection.
   - Use `httpx` and `create_mcp_http_client` for HTTP calls.
   - Define a small internal model for introspection response with fields like `active`, `sub`, `scope`, `exp`, `iss`, `aud`.

3. Implement OIDC verifier adapter.

   - Create `OIDCVerifierAdapter` or extend `OIDCProviderAdapter` with verifier methods such as `verify_access_token(...) -> UserInfo`.
   - Ensure discovery happens once via `ensure_ready()`.
   - Implement mapping from claims/userinfo to `UserInfo`.

4. Integrate verifier mode into server auth flow.

   - Identify where request authentication is performed (likely in `src/mxcp/server/core/auth/` or request middleware in `src/mxcp/server/interfaces/`).
   - If `auth.mode == verifier`, bypass issuer-mode OAuth server and call the verifier adapter with the inbound token.
   - Populate request context with the returned `UserInfo`.

5. Tests and docs.

   - Add unit tests in `tests/sdk/auth/` for JWT validation, introspection, and claim mapping.
   - Add a server-side test to ensure `get_user_email` and `get_username` resolve with verifier mode.
   - Update `docs/security/authentication.md` with a “Verifier Mode” section and sample config.
   - Add an end-to-end script under `scripts/` (for example `scripts/test_oidc_verifier_e2e.py`) that performs the Keycloak token fetch + MXCP tool call described above.

## Validation and Acceptance

Run the following from the repo root:

    uv run pytest tests/sdk/auth/test_verifier_jwt.py
    uv run pytest tests/sdk/auth/test_verifier_introspection.py

If integration tests are added:

    uv run pytest tests/server/test_auth_verifier.py

For the end-to-end Keycloak verifier test:

    export KEYCLOAK_SERVER_URL="http://localhost:8080"
    export KEYCLOAK_REALM="demo"
    export KEYCLOAK_CLIENT_ID="mxcp"
    export KEYCLOAK_CLIENT_SECRET="..."
    export MXCP_URL="http://localhost:8000"
    uv run python scripts/test_oidc_verifier_e2e.py

Acceptance is demonstrated when:

- A JWT signed by a known JWKS validates and produces `UserInfo` with `user_id` and `username`.
- An opaque token verified via introspection produces the same `UserInfo`.
- When verifier mode is enabled in config, tools see user context values via `get_user_*` functions without any OAuth redirect flow.
- The end-to-end script obtains a Keycloak access token and receives the expected user info from an MXCP tool call.

## Idempotence and Recovery

The steps are additive and can be re-run safely. If tests fail during verifier integration, revert only the verifier-specific changes and re-run the test suite. No migrations or destructive operations are required.

## Artifacts and Notes

Example expected JWT validation output for a happy-path test:

    VALID
    {
      "sub": "user-123",
      "preferred_username": "alice",
      "email": "alice@example.com"
    }

## Interfaces and Dependencies

Use existing `httpx` and `create_mcp_http_client` for network calls. Define the verifier interface to return `mxcp.sdk.auth.contracts.UserInfo`. If extending the OIDC adapter, add a method with a stable signature such as:

    async def verify_access_token(self, *, access_token: str) -> UserInfo:
        ...

Ensure any new models use `pydantic` and follow the existing error handling pattern with `ProviderError`.

Revision Notes: Initial version created on 2026-02-18.
Revision Notes: Added commit-style preference (single-line commits) on 2026-02-18 to reflect user preference.
