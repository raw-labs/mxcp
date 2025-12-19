import asyncio
from typing import Any
from urllib.parse import parse_qs, urlsplit

import pytest
from pytest import MonkeyPatch

from mxcp.sdk.auth.contracts import ProviderError
from mxcp.sdk.auth.models import AtlassianAuthConfigModel
from mxcp.sdk.auth.providers.atlassian import AtlassianProviderAdapter


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict[str, object]) -> None:
        self.status_code = status_code
        self._payload = payload

    def json(self) -> dict[str, object]:
        return self._payload


class _FakeResponseJsonError(_FakeResponse):
    def json(self) -> dict[str, object]:
        raise ValueError("invalid json")


class _FakeClient:
    def __init__(self, *, post_response: _FakeResponse, get_response: _FakeResponse | None = None) -> None:
        self._post_response = post_response
        self._get_response = get_response or _FakeResponse(200, {"account_id": "acct-1"})

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
def atlassian_config() -> AtlassianAuthConfigModel:
    return AtlassianAuthConfigModel(
        client_id="cid",
        client_secret="secret",
        scope="read:me offline_access",
        callback_path="/atlassian/callback",
        auth_url="https://auth.atlassian.com/authorize",
        token_url="https://auth.atlassian.com/oauth/token",
    )


def test_build_authorize_url_includes_required_params(atlassian_config: AtlassianAuthConfigModel) -> None:
    adapter = AtlassianProviderAdapter(atlassian_config)
    url = adapter.build_authorize_url(
        redirect_uri="https://server/atlassian/callback",
        state="abc",
        scopes=[],
        code_challenge="cc",
        code_challenge_method="S256",
        extra_params={"foo": "bar"},
    )
    query = parse_qs(urlsplit(url).query)
    assert query["audience"] == ["api.atlassian.com"]
    assert query["client_id"] == ["cid"]
    assert query["state"] == ["abc"]
    assert query["response_type"] == ["code"]
    assert query["prompt"] == ["consent"]
    assert query["scope"] == ["read:me offline_access"]
    assert query["code_challenge"] == ["cc"]
    assert query["code_challenge_method"] == ["S256"]
    assert query["foo"] == ["bar"]


@pytest.mark.asyncio
async def test_exchange_code_happy_path(monkeypatch: MonkeyPatch, atlassian_config: AtlassianAuthConfigModel) -> None:
    post_response = _FakeResponse(
        200,
        {"access_token": "at", "refresh_token": "rt", "expires_in": 3600, "token_type": "Bearer"},
    )
    fake_client = _FakeClient(post_response=post_response)
    monkeypatch.setattr(
        "mxcp.sdk.auth.providers.atlassian.create_mcp_http_client", lambda: fake_client
    )

    adapter = AtlassianProviderAdapter(atlassian_config)
    monkeypatch.setattr(adapter, "_fetch_me", lambda token: asyncio.sleep(0, {"account_id": "acct-1"}))

    grant = await adapter.exchange_code(
        code="code",
        redirect_uri="https://server/atlassian/callback",
        code_verifier=None,
        scopes=["read:me"],
    )
    assert grant.access_token == "at"
    assert grant.refresh_token == "rt"
    assert grant.provider_scopes_granted


@pytest.mark.asyncio
async def test_exchange_code_prefers_provider_scope_when_returned(
    monkeypatch: MonkeyPatch, atlassian_config: AtlassianAuthConfigModel
) -> None:
    post_response = _FakeResponse(
        200,
        {
            "access_token": "at",
            "refresh_token": "rt",
            "expires_in": 3600,
            "token_type": "Bearer",
            "scope": "read:me offline_access",
        },
    )
    fake_client = _FakeClient(post_response=post_response)
    monkeypatch.setattr(
        "mxcp.sdk.auth.providers.atlassian.create_mcp_http_client", lambda: fake_client
    )

    adapter = AtlassianProviderAdapter(atlassian_config)
    monkeypatch.setattr(adapter, "_fetch_me", lambda token: asyncio.sleep(0, {"account_id": "acct-1"}))

    grant = await adapter.exchange_code(
        code="code",
        redirect_uri="https://server/atlassian/callback",
        code_verifier=None,
        scopes=["read:me"],
    )
    assert grant.provider_scopes_granted == ["read:me", "offline_access"]


@pytest.mark.asyncio
async def test_exchange_code_invalid_json_raises_provider_error(
    monkeypatch: MonkeyPatch, atlassian_config: AtlassianAuthConfigModel
) -> None:
    post_response = _FakeResponseJsonError(200, {})
    fake_client = _FakeClient(post_response=post_response)
    monkeypatch.setattr(
        "mxcp.sdk.auth.providers.atlassian.create_mcp_http_client", lambda: fake_client
    )

    adapter = AtlassianProviderAdapter(atlassian_config)
    with pytest.raises(ProviderError):
        await adapter.exchange_code(
            code="code",
            redirect_uri="https://server/atlassian/callback",
            code_verifier=None,
            scopes=["read:me"],
        )


@pytest.mark.asyncio
async def test_fetch_user_info_requires_account_id(
    monkeypatch: MonkeyPatch, atlassian_config: AtlassianAuthConfigModel
) -> None:
    adapter = AtlassianProviderAdapter(atlassian_config)
    monkeypatch.setattr(adapter, "_fetch_me", lambda token: asyncio.sleep(0, {"name": "n"}))
    with pytest.raises(ProviderError):
        await adapter.fetch_user_info(access_token="at")


@pytest.mark.asyncio
async def test_revoke_token_propagates_status_code(
    monkeypatch: MonkeyPatch, atlassian_config: AtlassianAuthConfigModel
) -> None:
    post_response = _FakeResponse(500, {})
    fake_client = _FakeClient(post_response=post_response)
    monkeypatch.setattr(
        "mxcp.sdk.auth.providers.atlassian.create_mcp_http_client", lambda: fake_client
    )

    adapter = AtlassianProviderAdapter(atlassian_config)
    with pytest.raises(ProviderError) as exc:
        await adapter.revoke_token(token="t")
    assert exc.value.status_code == 500


def test_callback_path_property_matches_config(atlassian_config: AtlassianAuthConfigModel) -> None:
    adapter = AtlassianProviderAdapter(atlassian_config)
    assert adapter.callback_path == atlassian_config.callback_path

