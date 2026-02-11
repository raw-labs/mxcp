"""Tests for OIDC discovery document parsing and fetching."""

import pytest
from pydantic import ValidationError

from mxcp.sdk.auth.contracts import ProviderError
from mxcp.sdk.auth.providers.oidc_discovery import (
    OIDCDiscoveryDocument,
    fetch_oidc_discovery,
)
from tests.sdk.auth.provider_adapter_testkit import (
    FakeAsyncHttpClient,
    FakeResponse,
    FakeResponseJsonError,
    patch_http_client,
)


# ── Model parsing ──────────────────────────────────────────────────────

VALID_DISCOVERY = {
    "issuer": "https://idp.example.com",
    "authorization_endpoint": "https://idp.example.com/authorize",
    "token_endpoint": "https://idp.example.com/token",
    "userinfo_endpoint": "https://idp.example.com/userinfo",
    "revocation_endpoint": "https://idp.example.com/revoke",
    "code_challenge_methods_supported": ["S256"],
}


def test_parse_complete_document() -> None:
    doc = OIDCDiscoveryDocument.model_validate(VALID_DISCOVERY)
    assert doc.issuer == "https://idp.example.com"
    assert doc.authorization_endpoint == "https://idp.example.com/authorize"
    assert doc.token_endpoint == "https://idp.example.com/token"
    assert doc.userinfo_endpoint == "https://idp.example.com/userinfo"
    assert doc.revocation_endpoint == "https://idp.example.com/revoke"
    assert doc.code_challenge_methods_supported == ["S256"]


def test_parse_minimal_document() -> None:
    doc = OIDCDiscoveryDocument.model_validate(
        {
            "issuer": "https://idp.example.com",
            "authorization_endpoint": "https://idp.example.com/authorize",
            "token_endpoint": "https://idp.example.com/token",
        }
    )
    assert doc.issuer == "https://idp.example.com"
    assert doc.userinfo_endpoint is None
    assert doc.revocation_endpoint is None
    assert doc.code_challenge_methods_supported is None


def test_missing_issuer_rejected() -> None:
    data = dict(VALID_DISCOVERY)
    del data["issuer"]
    with pytest.raises(ValidationError):
        OIDCDiscoveryDocument.model_validate(data)


def test_missing_authorization_endpoint_rejected() -> None:
    data = dict(VALID_DISCOVERY)
    del data["authorization_endpoint"]
    with pytest.raises(ValidationError):
        OIDCDiscoveryDocument.model_validate(data)


def test_missing_token_endpoint_rejected() -> None:
    data = dict(VALID_DISCOVERY)
    del data["token_endpoint"]
    with pytest.raises(ValidationError):
        OIDCDiscoveryDocument.model_validate(data)


def test_extra_fields_ignored() -> None:
    data = dict(VALID_DISCOVERY)
    data["jwks_uri"] = "https://idp.example.com/jwks"
    data["response_types_supported"] = ["code"]
    doc = OIDCDiscoveryDocument.model_validate(data)
    assert doc.issuer == "https://idp.example.com"
    assert not hasattr(doc, "jwks_uri")


def test_pkce_detection_from_discovery() -> None:
    data = dict(VALID_DISCOVERY)
    data["code_challenge_methods_supported"] = ["S256", "plain"]
    doc = OIDCDiscoveryDocument.model_validate(data)
    assert doc.code_challenge_methods_supported == ["S256", "plain"]


def test_pkce_none_when_absent() -> None:
    data = {
        "issuer": "https://idp.example.com",
        "authorization_endpoint": "https://idp.example.com/authorize",
        "token_endpoint": "https://idp.example.com/token",
    }
    doc = OIDCDiscoveryDocument.model_validate(data)
    assert doc.code_challenge_methods_supported is None


# ── fetch_oidc_discovery ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_fetch_happy_path(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_client = FakeAsyncHttpClient(
        post_response=FakeResponse(200, {}),
        default_get_response=FakeResponse(200, VALID_DISCOVERY),
    )
    patch_http_client(
        monkeypatch,
        "mxcp.sdk.auth.providers.oidc_discovery.create_mcp_http_client",
        fake_client,
    )

    doc = await fetch_oidc_discovery("https://idp.example.com/.well-known/openid-configuration")
    assert doc.issuer == "https://idp.example.com"
    assert doc.authorization_endpoint == "https://idp.example.com/authorize"


@pytest.mark.asyncio
async def test_fetch_non_200_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_client = FakeAsyncHttpClient(
        post_response=FakeResponse(200, {}),
        default_get_response=FakeResponse(404, {}),
    )
    patch_http_client(
        monkeypatch,
        "mxcp.sdk.auth.providers.oidc_discovery.create_mcp_http_client",
        fake_client,
    )

    with pytest.raises(ProviderError) as exc_info:
        await fetch_oidc_discovery("https://idp.example.com/.well-known/openid-configuration")
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_fetch_invalid_json_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_client = FakeAsyncHttpClient(
        post_response=FakeResponse(200, {}),
        default_get_response=FakeResponseJsonError(200, None),
    )
    patch_http_client(
        monkeypatch,
        "mxcp.sdk.auth.providers.oidc_discovery.create_mcp_http_client",
        fake_client,
    )

    with pytest.raises(ProviderError) as exc_info:
        await fetch_oidc_discovery("https://idp.example.com/.well-known/openid-configuration")
    assert exc_info.value.error == "server_error"


@pytest.mark.asyncio
async def test_fetch_network_error_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    import httpx

    class _FailClient:
        async def __aenter__(self) -> "_FailClient":
            return self

        async def __aexit__(self, *args: object) -> bool:
            return False

        async def get(self, *args: object, **kwargs: object) -> None:
            raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(
        "mxcp.sdk.auth.providers.oidc_discovery.create_mcp_http_client",
        lambda: _FailClient(),
    )

    with pytest.raises(ProviderError) as exc_info:
        await fetch_oidc_discovery("https://idp.example.com/.well-known/openid-configuration")
    assert exc_info.value.error == "temporarily_unavailable"
    assert exc_info.value.status_code == 503
