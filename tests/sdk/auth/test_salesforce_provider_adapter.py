import asyncio
from typing import Any
from urllib.parse import parse_qs, urlsplit

import pytest
from pytest import MonkeyPatch

from mxcp.sdk.auth.contracts import ProviderError
from mxcp.sdk.auth.models import SalesforceAuthConfigModel
from mxcp.sdk.auth.providers.salesforce import SalesforceProviderAdapter


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
        self._get_response = get_response or _FakeResponse(200, {"user_id": "user-1"})

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
def salesforce_config() -> SalesforceAuthConfigModel:
    return SalesforceAuthConfigModel(
        client_id="cid",
        client_secret="secret",
        scope=None,
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
        scopes=["api"],
        code_challenge="cc",
        code_challenge_method="S256",
        extra_params={"foo": "bar"},
    )
    query = parse_qs(urlsplit(url).query)
    assert query["client_id"] == ["cid"]
    assert query["state"] == ["abc"]
    assert query["response_type"] == ["code"]
    assert query["scope"] == ["api"]
    assert query["code_challenge"] == ["cc"]
    assert query["code_challenge_method"] == ["S256"]
    assert query["foo"] == ["bar"]


def test_build_authorize_url_falls_back_to_default_scope(
    salesforce_config: SalesforceAuthConfigModel,
) -> None:
    adapter = SalesforceProviderAdapter(salesforce_config)
    url = adapter.build_authorize_url(
        redirect_uri="https://server/salesforce/callback",
        state="abc",
        scopes=[],
    )
    query = parse_qs(urlsplit(url).query)
    assert query["scope"] == ["api refresh_token openid profile email"]


@pytest.mark.asyncio
async def test_exchange_code_happy_path(
    monkeypatch: MonkeyPatch, salesforce_config: SalesforceAuthConfigModel
) -> None:
    post_response = _FakeResponse(
        200,
        {"access_token": "at", "refresh_token": "rt", "expires_in": 3600, "token_type": "Bearer"},
    )
    fake_client = _FakeClient(post_response=post_response)
    monkeypatch.setattr(
        "mxcp.sdk.auth.providers.salesforce.create_mcp_http_client", lambda: fake_client
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
    post_response = _FakeResponse(
        200,
        {
            "access_token": "at",
            "refresh_token": "rt",
            "expires_in": 3600,
            "token_type": "Bearer",
            "scope": "api refresh_token",
        },
    )
    fake_client = _FakeClient(post_response=post_response)
    monkeypatch.setattr(
        "mxcp.sdk.auth.providers.salesforce.create_mcp_http_client", lambda: fake_client
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
async def test_exchange_code_invalid_json_raises_provider_error(
    monkeypatch: MonkeyPatch, salesforce_config: SalesforceAuthConfigModel
) -> None:
    post_response = _FakeResponseJsonError(200, {})
    fake_client = _FakeClient(post_response=post_response)
    monkeypatch.setattr(
        "mxcp.sdk.auth.providers.salesforce.create_mcp_http_client", lambda: fake_client
    )

    adapter = SalesforceProviderAdapter(salesforce_config)
    with pytest.raises(ProviderError):
        await adapter.exchange_code(
            code="code",
            redirect_uri="https://server/salesforce/callback",
            code_verifier=None,
            scopes=["openid"],
        )


@pytest.mark.asyncio
async def test_refresh_token_happy_path(
    monkeypatch: MonkeyPatch, salesforce_config: SalesforceAuthConfigModel
) -> None:
    post_response = _FakeResponse(
        200,
        {"access_token": "new-at", "refresh_token": "new-rt", "expires_in": 3600},
    )
    fake_client = _FakeClient(post_response=post_response)
    monkeypatch.setattr(
        "mxcp.sdk.auth.providers.salesforce.create_mcp_http_client", lambda: fake_client
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
    get_response = _FakeResponse(200, {"email": "user@example.com"})
    post_response = _FakeResponse(200, {})
    fake_client = _FakeClient(post_response=post_response, get_response=get_response)
    monkeypatch.setattr(
        "mxcp.sdk.auth.providers.salesforce.create_mcp_http_client", lambda: fake_client
    )
    adapter = SalesforceProviderAdapter(salesforce_config)

    with pytest.raises(ProviderError):
        await adapter.fetch_user_info(access_token="at")


@pytest.mark.asyncio
async def test_fetch_user_info_happy_path(
    monkeypatch: MonkeyPatch, salesforce_config: SalesforceAuthConfigModel
) -> None:
    get_response = _FakeResponse(
        200,
        {"user_id": "user-1", "email": "user@example.com", "photos": {"picture": "pic"}},
    )
    post_response = _FakeResponse(200, {})
    fake_client = _FakeClient(post_response=post_response, get_response=get_response)
    monkeypatch.setattr(
        "mxcp.sdk.auth.providers.salesforce.create_mcp_http_client", lambda: fake_client
    )
    adapter = SalesforceProviderAdapter(salesforce_config)

    user_info = await adapter.fetch_user_info(access_token="at")
    assert user_info.user_id == "user-1"
    assert user_info.email == "user@example.com"
    assert user_info.avatar_url == "pic"


@pytest.mark.asyncio
async def test_revoke_token_propagates_status_code(
    monkeypatch: MonkeyPatch, salesforce_config: SalesforceAuthConfigModel
) -> None:
    post_response = _FakeResponse(500, {})
    fake_client = _FakeClient(post_response=post_response)
    monkeypatch.setattr(
        "mxcp.sdk.auth.providers.salesforce.create_mcp_http_client", lambda: fake_client
    )

    adapter = SalesforceProviderAdapter(salesforce_config)
    with pytest.raises(ProviderError) as exc:
        await adapter.revoke_token(token="t")
    assert exc.value.status_code == 500


def test_callback_path_property_matches_config(
    salesforce_config: SalesforceAuthConfigModel,
) -> None:
    adapter = SalesforceProviderAdapter(salesforce_config)
    assert adapter.callback_path == salesforce_config.callback_path
