"""Contract tests for ProviderAdapter implementations.

These tests assert a small set of invariants that must hold for every provider
adapter, without duplicating the same assertions in every provider-specific file.
Provider-specific behavior remains tested in the per-provider modules.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable
from urllib.parse import parse_qs, urlsplit

import pytest
from pytest import MonkeyPatch

from mxcp.sdk.auth.contracts import ProviderError
from mxcp.sdk.auth.models import (
    AtlassianAuthConfigModel,
    GitHubAuthConfigModel,
    GoogleAuthConfigModel,
    KeycloakAuthConfigModel,
    SalesforceAuthConfigModel,
)
from mxcp.sdk.auth.providers.atlassian import AtlassianProviderAdapter
from mxcp.sdk.auth.providers.github import GitHubProviderAdapter
from mxcp.sdk.auth.providers.google import GoogleProviderAdapter
from mxcp.sdk.auth.providers.keycloak import KeycloakProviderAdapter
from mxcp.sdk.auth.providers.salesforce import SalesforceProviderAdapter
from tests.sdk.auth.provider_adapter_testkit import (
    FakeAsyncHttpClient,
    FakeResponse,
    FakeResponseJsonError,
    patch_http_client,
)


@dataclass(frozen=True)
class _ProviderCase:
    name: str
    adapter_factory: Callable[[], object]
    create_client_path: str
    callback_path: str


def _cases() -> list[_ProviderCase]:
    return [
        _ProviderCase(
            name="google",
            adapter_factory=lambda: GoogleProviderAdapter(
                GoogleAuthConfigModel(
                    client_id="cid",
                    client_secret="secret",
                    scope="openid email",
                    callback_path="/google/callback",
                    auth_url="https://accounts.google.com/o/oauth2/v2/auth",
                    token_url="https://oauth2.googleapis.com/token",
                )
            ),
            create_client_path="mxcp.sdk.auth.providers.google.create_mcp_http_client",
            callback_path="/google/callback",
        ),
        _ProviderCase(
            name="github",
            adapter_factory=lambda: GitHubProviderAdapter(
                GitHubAuthConfigModel(
                    client_id="cid",
                    client_secret="secret",
                    scope=None,
                    callback_path="/github/callback",
                    auth_url="https://github.com/login/oauth/authorize",
                    token_url="https://github.com/login/oauth/access_token",
                )
            ),
            create_client_path="mxcp.sdk.auth.providers.github.create_mcp_http_client",
            callback_path="/github/callback",
        ),
        _ProviderCase(
            name="atlassian",
            adapter_factory=lambda: AtlassianProviderAdapter(
                AtlassianAuthConfigModel(
                    client_id="cid",
                    client_secret="secret",
                    scope="read:me offline_access",
                    callback_path="/atlassian/callback",
                    auth_url="https://auth.atlassian.com/authorize",
                    token_url="https://auth.atlassian.com/oauth/token",
                )
            ),
            create_client_path="mxcp.sdk.auth.providers.atlassian.create_mcp_http_client",
            callback_path="/atlassian/callback",
        ),
        _ProviderCase(
            name="keycloak",
            adapter_factory=lambda: KeycloakProviderAdapter(
                KeycloakAuthConfigModel(
                    client_id="cid",
                    client_secret="secret",
                    realm="master",
                    server_url="https://kc.example.com",
                    scope=None,
                    callback_path="/keycloak/callback",
                )
            ),
            create_client_path="mxcp.sdk.auth.providers.keycloak.create_mcp_http_client",
            callback_path="/keycloak/callback",
        ),
        _ProviderCase(
            name="salesforce",
            adapter_factory=lambda: SalesforceProviderAdapter(
                SalesforceAuthConfigModel(
                    client_id="cid",
                    client_secret="secret",
                    scope=None,
                    callback_path="/salesforce/callback",
                    auth_url="https://login.salesforce.com/services/oauth2/authorize",
                    token_url="https://login.salesforce.com/services/oauth2/token",
                )
            ),
            create_client_path="mxcp.sdk.auth.providers.salesforce.create_mcp_http_client",
            callback_path="/salesforce/callback",
        ),
    ]


@pytest.mark.parametrize("case", _cases(), ids=lambda c: c.name)
def test_callback_path_property_matches_config(case: _ProviderCase) -> None:
    adapter = case.adapter_factory()
    assert getattr(adapter, "callback_path") == case.callback_path


@pytest.mark.parametrize("case", _cases(), ids=lambda c: c.name)
def test_build_authorize_url_includes_boundary_params(case: _ProviderCase) -> None:
    adapter = case.adapter_factory()
    url = adapter.build_authorize_url(
        redirect_uri="https://server/callback",
        state="STATE",
        scopes=["s1"],
        code_challenge="cc",
        code_challenge_method="S256",
        extra_params={"foo": "bar"},
    )
    query = parse_qs(urlsplit(url).query)
    assert query["state"] == ["STATE"]
    assert query["code_challenge"] == ["cc"]
    assert query["code_challenge_method"] == ["S256"]
    assert query["foo"] == ["bar"]


@pytest.mark.parametrize("case", _cases(), ids=lambda c: c.name)
@pytest.mark.asyncio
async def test_exchange_code_invalid_json_raises_provider_error(
    case: _ProviderCase, monkeypatch: MonkeyPatch
) -> None:
    fake_client = FakeAsyncHttpClient(post_response=FakeResponseJsonError(200, {}))
    patch_http_client(monkeypatch, case.create_client_path, fake_client)

    adapter = case.adapter_factory()
    with pytest.raises(ProviderError):
        await adapter.exchange_code(
            code="code",
            redirect_uri="https://server/callback",
            code_verifier=None,
            scopes=["s1"],
        )


@pytest.mark.parametrize("case", _cases(), ids=lambda c: c.name)
@pytest.mark.asyncio
async def test_revoke_token_propagates_status_code(
    case: _ProviderCase, monkeypatch: MonkeyPatch
) -> None:
    fake_client = FakeAsyncHttpClient(post_response=FakeResponse(500, {}))
    patch_http_client(monkeypatch, case.create_client_path, fake_client)

    adapter = case.adapter_factory()
    with pytest.raises(ProviderError) as exc:
        await adapter.revoke_token(token="t")
    assert exc.value.status_code == 500

