import asyncio
from urllib.parse import parse_qs, urlsplit

import pytest
from pytest import MonkeyPatch

from mxcp.sdk.auth.contracts import ProviderError
from mxcp.sdk.auth.models import SalesforceAuthConfigModel
from mxcp.sdk.auth.providers.salesforce import SalesforceProviderAdapter
from tests.sdk.auth.provider_adapter_testkit import (
    FakeAsyncHttpClient,
    FakeResponse,
    patch_http_client,
)


@pytest.fixture
def salesforce_config() -> SalesforceAuthConfigModel:
    return SalesforceAuthConfigModel(
        client_id="cid",
        client_secret="secret",
        scope="api",
        callback_path="/salesforce/callback",
        auth_url="https://login.salesforce.com/services/oauth2/authorize",
        token_url="https://login.salesforce.com/services/oauth2/token",
    )


def test_build_authorize_url_includes_required_params(
    salesforce_config: SalesforceAuthConfigModel,
) -> None:
    adapter = SalesforceProviderAdapter(salesforce_config)
    url = adapter.build_authorize_url(
        redirect_uri="https://server/salesforce/callback",
        state="abc",
        code_challenge="cc",
        code_challenge_method="S256",
        extra_params={"foo": "bar"},
    )
    query = parse_qs(urlsplit(url).query)
    assert query["response_type"] == ["code"]
    assert query["scope"] == ["api"]


def test_build_authorize_url_uses_configured_scope_when_empty() -> None:
    adapter = SalesforceProviderAdapter(
        SalesforceAuthConfigModel(
            client_id="cid",
            client_secret="secret",
            scope="",
            callback_path="/salesforce/callback",
            auth_url="https://login.salesforce.com/services/oauth2/authorize",
            token_url="https://login.salesforce.com/services/oauth2/token",
        )
    )
    url = adapter.build_authorize_url(
        redirect_uri="https://server/salesforce/callback",
        state="abc",
    )
    query = parse_qs(urlsplit(url).query, keep_blank_values=True)
    assert query["scope"] == [""]


@pytest.mark.asyncio
async def test_exchange_code_happy_path(
    monkeypatch: MonkeyPatch, salesforce_config: SalesforceAuthConfigModel
) -> None:
    post_response = FakeResponse(
        200,
        {"access_token": "at", "refresh_token": "rt", "expires_in": 3600, "token_type": "Bearer"},
    )
    fake_client = FakeAsyncHttpClient(post_response=post_response)
    patch_http_client(
        monkeypatch, "mxcp.sdk.auth.providers.salesforce.create_mcp_http_client", fake_client
    )

    adapter = SalesforceProviderAdapter(salesforce_config)
    monkeypatch.setattr(
        adapter, "_fetch_user_profile", lambda token: asyncio.sleep(0, {"user_id": "user-1"})
    )

    grant = await adapter.exchange_code(
        code="code",
        redirect_uri="https://server/salesforce/callback",
        code_verifier=None,
        scopes=["api"],
    )
    assert grant.access_token == "at"
    assert grant.refresh_token == "rt"
    assert grant.provider_scopes_granted


@pytest.mark.asyncio
async def test_exchange_code_prefers_provider_scope_when_returned(
    monkeypatch: MonkeyPatch, salesforce_config: SalesforceAuthConfigModel
) -> None:
    post_response = FakeResponse(
        200,
        {
            "access_token": "at",
            "refresh_token": "rt",
            "expires_in": 3600,
            "token_type": "Bearer",
            "scope": "api refresh_token",
        },
    )
    fake_client = FakeAsyncHttpClient(post_response=post_response)
    patch_http_client(
        monkeypatch, "mxcp.sdk.auth.providers.salesforce.create_mcp_http_client", fake_client
    )

    adapter = SalesforceProviderAdapter(salesforce_config)
    monkeypatch.setattr(
        adapter, "_fetch_user_profile", lambda token: asyncio.sleep(0, {"user_id": "user-1"})
    )

    grant = await adapter.exchange_code(
        code="code",
        redirect_uri="https://server/salesforce/callback",
        code_verifier=None,
        scopes=["openid"],
    )
    assert grant.provider_scopes_granted == ["api", "refresh_token"]


@pytest.mark.asyncio
async def test_refresh_token_happy_path(
    monkeypatch: MonkeyPatch, salesforce_config: SalesforceAuthConfigModel
) -> None:
    post_response = FakeResponse(
        200,
        {"access_token": "new-at", "refresh_token": "new-rt", "expires_in": 3600},
    )
    fake_client = FakeAsyncHttpClient(post_response=post_response)
    patch_http_client(
        monkeypatch, "mxcp.sdk.auth.providers.salesforce.create_mcp_http_client", fake_client
    )

    adapter = SalesforceProviderAdapter(salesforce_config)
    grant = await adapter.refresh_token(refresh_token="rt", scopes=["api"])
    assert grant.access_token == "new-at"
    assert grant.refresh_token == "new-rt"
    assert grant.provider_scopes_granted == ["api"]


@pytest.mark.asyncio
async def test_fetch_user_info_requires_user_id(
    monkeypatch: MonkeyPatch, salesforce_config: SalesforceAuthConfigModel
) -> None:
    get_response = FakeResponse(200, {"email": "user@example.com"})
    post_response = FakeResponse(200, {})
    fake_client = FakeAsyncHttpClient(
        post_response=post_response,
        default_get_response=get_response,
    )
    patch_http_client(
        monkeypatch, "mxcp.sdk.auth.providers.salesforce.create_mcp_http_client", fake_client
    )
    adapter = SalesforceProviderAdapter(salesforce_config)

    with pytest.raises(ProviderError):
        await adapter.fetch_user_info(access_token="at")


@pytest.mark.asyncio
async def test_fetch_user_info_happy_path(
    monkeypatch: MonkeyPatch, salesforce_config: SalesforceAuthConfigModel
) -> None:
    get_response = FakeResponse(
        200,
        {"user_id": "user-1", "email": "user@example.com", "photos": {"picture": "pic"}},
    )
    post_response = FakeResponse(200, {})
    fake_client = FakeAsyncHttpClient(
        post_response=post_response,
        default_get_response=get_response,
    )
    patch_http_client(
        monkeypatch, "mxcp.sdk.auth.providers.salesforce.create_mcp_http_client", fake_client
    )
    adapter = SalesforceProviderAdapter(salesforce_config)

    user_info = await adapter.fetch_user_info(access_token="at")
    assert user_info.user_id == "user-1"
    assert user_info.email == "user@example.com"
    assert user_info.avatar_url == "pic"
