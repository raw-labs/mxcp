import asyncio
from typing import Any
from urllib.parse import parse_qs, urlsplit

import pytest
from pytest import MonkeyPatch

from mxcp.sdk.auth.contracts import ProviderError
from mxcp.sdk.auth.models import KeycloakAuthConfigModel
from mxcp.sdk.auth.providers.keycloak import KeycloakProviderAdapter


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict[str, object], text: str = "") -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = text

    def json(self) -> dict[str, object]:
        return self._payload


class _FakeResponseJsonError(_FakeResponse):
    def json(self) -> dict[str, object]:
        raise ValueError("invalid json")


class _FakeClient:
    def __init__(
        self,
        *,
        post_response: _FakeResponse,
        get_response: _FakeResponse | None = None,
    ) -> None:
        self._post_response = post_response
        self._get_response = get_response or _FakeResponse(200, {"sub": "user-1"})

    async def __aenter__(self) -> "_FakeClient":
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: Any,
    ) -> bool:
        return False

    async def post(self, *args: Any, **kwargs: Any) -> _FakeResponse:
        return self._post_response

    async def get(self, *args: Any, **kwargs: Any) -> _FakeResponse:
        return self._get_response


@pytest.fixture
def keycloak_config() -> KeycloakAuthConfigModel:
    return KeycloakAuthConfigModel(
        client_id="cid",
        client_secret="secret",
        realm="master",
        server_url="https://kc.example.com",
        scope=None,
        callback_path="/keycloak/callback",
    )


def test_build_authorize_url_includes_required_params(
    keycloak_config: KeycloakAuthConfigModel,
) -> None:
    adapter = KeycloakProviderAdapter(keycloak_config)
    url = adapter.build_authorize_url(
        redirect_uri="https://server/keycloak/callback",
        state="abc",
        scopes=["openid", "profile"],
        code_challenge="cc",
        code_challenge_method="S256",
        extra_params={"foo": "bar"},
    )
    query = parse_qs(urlsplit(url).query)
    assert query["client_id"] == ["cid"]
    assert query["state"] == ["abc"]
    assert query["response_type"] == ["code"]
    assert query["scope"] == ["openid profile"]
    assert query["redirect_uri"] == ["https://server/keycloak/callback"]
    assert query["code_challenge"] == ["cc"]
    assert query["code_challenge_method"] == ["S256"]
    assert query["foo"] == ["bar"]


def test_build_authorize_url_defaults_method_when_challenge_present(
    keycloak_config: KeycloakAuthConfigModel,
) -> None:
    adapter = KeycloakProviderAdapter(keycloak_config)
    url = adapter.build_authorize_url(
        redirect_uri="https://server/keycloak/callback",
        state="abc",
        scopes=["openid"],
        code_challenge="cc",
        code_challenge_method=None,
    )
    query = parse_qs(urlsplit(url).query)
    assert query["code_challenge"] == ["cc"]
    assert query["code_challenge_method"] == ["S256"]


def test_build_authorize_url_falls_back_to_default_scope(
    keycloak_config: KeycloakAuthConfigModel,
) -> None:
    adapter = KeycloakProviderAdapter(keycloak_config)
    url = adapter.build_authorize_url(
        redirect_uri="https://server/keycloak/callback",
        state="abc",
        scopes=[],
    )
    query = parse_qs(urlsplit(url).query)
    assert query["scope"] == ["openid profile email"]


@pytest.mark.asyncio
async def test_exchange_code_happy_path(
    monkeypatch: MonkeyPatch, keycloak_config: KeycloakAuthConfigModel
) -> None:
    post_response = _FakeResponse(
        200,
        {"access_token": "at", "refresh_token": "rt", "expires_in": 3600, "scope": "openid email"},
    )
    fake_client = _FakeClient(post_response=post_response)
    monkeypatch.setattr(
        "mxcp.sdk.auth.providers.keycloak.create_mcp_http_client", lambda: fake_client
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
async def test_exchange_code_invalid_json_raises_provider_error(
    monkeypatch: MonkeyPatch, keycloak_config: KeycloakAuthConfigModel
) -> None:
    post_response = _FakeResponseJsonError(200, {})
    fake_client = _FakeClient(post_response=post_response)
    monkeypatch.setattr(
        "mxcp.sdk.auth.providers.keycloak.create_mcp_http_client", lambda: fake_client
    )

    adapter = KeycloakProviderAdapter(keycloak_config)
    with pytest.raises(ProviderError):
        await adapter.exchange_code(
            code="code",
            redirect_uri="https://server/keycloak/callback",
            code_verifier=None,
            scopes=["openid"],
        )


@pytest.mark.asyncio
async def test_refresh_token_happy_path(
    monkeypatch: MonkeyPatch, keycloak_config: KeycloakAuthConfigModel
) -> None:
    post_response = _FakeResponse(200, {"access_token": "new-at", "scope": "openid"})
    fake_client = _FakeClient(post_response=post_response)
    monkeypatch.setattr(
        "mxcp.sdk.auth.providers.keycloak.create_mcp_http_client", lambda: fake_client
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


@pytest.mark.asyncio
async def test_revoke_token_propagates_status_code(
    monkeypatch: MonkeyPatch, keycloak_config: KeycloakAuthConfigModel
) -> None:
    post_response = _FakeResponse(500, {})
    fake_client = _FakeClient(post_response=post_response)
    monkeypatch.setattr(
        "mxcp.sdk.auth.providers.keycloak.create_mcp_http_client", lambda: fake_client
    )

    adapter = KeycloakProviderAdapter(keycloak_config)
    with pytest.raises(ProviderError) as exc:
        await adapter.revoke_token(token="t")
    assert exc.value.status_code == 500


def test_callback_path_property_matches_config(
    keycloak_config: KeycloakAuthConfigModel,
) -> None:
    adapter = KeycloakProviderAdapter(keycloak_config)
    assert adapter.callback_path == keycloak_config.callback_path
