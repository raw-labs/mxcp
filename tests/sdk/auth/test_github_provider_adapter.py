import asyncio
import base64
from urllib.parse import parse_qs, urlsplit

import pytest
from pytest import MonkeyPatch

from mxcp.sdk.auth.contracts import ProviderError
from mxcp.sdk.auth.models import GitHubAuthConfigModel
from mxcp.sdk.auth.providers.github import GitHubProviderAdapter
from tests.sdk.auth.provider_adapter_testkit import FakeAsyncHttpClient, FakeResponse, patch_http_client


@pytest.fixture
def github_config() -> GitHubAuthConfigModel:
    return GitHubAuthConfigModel(
        client_id="cid",
        client_secret="secret",
        scope=None,
        callback_path="/github/callback",
        auth_url="https://github.com/login/oauth/authorize",
        token_url="https://github.com/login/oauth/access_token",
    )


def test_build_authorize_url_includes_required_params(
    github_config: GitHubAuthConfigModel,
) -> None:
    adapter = GitHubProviderAdapter(github_config)
    url = adapter.build_authorize_url(
        redirect_uri="https://server/github/callback",
        state="abc",
        scopes=["repo", "gist"],
        code_challenge="cc",
        code_challenge_method="S256",
        extra_params={"foo": "bar"},
    )
    query = parse_qs(urlsplit(url).query)
    assert query["response_type"] == ["code"]
    assert query["scope"] == ["repo gist"]


def test_build_authorize_url_falls_back_to_default_scope(
    github_config: GitHubAuthConfigModel,
) -> None:
    adapter = GitHubProviderAdapter(github_config)
    url = adapter.build_authorize_url(
        redirect_uri="https://server/github/callback",
        state="abc",
        scopes=[],
    )
    query = parse_qs(urlsplit(url).query)
    assert query["scope"] == ["user:email"]


@pytest.mark.asyncio
async def test_exchange_code_happy_path(
    monkeypatch: MonkeyPatch, github_config: GitHubAuthConfigModel
) -> None:
    post_response = FakeResponse(
        200,
        {"access_token": "at", "refresh_token": "rt", "scope": "repo,gist", "token_type": "Bearer"},
    )
    fake_client = FakeAsyncHttpClient(post_response=post_response)
    patch_http_client(monkeypatch, "mxcp.sdk.auth.providers.github.create_mcp_http_client", fake_client)

    adapter = GitHubProviderAdapter(github_config)
    monkeypatch.setattr(adapter, "_fetch_user_profile", lambda token: asyncio.sleep(0, {"id": 123}))

    grant = await adapter.exchange_code(
        code="code",
        redirect_uri="https://server/github/callback",
        code_verifier="verifier",
        scopes=["repo"],
    )
    assert grant.access_token == "at"
    assert grant.refresh_token == "rt"
    assert grant.provider_scopes_granted == ["repo", "gist"]


@pytest.mark.asyncio
async def test_refresh_token_happy_path(
    monkeypatch: MonkeyPatch, github_config: GitHubAuthConfigModel
) -> None:
    post_response = FakeResponse(200, {"access_token": "new-at", "scope": "repo"})
    fake_client = FakeAsyncHttpClient(post_response=post_response)
    patch_http_client(monkeypatch, "mxcp.sdk.auth.providers.github.create_mcp_http_client", fake_client)

    adapter = GitHubProviderAdapter(github_config)
    grant = await adapter.refresh_token(refresh_token="rt", scopes=["repo"])
    assert grant.access_token == "new-at"
    assert grant.refresh_token == "rt"
    assert grant.provider_scopes_granted == ["repo"]


@pytest.mark.asyncio
async def test_fetch_user_info_requires_id(
    monkeypatch: MonkeyPatch, github_config: GitHubAuthConfigModel
) -> None:
    get_response = FakeResponse(200, {"login": "user"})
    post_response = FakeResponse(200, {})
    fake_client = FakeAsyncHttpClient(
        post_response=post_response,
        default_get_response=get_response,
    )
    patch_http_client(monkeypatch, "mxcp.sdk.auth.providers.github.create_mcp_http_client", fake_client)
    adapter = GitHubProviderAdapter(github_config)

    with pytest.raises(ProviderError):
        await adapter.fetch_user_info(access_token="at")


@pytest.mark.asyncio
async def test_fetch_user_info_happy_path(
    monkeypatch: MonkeyPatch, github_config: GitHubAuthConfigModel
) -> None:
    get_response = FakeResponse(
        200,
        {
            "id": 123,
            "email": "user@example.com",
            "login": "user",
            "avatar_url": "pic",
            "scope": "repo,gist",
        },
    )
    post_response = FakeResponse(200, {})
    fake_client = FakeAsyncHttpClient(
        post_response=post_response,
        default_get_response=get_response,
    )
    patch_http_client(monkeypatch, "mxcp.sdk.auth.providers.github.create_mcp_http_client", fake_client)
    adapter = GitHubProviderAdapter(github_config)

    user_info = await adapter.fetch_user_info(access_token="at")
    assert user_info.user_id == "123"
    assert user_info.email == "user@example.com"
    assert user_info.username == "user"
    assert user_info.avatar_url == "pic"
    assert user_info.provider_scopes_granted == ["repo", "gist"]


@pytest.mark.asyncio
async def test_fetch_user_info_skips_email_lookup_when_present(
    monkeypatch: MonkeyPatch, github_config: GitHubAuthConfigModel
) -> None:
    get_response = FakeResponse(
        200,
        {
            "id": 123,
            "email": "user@example.com",
            "login": "user",
        },
    )
    post_response = FakeResponse(200, {})
    get_email_response = FakeResponse(500, {"message": "nope"})
    fake_client = FakeAsyncHttpClient(
        post_response=post_response,
        get_responses={"user/emails": get_email_response},
        default_get_response=get_response,
    )
    patch_http_client(monkeypatch, "mxcp.sdk.auth.providers.github.create_mcp_http_client", fake_client)
    adapter = GitHubProviderAdapter(github_config)

    user_info = await adapter.fetch_user_info(access_token="at")
    assert user_info.email == "user@example.com"
    assert fake_client.get_calls_by_route.get("user/emails", 0) == 0


@pytest.mark.asyncio
async def test_fetch_user_info_falls_back_to_email_endpoint(
    monkeypatch: MonkeyPatch, github_config: GitHubAuthConfigModel
) -> None:
    get_response = FakeResponse(
        200,
        {
            "id": 123,
            "email": None,
            "login": "user",
        },
    )
    post_response = FakeResponse(200, {})
    get_email_response = FakeResponse(
        200,
        [
            {"email": "primary@example.com", "primary": True, "verified": True},
            {"email": "other@example.com", "primary": False, "verified": True},
        ],
    )
    fake_client = FakeAsyncHttpClient(
        post_response=post_response,
        get_responses={"user/emails": get_email_response},
        default_get_response=get_response,
    )
    patch_http_client(monkeypatch, "mxcp.sdk.auth.providers.github.create_mcp_http_client", fake_client)
    adapter = GitHubProviderAdapter(github_config)

    user_info = await adapter.fetch_user_info(access_token="at")
    assert user_info.email == "primary@example.com"
    assert fake_client.get_calls_by_route.get("user/emails", 0) == 1


@pytest.mark.asyncio
async def test_fetch_user_info_email_endpoint_unauthorized(
    monkeypatch: MonkeyPatch, github_config: GitHubAuthConfigModel
) -> None:
    get_response = FakeResponse(
        200,
        {
            "id": 123,
            "email": None,
            "login": "user",
        },
    )
    post_response = FakeResponse(200, {})
    get_email_response = FakeResponse(401, {"message": "Unauthorized"})
    fake_client = FakeAsyncHttpClient(
        post_response=post_response,
        get_responses={"user/emails": get_email_response},
        default_get_response=get_response,
    )
    patch_http_client(monkeypatch, "mxcp.sdk.auth.providers.github.create_mcp_http_client", fake_client)
    adapter = GitHubProviderAdapter(github_config)

    user_info = await adapter.fetch_user_info(access_token="at")
    assert user_info.email is None
    assert fake_client.get_calls_by_route.get("user/emails", 0) == 1
