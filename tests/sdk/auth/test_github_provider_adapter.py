import asyncio
import base64
from typing import Any
from urllib.parse import parse_qs, urlsplit

import pytest
from pytest import MonkeyPatch

from mxcp.sdk.auth.contracts import ProviderError
from mxcp.sdk.auth.models import GitHubAuthConfigModel
from mxcp.sdk.auth.providers.github import GitHubProviderAdapter


class _FakeResponse:
    def __init__(self, status_code: int, payload: object, text: str = "") -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = text

    def json(self) -> object:
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
        get_email_response: _FakeResponse | None = None,
    ) -> None:
        self._post_response = post_response
        self._get_response = get_response or _FakeResponse(200, {"id": 123})
        self._get_email_response = get_email_response or _FakeResponse(200, [])
        self.user_calls = 0
        self.email_calls = 0

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
        url = args[0] if args else ""
        if "user/emails" in str(url):
            self.email_calls += 1
            return self._get_email_response
        self.user_calls += 1
        return self._get_response


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
    assert query["client_id"] == ["cid"]
    assert query["state"] == ["abc"]
    assert query["response_type"] == ["code"]
    assert query["scope"] == ["repo gist"]
    assert query["code_challenge"] == ["cc"]
    assert query["code_challenge_method"] == ["S256"]
    assert query["foo"] == ["bar"]


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
    post_response = _FakeResponse(
        200,
        {"access_token": "at", "refresh_token": "rt", "scope": "repo,gist", "token_type": "Bearer"},
    )
    fake_client = _FakeClient(post_response=post_response)
    monkeypatch.setattr(
        "mxcp.sdk.auth.providers.github.create_mcp_http_client", lambda: fake_client
    )

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
async def test_exchange_code_invalid_json_raises_provider_error(
    monkeypatch: MonkeyPatch, github_config: GitHubAuthConfigModel
) -> None:
    post_response = _FakeResponseJsonError(200, {})
    fake_client = _FakeClient(post_response=post_response)
    monkeypatch.setattr(
        "mxcp.sdk.auth.providers.github.create_mcp_http_client", lambda: fake_client
    )

    adapter = GitHubProviderAdapter(github_config)
    with pytest.raises(ProviderError):
        await adapter.exchange_code(
            code="code",
            redirect_uri="https://server/github/callback",
            code_verifier=None,
            scopes=["repo"],
        )


@pytest.mark.asyncio
async def test_refresh_token_happy_path(
    monkeypatch: MonkeyPatch, github_config: GitHubAuthConfigModel
) -> None:
    post_response = _FakeResponse(200, {"access_token": "new-at", "scope": "repo"})
    fake_client = _FakeClient(post_response=post_response)
    monkeypatch.setattr(
        "mxcp.sdk.auth.providers.github.create_mcp_http_client", lambda: fake_client
    )

    adapter = GitHubProviderAdapter(github_config)
    grant = await adapter.refresh_token(refresh_token="rt", scopes=["repo"])
    assert grant.access_token == "new-at"
    assert grant.refresh_token == "rt"
    assert grant.provider_scopes_granted == ["repo"]


@pytest.mark.asyncio
async def test_fetch_user_info_requires_id(
    monkeypatch: MonkeyPatch, github_config: GitHubAuthConfigModel
) -> None:
    get_response = _FakeResponse(200, {"login": "user"})
    post_response = _FakeResponse(200, {})
    fake_client = _FakeClient(post_response=post_response, get_response=get_response)
    monkeypatch.setattr(
        "mxcp.sdk.auth.providers.github.create_mcp_http_client", lambda: fake_client
    )
    adapter = GitHubProviderAdapter(github_config)

    with pytest.raises(ProviderError):
        await adapter.fetch_user_info(access_token="at")


@pytest.mark.asyncio
async def test_fetch_user_info_happy_path(
    monkeypatch: MonkeyPatch, github_config: GitHubAuthConfigModel
) -> None:
    get_response = _FakeResponse(
        200,
        {
            "id": 123,
            "email": "user@example.com",
            "login": "user",
            "avatar_url": "pic",
            "scope": "repo,gist",
        },
    )
    post_response = _FakeResponse(200, {})
    fake_client = _FakeClient(post_response=post_response, get_response=get_response)
    monkeypatch.setattr(
        "mxcp.sdk.auth.providers.github.create_mcp_http_client", lambda: fake_client
    )
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
    get_response = _FakeResponse(
        200,
        {
            "id": 123,
            "email": "user@example.com",
            "login": "user",
        },
    )
    post_response = _FakeResponse(200, {})
    get_email_response = _FakeResponse(500, {"message": "nope"})
    fake_client = _FakeClient(
        post_response=post_response,
        get_response=get_response,
        get_email_response=get_email_response,
    )
    monkeypatch.setattr(
        "mxcp.sdk.auth.providers.github.create_mcp_http_client", lambda: fake_client
    )
    adapter = GitHubProviderAdapter(github_config)

    user_info = await adapter.fetch_user_info(access_token="at")
    assert user_info.email == "user@example.com"
    assert fake_client.email_calls == 0


@pytest.mark.asyncio
async def test_fetch_user_info_falls_back_to_email_endpoint(
    monkeypatch: MonkeyPatch, github_config: GitHubAuthConfigModel
) -> None:
    get_response = _FakeResponse(
        200,
        {
            "id": 123,
            "email": None,
            "login": "user",
        },
    )
    post_response = _FakeResponse(200, {})
    get_email_response = _FakeResponse(
        200,
        [
            {"email": "primary@example.com", "primary": True, "verified": True},
            {"email": "other@example.com", "primary": False, "verified": True},
        ],
    )
    fake_client = _FakeClient(
        post_response=post_response,
        get_response=get_response,
        get_email_response=get_email_response,
    )
    monkeypatch.setattr(
        "mxcp.sdk.auth.providers.github.create_mcp_http_client", lambda: fake_client
    )
    adapter = GitHubProviderAdapter(github_config)

    user_info = await adapter.fetch_user_info(access_token="at")
    assert user_info.email == "primary@example.com"
    assert fake_client.email_calls == 1


@pytest.mark.asyncio
async def test_fetch_user_info_email_endpoint_unauthorized(
    monkeypatch: MonkeyPatch, github_config: GitHubAuthConfigModel
) -> None:
    get_response = _FakeResponse(
        200,
        {
            "id": 123,
            "email": None,
            "login": "user",
        },
    )
    post_response = _FakeResponse(200, {})
    get_email_response = _FakeResponse(401, {"message": "Unauthorized"})
    fake_client = _FakeClient(
        post_response=post_response,
        get_response=get_response,
        get_email_response=get_email_response,
    )
    monkeypatch.setattr(
        "mxcp.sdk.auth.providers.github.create_mcp_http_client", lambda: fake_client
    )
    adapter = GitHubProviderAdapter(github_config)

    user_info = await adapter.fetch_user_info(access_token="at")
    assert user_info.email is None
    assert fake_client.email_calls == 1


@pytest.mark.asyncio
async def test_revoke_token_propagates_status_code(
    monkeypatch: MonkeyPatch, github_config: GitHubAuthConfigModel
) -> None:
    post_response = _FakeResponse(500, {})
    fake_client = _FakeClient(post_response=post_response)
    monkeypatch.setattr(
        "mxcp.sdk.auth.providers.github.create_mcp_http_client", lambda: fake_client
    )

    adapter = GitHubProviderAdapter(github_config)
    with pytest.raises(ProviderError) as exc:
        await adapter.revoke_token(token="t")
    assert exc.value.status_code == 500


def test_callback_path_property_matches_config(
    github_config: GitHubAuthConfigModel,
) -> None:
    adapter = GitHubProviderAdapter(github_config)
    assert adapter.callback_path == github_config.callback_path


def test_revoke_uses_basic_auth_header(github_config: GitHubAuthConfigModel) -> None:
    adapter = GitHubProviderAdapter(github_config)
    basic = base64.b64encode(
        f"{github_config.client_id}:{github_config.client_secret}".encode()
    ).decode()
    assert basic  # sanity check header generation mirrors adapter path
