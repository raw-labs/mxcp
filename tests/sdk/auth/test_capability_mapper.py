"""Tests for CapabilityMapper."""

from __future__ import annotations

import logging

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
        result = mapper.derive({"resource_access": {"mxcp-client": {"roles": ["report-viewer"]}}})
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
        mapper = CapabilityMapper(
            claim_mappings={
                "a.b": {
                    "val": ["cap_from_exact"],
                },
            }
        )
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


class TestCapabilityMapperIntegration:
    """Test mapper used in the way require_user_info will call it."""

    def test_derive_from_auth0_style_profile(self) -> None:
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
        raw_profile = {"https://mycompany.com/roles": ["admin"]}
        mapper_v1 = CapabilityMapper(
            claim_mappings={"https://mycompany.com/roles": {"admin": ["admin"]}}
        )
        assert mapper_v1.derive(raw_profile) == {"admin"}
        mapper_v2 = CapabilityMapper(
            claim_mappings={"https://mycompany.com/roles": {"admin": ["admin", "super-admin"]}}
        )
        assert mapper_v2.derive(raw_profile) == {"admin", "super-admin"}


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
        field_info = model_class.model_fields.get("claim_mappings")
        assert field_info is not None, f"{model_class.__name__} missing claim_mappings field"
        assert field_info.default_factory is not None

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
