"""Tests for the generic OIDC provider adapter."""

import asyncio
from urllib.parse import parse_qs, urlsplit

import pytest
from pytest import MonkeyPatch

from mxcp.sdk.auth.contracts import ProviderError
from mxcp.sdk.auth.models import OIDCAuthConfigModel
from mxcp.sdk.auth.providers.oidc import OIDCProviderAdapter
from mxcp.sdk.auth.providers.oidc_discovery import OIDCDiscoveryDocument
from tests.sdk.auth.provider_adapter_testkit import (
    FakeAsyncHttpClient,
    FakeResponse,
    patch_http_client,
)

DISCOVERY_DOC = OIDCDiscoveryDocument(
    issuer="https://idp.example.com",
    authorization_endpoint="https://idp.example.com/authorize",
    token_endpoint="https://idp.example.com/token",
    userinfo_endpoint="https://idp.example.com/userinfo",
    revocation_endpoint="https://idp.example.com/revoke",
    code_challenge_methods_supported=["S256"],
)

DISCOVERY_NO_PKCE = OIDCDiscoveryDocument(
    issuer="https://idp.example.com",
    authorization_endpoint="https://idp.example.com/authorize",
    token_endpoint="https://idp.example.com/token",
    userinfo_endpoint="https://idp.example.com/userinfo",
)


@pytest.fixture
def oidc_config() -> OIDCAuthConfigModel:
    return OIDCAuthConfigModel(
        config_url="https://idp.example.com/.well-known/openid-configuration",
        client_id="cid",
        client_secret="secret",
        scope="openid profile",
        callback_path="/oidc/callback",
    )


@pytest.fixture
def oidc_config_with_audience() -> OIDCAuthConfigModel:
    return OIDCAuthConfigModel(
        config_url="https://idp.example.com/.well-known/openid-configuration",
        client_id="cid",
        client_secret="secret",
        scope="openid profile",
        callback_path="/oidc/callback",
        audience="https://api.example.com",
        extra_authorize_params={"prompt": "consent"},
    )


def _make_ready(adapter: OIDCProviderAdapter, discovery: OIDCDiscoveryDocument) -> None:
    """Simulate ensure_ready() by injecting a discovery document."""
    adapter._discovery = discovery
    adapter.auth_url = discovery.authorization_endpoint
    adapter.token_url = discovery.token_endpoint
    adapter.userinfo_url = discovery.userinfo_endpoint
    adapter.revoke_url = discovery.revocation_endpoint
    if discovery.code_challenge_methods_supported:
        adapter.pkce_methods_supported = list(discovery.code_challenge_methods_supported)
    else:
        adapter.pkce_methods_supported = ["S256"]


# ── ensure_ready ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_ensure_ready_fetches_and_caches(
    monkeypatch: MonkeyPatch, oidc_config: OIDCAuthConfigModel
) -> None:
    discovery_payload = DISCOVERY_DOC.model_dump()
    fake_client = FakeAsyncHttpClient(
        post_response=FakeResponse(200, {}),
        default_get_response=FakeResponse(200, discovery_payload),
    )
    patch_http_client(
        monkeypatch,
        "mxcp.sdk.auth.providers.oidc_discovery.create_mcp_http_client",
        fake_client,
    )

    adapter = OIDCProviderAdapter(oidc_config)
    assert adapter._discovery is None

    await adapter.ensure_ready()
    assert adapter._discovery is not None
    assert adapter.auth_url == "https://idp.example.com/authorize"
    assert adapter.token_url == "https://idp.example.com/token"
    assert adapter.pkce_methods_supported == ["S256"]

    # Second call is a no-op (no additional HTTP request).
    await adapter.ensure_ready()
    assert fake_client.get_calls == 1


@pytest.mark.asyncio
async def test_ensure_ready_defaults_pkce_when_absent(
    monkeypatch: MonkeyPatch, oidc_config: OIDCAuthConfigModel
) -> None:
    discovery_payload = DISCOVERY_NO_PKCE.model_dump()
    fake_client = FakeAsyncHttpClient(
        post_response=FakeResponse(200, {}),
        default_get_response=FakeResponse(200, discovery_payload),
    )
    patch_http_client(
        monkeypatch,
        "mxcp.sdk.auth.providers.oidc_discovery.create_mcp_http_client",
        fake_client,
    )

    adapter = OIDCProviderAdapter(oidc_config)
    await adapter.ensure_ready()
    assert adapter.pkce_methods_supported == ["S256"]


# ── build_authorize_url ─────────────────────────────────────────────────


def test_build_authorize_url_includes_required_params(
    oidc_config: OIDCAuthConfigModel,
) -> None:
    adapter = OIDCProviderAdapter(oidc_config)
    _make_ready(adapter, DISCOVERY_DOC)

    url = adapter.build_authorize_url(
        redirect_uri="https://server/oidc/callback",
        state="abc",
        code_challenge="cc",
        code_challenge_method="S256",
        extra_params={"foo": "bar"},
    )
    query = parse_qs(urlsplit(url).query)
    assert query["response_type"] == ["code"]
    assert query["scope"] == ["openid profile"]
    assert query["redirect_uri"] == ["https://server/oidc/callback"]
    assert query["client_id"] == ["cid"]
    assert query["state"] == ["abc"]
    assert query["code_challenge"] == ["cc"]
    assert query["code_challenge_method"] == ["S256"]
    assert query["foo"] == ["bar"]


def test_build_authorize_url_includes_audience_and_extra_params(
    oidc_config_with_audience: OIDCAuthConfigModel,
) -> None:
    adapter = OIDCProviderAdapter(oidc_config_with_audience)
    _make_ready(adapter, DISCOVERY_DOC)

    url = adapter.build_authorize_url(
        redirect_uri="https://server/oidc/callback",
        state="abc",
    )
    query = parse_qs(urlsplit(url).query)
    assert query["audience"] == ["https://api.example.com"]
    assert query["prompt"] == ["consent"]


def test_build_authorize_url_defaults_method_when_challenge_present(
    oidc_config: OIDCAuthConfigModel,
) -> None:
    adapter = OIDCProviderAdapter(oidc_config)
    _make_ready(adapter, DISCOVERY_DOC)

    url = adapter.build_authorize_url(
        redirect_uri="https://server/oidc/callback",
        state="abc",
        code_challenge="cc",
        code_challenge_method=None,
    )
    query = parse_qs(urlsplit(url).query)
    assert query["code_challenge"] == ["cc"]
    assert query["code_challenge_method"] == ["S256"]


def test_build_authorize_url_raises_without_ensure_ready(
    oidc_config: OIDCAuthConfigModel,
) -> None:
    adapter = OIDCProviderAdapter(oidc_config)
    with pytest.raises(AssertionError, match="ensure_ready"):
        adapter.build_authorize_url(
            redirect_uri="https://server/oidc/callback",
            state="abc",
        )


# ── exchange_code ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_exchange_code_happy_path(
    monkeypatch: MonkeyPatch, oidc_config: OIDCAuthConfigModel
) -> None:
    post_response = FakeResponse(
        200,
        {"access_token": "at", "refresh_token": "rt", "expires_in": 3600, "scope": "openid email"},
    )
    fake_client = FakeAsyncHttpClient(post_response=post_response)
    patch_http_client(
        monkeypatch, "mxcp.sdk.auth.providers.oidc.create_mcp_http_client", fake_client
    )

    adapter = OIDCProviderAdapter(oidc_config)
    _make_ready(adapter, DISCOVERY_DOC)

    grant = await adapter.exchange_code(
        code="code",
        redirect_uri="https://server/oidc/callback",
        code_verifier=None,
        scopes=["openid"],
    )
    assert grant.access_token == "at"
    assert grant.refresh_token == "rt"
    assert grant.provider_scopes_granted == ["openid", "email"]


@pytest.mark.asyncio
async def test_exchange_code_with_audience(
    monkeypatch: MonkeyPatch, oidc_config_with_audience: OIDCAuthConfigModel
) -> None:
    post_response = FakeResponse(
        200,
        {"access_token": "at", "expires_in": 3600, "scope": "openid"},
    )
    fake_client = FakeAsyncHttpClient(post_response=post_response)
    patch_http_client(
        monkeypatch, "mxcp.sdk.auth.providers.oidc.create_mcp_http_client", fake_client
    )

    adapter = OIDCProviderAdapter(oidc_config_with_audience)
    _make_ready(adapter, DISCOVERY_DOC)

    grant = await adapter.exchange_code(
        code="code",
        redirect_uri="https://server/oidc/callback",
        code_verifier=None,
        scopes=["openid"],
    )
    assert grant.access_token == "at"


# ── refresh_token ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_refresh_token_happy_path(
    monkeypatch: MonkeyPatch, oidc_config: OIDCAuthConfigModel
) -> None:
    post_response = FakeResponse(200, {"access_token": "new-at", "scope": "openid"})
    fake_client = FakeAsyncHttpClient(post_response=post_response)
    patch_http_client(
        monkeypatch, "mxcp.sdk.auth.providers.oidc.create_mcp_http_client", fake_client
    )

    adapter = OIDCProviderAdapter(oidc_config)
    _make_ready(adapter, DISCOVERY_DOC)

    grant = await adapter.refresh_token(refresh_token="rt", scopes=["openid"])
    assert grant.access_token == "new-at"
    assert grant.refresh_token == "rt"
    assert grant.provider_scopes_granted == ["openid"]


@pytest.mark.asyncio
async def test_refresh_token_with_audience(
    monkeypatch: MonkeyPatch, oidc_config_with_audience: OIDCAuthConfigModel
) -> None:
    post_response = FakeResponse(200, {"access_token": "new-at", "scope": "openid"})
    fake_client = FakeAsyncHttpClient(post_response=post_response)
    patch_http_client(
        monkeypatch, "mxcp.sdk.auth.providers.oidc.create_mcp_http_client", fake_client
    )

    adapter = OIDCProviderAdapter(oidc_config_with_audience)
    _make_ready(adapter, DISCOVERY_DOC)

    grant = await adapter.refresh_token(refresh_token="rt", scopes=["openid"])
    assert grant.access_token == "new-at"


# ── fetch_user_info ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_fetch_user_info_happy_path(
    monkeypatch: MonkeyPatch, oidc_config: OIDCAuthConfigModel
) -> None:
    adapter = OIDCProviderAdapter(oidc_config)
    _make_ready(adapter, DISCOVERY_DOC)

    monkeypatch.setattr(
        adapter,
        "_fetch_user_profile",
        lambda token: asyncio.sleep(
            0,
            {
                "sub": "user-1",
                "email": "user@example.com",
                "preferred_username": "user",
                "picture": "pic",
                "scope": "openid email",
            },
        ),
    )
    user_info = await adapter.fetch_user_info(access_token="at")
    assert user_info.user_id == "user-1"
    assert user_info.email == "user@example.com"
    assert user_info.username == "user"
    assert user_info.avatar_url == "pic"
    assert user_info.provider_scopes_granted == ["openid", "email"]
    assert user_info.provider == "oidc"


@pytest.mark.asyncio
async def test_fetch_user_info_requires_sub(
    monkeypatch: MonkeyPatch, oidc_config: OIDCAuthConfigModel
) -> None:
    adapter = OIDCProviderAdapter(oidc_config)
    _make_ready(adapter, DISCOVERY_DOC)

    monkeypatch.setattr(
        adapter, "_fetch_user_profile", lambda token: asyncio.sleep(0, {"email": "e"})
    )
    with pytest.raises(ProviderError):
        await adapter.fetch_user_info(access_token="at")


# ── callback_path ──────────────────────────────────────────────────────


def test_callback_path_property(oidc_config: OIDCAuthConfigModel) -> None:
    adapter = OIDCProviderAdapter(oidc_config)
    assert adapter.callback_path == "/oidc/callback"
