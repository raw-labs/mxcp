import asyncio
from urllib.parse import parse_qs, urlsplit

import pytest
from pytest import MonkeyPatch

from mxcp.sdk.auth.contracts import ProviderError
from mxcp.sdk.auth.models import GoogleAuthConfigModel
from mxcp.sdk.auth.providers.google import GoogleProviderAdapter
from tests.sdk.auth.provider_adapter_testkit import (
    FakeAsyncHttpClient,
    FakeResponse,
    patch_http_client,
)


@pytest.fixture
def google_config() -> GoogleAuthConfigModel:
    return GoogleAuthConfigModel(
        client_id="cid",
        client_secret="secret",
        scope="openid email",
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
    assert query["scope"] == ["openid email"]
    assert query["access_type"] == ["offline"]
    assert query["prompt"] == ["consent"]


@pytest.mark.asyncio
async def test_exchange_code_happy_path(
    monkeypatch: MonkeyPatch, google_config: GoogleAuthConfigModel
) -> None:
    post_response = FakeResponse(
        200,
        {"access_token": "at", "refresh_token": "rt", "expires_in": 3600, "token_type": "Bearer"},
    )
    fake_client = FakeAsyncHttpClient(post_response=post_response)
    patch_http_client(
        monkeypatch, "mxcp.sdk.auth.providers.google.create_mcp_http_client", fake_client
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
async def test_exchange_code_prefers_provider_scope_when_returned(
    monkeypatch: MonkeyPatch, google_config: GoogleAuthConfigModel
) -> None:
    post_response = FakeResponse(
        200,
        {
            "access_token": "at",
            "refresh_token": "rt",
            "expires_in": 3600,
            "token_type": "Bearer",
            "scope": "profile email",
        },
    )
    fake_client = FakeAsyncHttpClient(post_response=post_response)
    patch_http_client(
        monkeypatch, "mxcp.sdk.auth.providers.google.create_mcp_http_client", fake_client
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
    assert grant.provider_scopes_granted == ["profile", "email"]


@pytest.mark.asyncio
async def test_exchange_code_error(
    monkeypatch: MonkeyPatch, google_config: GoogleAuthConfigModel
) -> None:
    post_response = FakeResponse(400, {"error": "bad"}, text="bad")
    fake_client = FakeAsyncHttpClient(post_response=post_response)
    patch_http_client(
        monkeypatch, "mxcp.sdk.auth.providers.google.create_mcp_http_client", fake_client
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
