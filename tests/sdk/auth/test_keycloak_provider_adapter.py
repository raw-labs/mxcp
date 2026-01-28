import asyncio
from urllib.parse import parse_qs, urlsplit

import pytest
from pytest import MonkeyPatch

from mxcp.sdk.auth.contracts import ProviderError
from mxcp.sdk.auth.models import KeycloakAuthConfigModel
from mxcp.sdk.auth.providers.keycloak import KeycloakProviderAdapter
from tests.sdk.auth.provider_adapter_testkit import (
    FakeAsyncHttpClient,
    FakeResponse,
    patch_http_client,
)


@pytest.fixture
def keycloak_config() -> KeycloakAuthConfigModel:
    return KeycloakAuthConfigModel(
        client_id="cid",
        client_secret="secret",
        realm="master",
        server_url="https://kc.example.com",
        scope="openid profile",
        callback_path="/keycloak/callback",
    )


def test_build_authorize_url_includes_required_params(
    keycloak_config: KeycloakAuthConfigModel,
) -> None:
    adapter = KeycloakProviderAdapter(keycloak_config)
    url = adapter.build_authorize_url(
        redirect_uri="https://server/keycloak/callback",
        state="abc",
        code_challenge="cc",
        code_challenge_method="S256",
        extra_params={"foo": "bar"},
    )
    query = parse_qs(urlsplit(url).query)
    assert query["response_type"] == ["code"]
    assert query["scope"] == ["openid profile"]
    assert query["redirect_uri"] == ["https://server/keycloak/callback"]


def test_build_authorize_url_defaults_method_when_challenge_present(
    keycloak_config: KeycloakAuthConfigModel,
) -> None:
    adapter = KeycloakProviderAdapter(keycloak_config)
    url = adapter.build_authorize_url(
        redirect_uri="https://server/keycloak/callback",
        state="abc",
        code_challenge="cc",
        code_challenge_method=None,
    )
    query = parse_qs(urlsplit(url).query)
    assert query["code_challenge"] == ["cc"]
    assert query["code_challenge_method"] == ["S256"]


def test_build_authorize_url_uses_configured_scope_when_empty() -> None:
    adapter = KeycloakProviderAdapter(
        KeycloakAuthConfigModel(
            client_id="cid",
            client_secret="secret",
            realm="master",
            server_url="https://kc.example.com",
            scope="",
            callback_path="/keycloak/callback",
        )
    )
    url = adapter.build_authorize_url(
        redirect_uri="https://server/keycloak/callback",
        state="abc",
    )
    query = parse_qs(urlsplit(url).query, keep_blank_values=True)
    assert query["scope"] == [""]


@pytest.mark.asyncio
async def test_exchange_code_happy_path(
    monkeypatch: MonkeyPatch, keycloak_config: KeycloakAuthConfigModel
) -> None:
    post_response = FakeResponse(
        200,
        {"access_token": "at", "refresh_token": "rt", "expires_in": 3600, "scope": "openid email"},
    )
    fake_client = FakeAsyncHttpClient(post_response=post_response)
    patch_http_client(
        monkeypatch, "mxcp.sdk.auth.providers.keycloak.create_mcp_http_client", fake_client
    )

    adapter = KeycloakProviderAdapter(keycloak_config)
    monkeypatch.setattr(
        adapter, "_fetch_user_profile", lambda token: asyncio.sleep(0, {"sub": "user-1"})
    )

    grant = await adapter.exchange_code(
        code="code",
        redirect_uri="https://server/keycloak/callback",
        code_verifier=None,
        scopes=["openid"],
    )
    assert grant.access_token == "at"
    assert grant.refresh_token == "rt"
    assert grant.provider_scopes_granted == ["openid", "email"]


@pytest.mark.asyncio
async def test_refresh_token_happy_path(
    monkeypatch: MonkeyPatch, keycloak_config: KeycloakAuthConfigModel
) -> None:
    post_response = FakeResponse(200, {"access_token": "new-at", "scope": "openid"})
    fake_client = FakeAsyncHttpClient(post_response=post_response)
    patch_http_client(
        monkeypatch, "mxcp.sdk.auth.providers.keycloak.create_mcp_http_client", fake_client
    )

    adapter = KeycloakProviderAdapter(keycloak_config)
    grant = await adapter.refresh_token(refresh_token="rt", scopes=["openid"])
    assert grant.access_token == "new-at"
    assert grant.refresh_token == "rt"
    assert grant.provider_scopes_granted == ["openid"]


@pytest.mark.asyncio
async def test_fetch_user_info_requires_sub(
    monkeypatch: MonkeyPatch, keycloak_config: KeycloakAuthConfigModel
) -> None:
    adapter = KeycloakProviderAdapter(keycloak_config)
    monkeypatch.setattr(
        adapter, "_fetch_user_profile", lambda token: asyncio.sleep(0, {"email": "e"})
    )
    with pytest.raises(ProviderError):
        await adapter.fetch_user_info(access_token="at")


@pytest.mark.asyncio
async def test_fetch_user_info_happy_path(
    monkeypatch: MonkeyPatch, keycloak_config: KeycloakAuthConfigModel
) -> None:
    adapter = KeycloakProviderAdapter(keycloak_config)
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
