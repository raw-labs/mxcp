import asyncio
from typing import Any
from urllib.parse import parse_qs, urlsplit

import pytest
from pytest import MonkeyPatch

from mxcp.sdk.auth.contracts import ProviderError
from mxcp.sdk.auth.models import GoogleAuthConfigModel
from mxcp.sdk.auth.providers.google import GoogleProviderAdapter


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict[str, object], text: str = "") -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = text

    def json(self) -> dict[str, object]:
        return self._payload


class _FakeClient:
    def __init__(self, post_response: _FakeResponse) -> None:
        self._post_response = post_response

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
        return _FakeResponse(200, {"sub": "user-1", "email": "user@example.com"})


@pytest.fixture
def google_config() -> GoogleAuthConfigModel:
    return GoogleAuthConfigModel(
        client_id="cid",
        client_secret="secret",
        scope=None,
        callback_path="/google/callback",
        auth_url="https://accounts.google.com/o/oauth2/v2/auth",
        token_url="https://oauth2.googleapis.com/token",
    )


def test_build_authorize_url_includes_required_params(
    google_config: GoogleAuthConfigModel,
) -> None:
    adapter = GoogleProviderAdapter(google_config)
    url = adapter.build_authorize_url(
        redirect_uri="https://server/google/callback",
        state="abc",
        scopes=["openid", "email"],
        code_challenge="cc",
        code_challenge_method="S256",
        extra_params={"foo": "bar"},
    )
    query = parse_qs(urlsplit(url).query)
    assert query["client_id"] == ["cid"]
    assert query["state"] == ["abc"]
    assert query["scope"] == ["openid email"]
    assert query["access_type"] == ["offline"]
    assert query["prompt"] == ["consent"]
    assert query["code_challenge"] == ["cc"]
    assert query["code_challenge_method"] == ["S256"]
    assert query["foo"] == ["bar"]


@pytest.mark.asyncio
async def test_exchange_code_happy_path(
    monkeypatch: MonkeyPatch, google_config: GoogleAuthConfigModel
) -> None:
    post_response = _FakeResponse(
        200,
        {"access_token": "at", "refresh_token": "rt", "expires_in": 3600, "token_type": "Bearer"},
    )
    fake_client = _FakeClient(post_response)
    monkeypatch.setattr(
        "mxcp.sdk.auth.providers.google.create_mcp_http_client", lambda: fake_client
    )

    adapter = GoogleProviderAdapter(google_config)
    monkeypatch.setattr(
        adapter, "_fetch_user_profile", lambda token: asyncio.sleep(0, {"sub": "user-1"})
    )

    grant = await adapter.exchange_code(
        code="code",
        redirect_uri="https://server/google/callback",
        code_verifier=None,
        scopes=["openid"],
    )
    assert grant.access_token == "at"
    assert grant.refresh_token == "rt"
    assert grant.provider_scopes_granted


@pytest.mark.asyncio
async def test_exchange_code_error(
    monkeypatch: MonkeyPatch, google_config: GoogleAuthConfigModel
) -> None:
    post_response = _FakeResponse(400, {"error": "bad"}, text="bad")
    fake_client = _FakeClient(post_response)
    monkeypatch.setattr(
        "mxcp.sdk.auth.providers.google.create_mcp_http_client", lambda: fake_client
    )

    adapter = GoogleProviderAdapter(google_config)
    monkeypatch.setattr(
        adapter, "_fetch_user_profile", lambda token: asyncio.sleep(0, {"sub": "user-1"})
    )

    with pytest.raises(ProviderError):
        await adapter.exchange_code(
            code="code",
            redirect_uri="https://server/google/callback",
            code_verifier=None,
            scopes=["openid"],
        )
