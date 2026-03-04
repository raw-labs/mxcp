# CapabilityMapper Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement a `CapabilityMapper` that translates IdP claims into MXCP capabilities via claim-path-based config, and surface capabilities in the user context and CEL policies.

**Architecture:** A standalone `CapabilityMapper` class in the SDK takes `claim_mappings` config at construction and derives capabilities from `raw_profile` dicts per-request. The mapper is wired into `require_user_info` in the server layer so both issuer and verifier modes produce capabilities. Config changes via live reload recreate the mapper.

**Tech Stack:** Python 3.10+, Pydantic v2 (SDK models), pytest

---

### Task 1: CapabilityMapper — Core class with basic claim path resolution

**Files:**
- Create: `src/mxcp/sdk/auth/capabilities.py`
- Test: `tests/sdk/auth/test_capability_mapper.py`

**Step 1: Write the failing tests**

Create `tests/sdk/auth/test_capability_mapper.py`:

```python
"""Tests for CapabilityMapper."""

from __future__ import annotations

import logging
from typing import Any

import pytest

from mxcp.sdk.auth.capabilities import CapabilityMapper


class TestCapabilityMapperBasic:
    """Basic mapping behavior."""

    def test_single_claim_path_single_value(self) -> None:
        mapper = CapabilityMapper(
            claim_mappings={
                "https://mycompany.com/roles": {
                    "admin": ["admin"],
                },
            }
        )
        result = mapper.derive({"https://mycompany.com/roles": ["admin"]})
        assert result == {"admin"}

    def test_multiple_claim_paths_aggregate(self) -> None:
        mapper = CapabilityMapper(
            claim_mappings={
                "https://mycompany.com/roles": {
                    "admin": ["admin"],
                },
                "https://mycompany.com/groups": {
                    "finance-team": ["billing.manage"],
                },
            }
        )
        result = mapper.derive(
            {
                "https://mycompany.com/roles": ["admin"],
                "https://mycompany.com/groups": ["finance-team"],
            }
        )
        assert result == {"admin", "billing.manage"}

    def test_one_value_maps_to_multiple_capabilities(self) -> None:
        mapper = CapabilityMapper(
            claim_mappings={
                "https://mycompany.com/roles": {
                    "admin": ["admin", "billing.manage", "reports.view"],
                },
            }
        )
        result = mapper.derive({"https://mycompany.com/roles": ["admin"]})
        assert result == {"admin", "billing.manage", "reports.view"}

    def test_list_claim_values_matched_independently(self) -> None:
        mapper = CapabilityMapper(
            claim_mappings={
                "https://mycompany.com/roles": {
                    "admin": ["admin"],
                    "viewer": ["reports.view"],
                },
            }
        )
        result = mapper.derive({"https://mycompany.com/roles": ["admin", "viewer"]})
        assert result == {"admin", "reports.view"}

    def test_space_separated_string_split_and_matched(self) -> None:
        mapper = CapabilityMapper(
            claim_mappings={
                "scope": {
                    "calendar.readonly": ["calendar.read"],
                    "drive.readonly": ["files.read"],
                },
            }
        )
        result = mapper.derive({"scope": "openid calendar.readonly drive.readonly"})
        assert result == {"calendar.read", "files.read"}

    def test_single_string_value_matched_directly(self) -> None:
        mapper = CapabilityMapper(
            claim_mappings={
                "department": {
                    "engineering": ["code.deploy"],
                },
            }
        )
        result = mapper.derive({"department": "engineering"})
        assert result == {"code.deploy"}

    def test_unmapped_claim_value_ignored(self) -> None:
        mapper = CapabilityMapper(
            claim_mappings={
                "https://mycompany.com/roles": {
                    "admin": ["admin"],
                },
            }
        )
        result = mapper.derive({"https://mycompany.com/roles": ["viewer"]})
        assert result == set()

    def test_empty_claim_mappings_returns_empty_set(self) -> None:
        mapper = CapabilityMapper(claim_mappings={})
        result = mapper.derive({"scope": "openid", "roles": ["admin"]})
        assert result == set()


class TestCapabilityMapperPathResolution:
    """Claim path resolution: dot paths, URI keys, precedence."""

    def test_dot_path_resolves_nested_dict(self) -> None:
        mapper = CapabilityMapper(
            claim_mappings={
                "realm_access.roles": {
                    "billing-manager": ["billing.manage"],
                },
            }
        )
        result = mapper.derive({"realm_access": {"roles": ["billing-manager"]}})
        assert result == {"billing.manage"}

    def test_deep_dot_path(self) -> None:
        mapper = CapabilityMapper(
            claim_mappings={
                "resource_access.mxcp-client.roles": {
                    "report-viewer": ["reports.view"],
                },
            }
        )
        result = mapper.derive(
            {"resource_access": {"mxcp-client": {"roles": ["report-viewer"]}}}
        )
        assert result == {"reports.view"}

    def test_uri_key_exact_match(self) -> None:
        mapper = CapabilityMapper(
            claim_mappings={
                "https://mycompany.com/roles": {
                    "admin": ["admin"],
                },
            }
        )
        result = mapper.derive({"https://mycompany.com/roles": ["admin"]})
        assert result == {"admin"}

    def test_uri_key_takes_precedence_over_dot_traversal(self) -> None:
        """If exact key exists in profile, don't try splitting on dots."""
        mapper = CapabilityMapper(
            claim_mappings={
                "a.b": {
                    "val": ["cap_from_exact"],
                },
            }
        )
        # Profile has both exact key "a.b" and nested {"a": {"b": ...}}
        result = mapper.derive({"a.b": ["val"], "a": {"b": ["other"]}})
        assert result == {"cap_from_exact"}

    def test_missing_claim_path_logs_warning(self, caplog: pytest.LogCaptureFixture) -> None:
        mapper = CapabilityMapper(
            claim_mappings={
                "missing.path": {
                    "val": ["cap"],
                },
            }
        )
        with caplog.at_level(logging.WARNING, logger="mxcp.sdk.auth.capabilities"):
            result = mapper.derive({"other": "data"})
        assert result == set()
        assert "missing.path" in caplog.text

    def test_empty_raw_profile_logs_warnings(self, caplog: pytest.LogCaptureFixture) -> None:
        mapper = CapabilityMapper(
            claim_mappings={
                "roles": {"admin": ["admin"]},
                "groups": {"eng": ["code.deploy"]},
            }
        )
        with caplog.at_level(logging.WARNING, logger="mxcp.sdk.auth.capabilities"):
            result = mapper.derive({})
        assert result == set()
        assert "roles" in caplog.text
        assert "groups" in caplog.text
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/sdk/auth/test_capability_mapper.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'mxcp.sdk.auth.capabilities'`

**Step 3: Write minimal implementation**

Create `src/mxcp/sdk/auth/capabilities.py`:

```python
"""CapabilityMapper translates IdP claims into MXCP capabilities."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class CapabilityMapper:
    """Maps IdP claims to MXCP capabilities using claim-path-based config.

    Claim paths point into the raw token/userinfo JSON:
    - Top-level keys: "scope", "email_verified"
    - Dot-separated nested paths: "realm_access.roles"
    - URI-namespaced keys: "https://mycompany.com/roles"

    URI keys (exact match) take precedence over dot traversal.
    """

    def __init__(self, claim_mappings: dict[str, dict[str, list[str]]]) -> None:
        self._mappings = claim_mappings

    def derive(self, raw_profile: dict[str, Any]) -> set[str]:
        """Derive capabilities from a raw claims profile."""
        capabilities: set[str] = set()
        for claim_path, value_map in self._mappings.items():
            claim_value = self._resolve_path(raw_profile, claim_path)
            if claim_value is None:
                logger.warning("Claim path '%s' not found in profile", claim_path)
                continue
            for value in self._normalize_claim_value(claim_value):
                if value in value_map:
                    capabilities.update(value_map[value])
        return capabilities

    def _resolve_path(self, profile: dict[str, Any], path: str) -> Any:
        """Resolve a claim path in the profile dict.

        Tries exact key match first (handles URI keys like
        "https://mycompany.com/roles"), then dot-separated traversal.
        """
        if path in profile:
            return profile[path]
        parts = path.split(".")
        current: Any = profile
        for part in parts:
            if not isinstance(current, dict) or part not in current:
                return None
            current = current[part]
        return current

    @staticmethod
    def _normalize_claim_value(value: Any) -> list[str]:
        """Normalize a claim value to a list of strings for matching."""
        if isinstance(value, list):
            return [str(v) for v in value]
        if isinstance(value, str) and " " in value:
            return value.split()
        return [str(value)]
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/sdk/auth/test_capability_mapper.py -v`
Expected: All 14 tests PASS

**Step 5: Commit**

```bash
git add src/mxcp/sdk/auth/capabilities.py tests/sdk/auth/test_capability_mapper.py
git commit -m "feat: add CapabilityMapper for claim-to-capability mapping"
```

---

### Task 2: Add `claim_mappings` field to all provider config models

**Files:**
- Modify: `src/mxcp/sdk/auth/models.py` (7 provider config classes)
- Modify: `src/mxcp/server/core/config/models.py` (7 User provider config classes)
- Test: `tests/sdk/auth/test_capability_mapper.py` (add config model tests)

**Step 1: Write the failing tests**

Append to `tests/sdk/auth/test_capability_mapper.py`:

```python
from mxcp.sdk.auth.models import (
    OIDCAuthConfigModel,
    OIDCVerifierAuthConfigModel,
    GitHubAuthConfigModel,
    KeycloakAuthConfigModel,
    GoogleAuthConfigModel,
    SalesforceAuthConfigModel,
    AtlassianAuthConfigModel,
)


class TestClaimMappingsConfigField:
    """claim_mappings field exists and defaults correctly on all provider configs."""

    @pytest.mark.parametrize(
        "model_class",
        [
            OIDCAuthConfigModel,
            OIDCVerifierAuthConfigModel,
            GitHubAuthConfigModel,
            KeycloakAuthConfigModel,
            GoogleAuthConfigModel,
            SalesforceAuthConfigModel,
            AtlassianAuthConfigModel,
        ],
    )
    def test_claim_mappings_defaults_to_empty_dict(self, model_class: type) -> None:
        """All provider config models should have claim_mappings defaulting to {}."""
        # We just check the field exists and has the right default
        field_info = model_class.model_fields.get("claim_mappings")
        assert field_info is not None, f"{model_class.__name__} missing claim_mappings field"
        assert field_info.default_factory is not None or field_info.default == {}

    def test_oidc_config_with_claim_mappings(self) -> None:
        config = OIDCAuthConfigModel(
            config_url="https://example.com/.well-known/openid-configuration",
            client_id="test",
            client_secret="secret",
            scope="openid profile",
            callback_path="/callback",
            claim_mappings={
                "https://example.com/roles": {
                    "admin": ["admin"],
                },
            },
        )
        assert config.claim_mappings == {
            "https://example.com/roles": {"admin": ["admin"]},
        }

    def test_oidc_config_without_claim_mappings(self) -> None:
        config = OIDCAuthConfigModel(
            config_url="https://example.com/.well-known/openid-configuration",
            client_id="test",
            client_secret="secret",
            scope="openid profile",
            callback_path="/callback",
        )
        assert config.claim_mappings == {}
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/sdk/auth/test_capability_mapper.py::TestClaimMappingsConfigField -v`
Expected: FAIL — `claim_mappings` field not found on models

**Step 3: Add `claim_mappings` to SDK provider configs**

In `src/mxcp/sdk/auth/models.py`, add to the `Field` import if not already present, then add this field to each of these 7 classes: `GitHubAuthConfigModel` (after line 69), `AtlassianAuthConfigModel` (after line 88), `SalesforceAuthConfigModel` (after line 107), `KeycloakAuthConfigModel` (after line 126), `GoogleAuthConfigModel` (after line 145), `OIDCAuthConfigModel` (after line 193, before the validator), `OIDCVerifierAuthConfigModel` (after line 221, before the validator):

```python
    claim_mappings: dict[str, dict[str, list[str]]] = Field(default_factory=dict)
```

**Step 4: Add `claim_mappings` to User (server) provider configs**

In `src/mxcp/server/core/config/models.py`, add the same field to all 7 User provider config classes: `UserGitHubAuthConfigModel` (after line 319), `UserAtlassianAuthConfigModel` (after line 331), `UserSalesforceAuthConfigModel` (after line 343), `UserKeycloakAuthConfigModel` (after line 353), `UserGoogleAuthConfigModel` (after line 365), `UserOIDCAuthConfigModel` (after line 378, before validator), `UserOIDCVerifierAuthConfigModel` (after line 397, before validator):

```python
    claim_mappings: dict[str, dict[str, list[str]]] = Field(default_factory=dict)
```

Note: `Field` is already imported in both files.

**Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/sdk/auth/test_capability_mapper.py -v`
Expected: All tests PASS (both Task 1 and Task 2 tests)

**Step 6: Run existing tests to check for regressions**

Run: `uv run pytest tests/sdk/auth/ -v`
Expected: All existing auth tests still PASS. The new field has a default so no existing code breaks.

**Step 7: Commit**

```bash
git add src/mxcp/sdk/auth/models.py src/mxcp/server/core/config/models.py tests/sdk/auth/test_capability_mapper.py
git commit -m "feat: add claim_mappings field to all provider config models"
```

---

### Task 3: Rename `UserInfo.mxcp_scopes` to `capabilities` and add `capabilities` to `UserContextModel`

**Files:**
- Modify: `src/mxcp/sdk/auth/contracts.py:66` — rename `mxcp_scopes` to `capabilities`
- Modify: `src/mxcp/sdk/auth/models.py:256-270` — add `capabilities` to `UserContextModel`
- Modify: `src/mxcp/sdk/auth/auth_service.py:173,183` — update references to `mxcp_scopes`
- Modify: `src/mxcp/server/core/auth/issuer_provider.py:362,370` — update references to `mxcp_scopes`
- Modify: `src/mxcp/server/interfaces/server/mcp.py:665-675` — forward `capabilities` to `UserContextModel`

**Step 1: Find all references to `mxcp_scopes`**

Run: `uv run grep -rn "mxcp_scopes" src/`
Note every occurrence. These all need updating.

**Step 2: Rename `mxcp_scopes` to `capabilities` in `contracts.py`**

In `src/mxcp/sdk/auth/contracts.py`, line 66, change:
```python
    mxcp_scopes: list[str] | None = None
```
to:
```python
    capabilities: list[str] = Field(default_factory=list)
```

Note the type change: `list[str] | None = None` → `list[str] = Field(default_factory=list)`. A capability list that is always present (empty by default) is cleaner than an optional that must be null-checked.

**Step 3: Add `capabilities` to `UserContextModel`**

In `src/mxcp/sdk/auth/models.py`, after line 270 (`external_token`), add:

```python
    capabilities: list[str] = Field(default_factory=list)
```

**Step 4: Update `AuthService.derive_mxcp_scopes` references**

In `src/mxcp/sdk/auth/auth_service.py`, line 183, change:
```python
                "mxcp_scopes": mxcp_scopes,
```
to:
```python
                "capabilities": mxcp_scopes,
```

**Step 5: Update `issuer_provider.py` references**

In `src/mxcp/server/core/auth/issuer_provider.py`, line 370, change:
```python
                "mxcp_scopes": updated_mxcp_scopes,
```
to:
```python
                "capabilities": updated_mxcp_scopes,
```

**Step 6: Forward capabilities in `require_user_info`**

In `src/mxcp/server/interfaces/server/mcp.py`, lines 665-675, update the `UserContextModel` construction to include capabilities from `UserInfo`:

```python
            ctx_token = set_user_context(
                UserContextModel(
                    provider=info.provider,
                    user_id=info.user_id,
                    username=info.username,
                    email=info.email,
                    name=info.name,
                    avatar_url=info.avatar_url,
                    raw_profile=info.raw_profile,
                    external_token=None,
                    capabilities=info.capabilities,
                )
            )
```

**Step 7: Run all tests to check for regressions**

Run: `uv run pytest tests/ -v`
Expected: All tests PASS. Look for any test that referenced `mxcp_scopes` — they need updating too. Fix any found.

**Step 8: Commit**

```bash
git add src/mxcp/sdk/auth/contracts.py src/mxcp/sdk/auth/models.py src/mxcp/sdk/auth/auth_service.py src/mxcp/server/core/auth/issuer_provider.py src/mxcp/server/interfaces/server/mcp.py
git commit -m "refactor: rename mxcp_scopes to capabilities across auth models"
```

---

### Task 4: Wire CapabilityMapper into `require_user_info` (per-request derivation)

**Files:**
- Modify: `src/mxcp/server/interfaces/server/mcp.py:469-507,651-683` — create mapper, call it per-request
- Test: `tests/sdk/auth/test_capability_mapper.py` (add integration-style test)

**Step 1: Write the failing test**

Append to `tests/sdk/auth/test_capability_mapper.py`:

```python
class TestCapabilityMapperIntegration:
    """Test mapper used in the way require_user_info will call it."""

    def test_derive_from_auth0_style_profile(self) -> None:
        """Simulate an Auth0 raw_profile with URI-namespaced claims."""
        mapper = CapabilityMapper(
            claim_mappings={
                "https://mycompany.com/roles": {
                    "admin": ["admin", "billing.manage"],
                    "billing-manager": ["billing.manage"],
                },
                "https://mycompany.com/groups": {
                    "finance-team": ["billing.manage"],
                },
                "scope": {
                    "calendar.readonly": ["calendar.read"],
                },
            }
        )
        raw_profile = {
            "sub": "auth0|abc123",
            "https://mycompany.com/roles": ["billing-manager"],
            "https://mycompany.com/groups": ["finance-team", "engineering"],
            "scope": "openid profile email calendar.readonly",
        }
        result = mapper.derive(raw_profile)
        assert result == {"billing.manage", "calendar.read"}

    def test_derive_from_keycloak_style_profile(self) -> None:
        """Simulate a Keycloak raw_profile with nested role claims."""
        mapper = CapabilityMapper(
            claim_mappings={
                "realm_access.roles": {
                    "admin": ["admin"],
                    "billing-manager": ["billing.manage"],
                },
                "resource_access.mxcp-client.roles": {
                    "report-viewer": ["reports.view"],
                },
            }
        )
        raw_profile = {
            "sub": "kc-user-123",
            "realm_access": {"roles": ["admin", "billing-manager"]},
            "resource_access": {"mxcp-client": {"roles": ["report-viewer"]}},
        }
        result = mapper.derive(raw_profile)
        assert result == {"admin", "billing.manage", "reports.view"}

    def test_mapper_recreated_with_new_config_reflects_changes(self) -> None:
        """Simulate config reload: new mapper instance has different mappings."""
        raw_profile = {"https://mycompany.com/roles": ["admin"]}

        mapper_v1 = CapabilityMapper(
            claim_mappings={
                "https://mycompany.com/roles": {"admin": ["admin"]},
            }
        )
        assert mapper_v1.derive(raw_profile) == {"admin"}

        # Config reload creates a new mapper with updated mappings
        mapper_v2 = CapabilityMapper(
            claim_mappings={
                "https://mycompany.com/roles": {
                    "admin": ["admin", "super-admin"],
                },
            }
        )
        assert mapper_v2.derive(raw_profile) == {"admin", "super-admin"}
```

**Step 2: Run tests to verify they pass (these are unit-level, using mapper directly)**

Run: `uv run pytest tests/sdk/auth/test_capability_mapper.py::TestCapabilityMapperIntegration -v`
Expected: PASS (mapper already works, these just validate realistic profiles)

**Step 3: Wire mapper into RAWMCP initialization**

In `src/mxcp/server/interfaces/server/mcp.py`, in the `_initialize_oauth` method:

After the provider adapter is created (around line 483), extract `claim_mappings` from the active provider config and create a `CapabilityMapper`. Add a helper method to RAWMCP:

```python
def _build_capability_mapper(self) -> CapabilityMapper:
    """Create a CapabilityMapper from the active provider's claim_mappings."""
    auth_config = self.active_profile.auth
    provider = auth_config.provider
    provider_config = getattr(auth_config, provider, None)
    if provider_config and hasattr(provider_config, "claim_mappings"):
        return CapabilityMapper(claim_mappings=provider_config.claim_mappings)
    return CapabilityMapper(claim_mappings={})
```

Call it in `_initialize_oauth`, storing result as `self.capability_mapper`.

Add the import at the top of the file:
```python
from mxcp.sdk.auth.capabilities import CapabilityMapper
```

**Step 4: Call mapper in `require_user_info`**

In `require_user_info` (line 657), after getting `info`, derive capabilities:

```python
            info = get_verified_user_info()
            if info is None:
                raise HTTPException(401, "Authentication required")

            capabilities = list(self.capability_mapper.derive(info.raw_profile or {}))

            ctx_token = set_user_context(
                UserContextModel(
                    provider=info.provider,
                    user_id=info.user_id,
                    username=info.username,
                    email=info.email,
                    name=info.name,
                    avatar_url=info.avatar_url,
                    raw_profile=info.raw_profile,
                    external_token=None,
                    capabilities=capabilities,
                )
            )
```

Also ensure `self.capability_mapper` is initialized to `CapabilityMapper(claim_mappings={})` at the top of `_initialize_oauth` (before any early returns), so it's always available.

**Step 5: Run all tests**

Run: `uv run pytest tests/ -v`
Expected: All tests PASS

**Step 6: Commit**

```bash
git add src/mxcp/server/interfaces/server/mcp.py tests/sdk/auth/test_capability_mapper.py
git commit -m "feat: wire CapabilityMapper into require_user_info for per-request derivation"
```

---

### Task 5: Add `capabilities` to CEL policy context

**Files:**
- Modify: `src/mxcp/sdk/policy/enforcer.py:123-151` — add `capabilities` to user dict
- Test: `tests/sdk/policy/test_enforcer.py` (or appropriate existing test file)

**Step 1: Write the failing test**

Find the existing policy enforcer test file first:

Run: `uv run find tests/ -name "*enforcer*" -o -name "*policy*" | head -10`

Create or append a test that verifies capabilities are in the CEL context:

```python
def test_user_context_dict_includes_capabilities() -> None:
    """Capabilities from UserContextModel should appear in the CEL user dict."""
    enforcer = PolicyEnforcer(input_policies=[], output_policies=[])
    user_context = UserContextModel(
        provider="oidc",
        user_id="user1",
        username="alice",
        capabilities=["admin", "billing.manage"],
    )
    user_dict = enforcer._user_context_to_dict(user_context)
    assert user_dict["capabilities"] == ["admin", "billing.manage"]


def test_user_context_dict_capabilities_default_empty() -> None:
    """Capabilities should default to empty list when not set."""
    enforcer = PolicyEnforcer(input_policies=[], output_policies=[])
    user_context = UserContextModel(
        provider="oidc",
        user_id="user1",
        username="alice",
    )
    user_dict = enforcer._user_context_to_dict(user_context)
    assert user_dict["capabilities"] == []


def test_anonymous_user_has_empty_capabilities() -> None:
    """Anonymous user (None context) should have empty capabilities."""
    enforcer = PolicyEnforcer(input_policies=[], output_policies=[])
    user_dict = enforcer._user_context_to_dict(None)
    assert user_dict["capabilities"] == []
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/sdk/policy/ -v -k "capabilities"`
Expected: FAIL — `capabilities` key missing from dict

**Step 3: Update `_user_context_to_dict`**

In `src/mxcp/sdk/policy/enforcer.py`:

At line 128 (in the `None` branch), add `"capabilities": []` to the returned dict:

```python
        if user_context is None:
            return {
                "role": "anonymous",
                "permissions": [],
                "capabilities": [],
                "user_id": None,
                "username": None,
                "email": None,
                "provider": None,
            }
```

At line 143 (in the populated branch), add `"capabilities"`:

```python
        user_dict: dict[str, Any] = {
            "user_id": user_context.user_id,
            "username": user_context.username,
            "email": user_context.email,
            "provider": user_context.provider,
            "name": user_context.name,
            "role": "user",
            "permissions": [],
            "capabilities": list(user_context.capabilities),
        }
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/sdk/policy/ -v`
Expected: All policy tests PASS (existing + new)

**Step 5: Run full test suite**

Run: `uv run pytest tests/ -v`
Expected: All tests PASS

**Step 6: Commit**

```bash
git add src/mxcp/sdk/policy/enforcer.py tests/sdk/policy/
git commit -m "feat: add capabilities to CEL policy user context"
```

---

### Task 6: Final validation — run full test suite and quality checks

**Files:** None (validation only)

**Step 1: Run full test suite**

Run: `uv run pytest tests/ -v`
Expected: All tests PASS

**Step 2: Run code quality checks**

Run: `ruff check src/mxcp/sdk/auth/capabilities.py src/mxcp/sdk/auth/models.py src/mxcp/sdk/auth/contracts.py src/mxcp/sdk/policy/enforcer.py src/mxcp/server/interfaces/server/mcp.py src/mxcp/server/core/config/models.py`
Expected: No errors

**Step 3: Run mypy type check**

Run: `mypy src/mxcp/sdk/auth/capabilities.py`
Expected: No type errors

**Step 4: Commit any fixes**

If any quality check failed, fix and commit:
```bash
git commit -m "fix: address linting/type issues in capability mapper"
```
