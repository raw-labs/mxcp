# CapabilityMapper Design

## Overview

Implement a `CapabilityMapper` that translates IdP claims (scopes, roles, groups, custom claims) into MXCP **capabilities** — the internal authorization vocabulary used by tools and policies.

This corresponds to Phase 5 of the auth redesign plan. Tool-level enforcement (Phase 6) is out of scope.

## Terminology

- **Provider scopes**: What we request from the IdP (`scope: "openid profile email"`)
- **Capabilities**: Internal MXCP authorization vocabulary (`capabilities: [billing.manage]`)

"Capabilities" replaces the overloaded term "MXCP scopes" to avoid confusion with OAuth scopes.

## Config Model

`claim_mappings` lives under the provider config in `config.yml` (deployer-level). Each key is a **claim path** into the raw token/userinfo JSON. Each value maps claim values to lists of capabilities.

```yaml
auth:
  provider: oidc
  oidc:
    config_url: "https://mycompany.auth0.com/.well-known/openid-configuration"
    client_id: "${AUTH0_CLIENT_ID}"
    client_secret: "${AUTH0_CLIENT_SECRET}"
    scope: "openid profile email"
    callback_path: "/oidc/callback"
    claim_mappings:
      "https://mycompany.com/roles":
        "admin": [admin, billing.manage, reports.view]
        "billing-manager": [billing.manage]
      "https://mycompany.com/groups":
        "finance-team": [billing.manage]
      "scope":
        "https://www.googleapis.com/auth/calendar.readonly": [calendar.read]
```

### Claim path resolution

- **Top-level keys**: `"scope"` → `raw_profile["scope"]`
- **Dot-separated nested paths**: `"realm_access.roles"` → `raw_profile["realm_access"]["roles"]`
- **URI-namespaced keys**: `"https://mycompany.com/roles"` → `raw_profile["https://mycompany.com/roles"]`

URI keys are tried first (exact match), then dot traversal. This avoids ambiguity with URIs containing dots.

### Value types at the resolved path

- **List of strings** (e.g., `["admin", "viewer"]`): each element matched against the mapping
- **Space-separated string** (e.g., `"openid email calendar.readonly"`): split, then each part matched
- **Single string**: matched directly

### Behaviors

- Unmapped claim values are silently ignored
- Missing claim paths produce a warning log but do not fail auth
- Empty `claim_mappings` produces an empty capability set

## CapabilityMapper Class

Located at `mxcp/sdk/auth/capabilities.py`.

```python
class CapabilityMapper:
    def __init__(self, claim_mappings: dict[str, dict[str, list[str]]]):
        self._mappings = claim_mappings

    def derive(self, raw_profile: dict[str, Any]) -> set[str]:
        """Derive capabilities from a raw claims profile."""
        capabilities: set[str] = set()
        for claim_path, value_map in self._mappings.items():
            claim_value = self._resolve_path(raw_profile, claim_path)
            if claim_value is None:
                logger.warning("Claim path '%s' not found in profile", claim_path)
                continue
            matched_values = self._normalize_claim_value(claim_value)
            for value in matched_values:
                if value in value_map:
                    capabilities.update(value_map[value])
        return capabilities

    def _resolve_path(self, profile: dict, path: str) -> Any:
        """Traverse dotted path, handling URI keys that contain dots."""
        if path in profile:
            return profile[path]
        parts = path.split(".")
        current = profile
        for part in parts:
            if not isinstance(current, dict) or part not in current:
                return None
            current = current[part]
        return current

    def _normalize_claim_value(self, value: Any) -> list[str]:
        """Normalize claim value to a list of strings for matching."""
        if isinstance(value, list):
            return [str(v) for v in value]
        if isinstance(value, str) and " " in value:
            return value.split()
        return [str(value)]
```

- Stateless after construction
- Recreated on config reload (new mappings take effect immediately)
- No async needed — pure dict traversal

## Integration Points

### Per-request capability derivation

Capabilities are derived on every request (not cached in sessions). This ensures config changes (via live reload) take effect immediately without session invalidation.

### Both auth modes — single integration point

`RAWMCP.require_user_info` (the decorator wrapping every tool/resource/prompt handler) is the integration point for both issuer and verifier modes:

1. Retrieve `UserInfo` (already contains `raw_profile`)
2. Call `mapper.derive(user_info.raw_profile)`
3. Attach result as `capabilities` on the `UserContextModel`

### Mapper lifecycle

The `CapabilityMapper` instance is held by `RAWMCP`. Created from the active provider's `claim_mappings` during initialization. On config reload, a new mapper is constructed with updated mappings.

## Pydantic Model Changes

### SDK provider configs (`mxcp/sdk/auth/models.py`)

Add `claim_mappings` field to all provider config models:

```python
claim_mappings: dict[str, dict[str, list[str]]] = Field(default_factory=dict)
```

Applied to: `OIDCAuthConfigModel`, `OIDCVerifierAuthConfigModel`, `GitHubAuthConfigModel`, `KeycloakAuthConfigModel`, `GoogleAuthConfigModel`, `SalesforceAuthConfigModel`, `AtlassianAuthConfigModel`.

### Server provider configs (`mxcp/server/core/config/models.py`)

Mirror the field on all User provider config models:

```python
claim_mappings: dict[str, dict[str, list[str]]] = Field(default_factory=dict)
```

Applied to: `UserOIDCAuthConfigModel`, `UserOIDCVerifierAuthConfigModel`, `UserGitHubAuthConfigModel`, `UserKeycloakAuthConfigModel`, `UserGoogleAuthConfigModel`, `UserSalesforceAuthConfigModel`, `UserAtlassianAuthConfigModel`.

### Runtime models

**`UserInfo`** (`contracts.py`): rename `mxcp_scopes` → `capabilities` (type: `set[str]`)

**`UserContextModel`** (`models.py`): add `capabilities: set[str] = Field(default_factory=set)`

### CEL policy context

In `PolicyEnforcer._user_context_to_dict`, add:

```python
"capabilities": list(user_context.capabilities),
```

This allows CEL expressions like:

```yaml
condition: 'user.capabilities.exists(c, c == "billing.manage")'
```

## Example Configs

### Auth0 deployer

```yaml
auth:
  provider: oidc
  oidc:
    config_url: "https://mycompany.auth0.com/.well-known/openid-configuration"
    client_id: "${AUTH0_CLIENT_ID}"
    client_secret: "${AUTH0_CLIENT_SECRET}"
    scope: "openid profile email"
    callback_path: "/oidc/callback"
    claim_mappings:
      "https://mycompany.com/roles":
        "admin": [admin]
        "billing-manager": [billing.manage]
        "report-viewer": [reports.view]
      "https://mycompany.com/groups":
        "finance-team": [billing.manage]
```

### Keycloak deployer (same project)

```yaml
auth:
  provider: keycloak
  keycloak:
    client_id: "${KC_CLIENT_ID}"
    client_secret: "${KC_CLIENT_SECRET}"
    realm: "mxcp"
    server_url: "https://keycloak.internal"
    scope: "openid profile email"
    callback_path: "/keycloak/callback"
    claim_mappings:
      "realm_access.roles":
        "admin": [admin]
        "billing-manager": [billing.manage]
      "resource_access.mxcp-client.roles":
        "report-viewer": [reports.view]
```

### Google deployer with scope mapping

```yaml
auth:
  provider: google
  google:
    client_id: "${GOOGLE_CLIENT_ID}"
    client_secret: "${GOOGLE_CLIENT_SECRET}"
    scope: "openid email https://www.googleapis.com/auth/calendar.readonly"
    callback_path: "/google/callback"
    auth_url: "https://accounts.google.com/o/oauth2/v2/auth"
    token_url: "https://oauth2.googleapis.com/token"
    claim_mappings:
      "scope":
        "https://www.googleapis.com/auth/calendar.readonly": [calendar.read]
```

## Testing

Tests in `tests/sdk/auth/test_capability_mapper.py`.

### Unit tests

1. Basic mapping — single claim path, single value, produces expected capabilities
2. Multiple claim paths — capabilities aggregated from multiple paths
3. One value to multiple capabilities — `"admin": [admin, billing.manage]`
4. List claim values — `["admin", "viewer"]` each matched independently
5. Space-separated string — split and matched (scope claim)
6. Single string value — matched directly
7. Dot-path resolution — `"realm_access.roles"` traverses nested dicts
8. URI key resolution — `"https://mycompany.com/roles"` as exact top-level key
9. URI key precedence — exact key match tried before dot traversal
10. Missing claim path — logs warning, returns no capabilities from that path
11. Unmapped claim value — silently ignored
12. Empty claim_mappings — returns empty set
13. Empty raw_profile — logs warnings, returns empty set

### Integration tests

14. Issuer mode — after callback, user context contains derived capabilities
15. Verifier mode — after token verification, user context contains derived capabilities
16. Config reload — new mapper instance reflects updated claim_mappings

## Out of Scope (Phase 6)

- Declarative `capabilities:` field on tool YAML definitions
- Per-tool capability enforcement in the execution pipeline
- Validation warnings for capabilities referenced in tools but not in any mapping
