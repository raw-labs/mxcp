import asyncio
from urllib.parse import parse_qs, urlsplit

import pytest
from pytest import MonkeyPatch

from mxcp.sdk.auth.contracts import ProviderError
from mxcp.sdk.auth.models import AtlassianAuthConfigModel
from mxcp.sdk.auth.providers.atlassian import AtlassianProviderAdapter
from tests.sdk.auth.provider_adapter_testkit import (
    FakeAsyncHttpClient,
    FakeResponse,
    patch_http_client,
)


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


def test_build_authorize_url_includes_required_params(
    atlassian_config: AtlassianAuthConfigModel,
) -> None:
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
    assert query["prompt"] == ["consent"]
    assert query["scope"] == ["read:me offline_access"]


@pytest.mark.asyncio
async def test_exchange_code_happy_path(
    monkeypatch: MonkeyPatch, atlassian_config: AtlassianAuthConfigModel
) -> None:
    post_response = FakeResponse(
        200,
        {"access_token": "at", "refresh_token": "rt", "expires_in": 3600, "token_type": "Bearer"},
    )
    fake_client = FakeAsyncHttpClient(post_response=post_response)
    patch_http_client(
        monkeypatch, "mxcp.sdk.auth.providers.atlassian.create_mcp_http_client", fake_client
    )

    adapter = AtlassianProviderAdapter(atlassian_config)
    monkeypatch.setattr(
        adapter, "_fetch_me", lambda token: asyncio.sleep(0, {"account_id": "acct-1"})
    )

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
    post_response = FakeResponse(
        200,
        {
            "access_token": "at",
            "refresh_token": "rt",
            "expires_in": 3600,
            "token_type": "Bearer",
            "scope": "read:me offline_access",
        },
    )
    fake_client = FakeAsyncHttpClient(post_response=post_response)
    patch_http_client(
        monkeypatch, "mxcp.sdk.auth.providers.atlassian.create_mcp_http_client", fake_client
    )

    adapter = AtlassianProviderAdapter(atlassian_config)
    monkeypatch.setattr(
        adapter, "_fetch_me", lambda token: asyncio.sleep(0, {"account_id": "acct-1"})
    )

    grant = await adapter.exchange_code(
        code="code",
        redirect_uri="https://server/atlassian/callback",
        code_verifier=None,
        scopes=["read:me"],
    )
    assert grant.provider_scopes_granted == ["read:me", "offline_access"]


@pytest.mark.asyncio
async def test_fetch_user_info_requires_account_id(
    monkeypatch: MonkeyPatch, atlassian_config: AtlassianAuthConfigModel
) -> None:
    adapter = AtlassianProviderAdapter(atlassian_config)
    monkeypatch.setattr(adapter, "_fetch_me", lambda token: asyncio.sleep(0, {"name": "n"}))
    with pytest.raises(ProviderError):
        await adapter.fetch_user_info(access_token="at")
