from __future__ import annotations

from urllib.parse import parse_qs

import pytest
import respx

from mxcp.sdk.auth.contracts import ProviderError
from mxcp.sdk.auth.models import OIDCAuthConfigModel
from mxcp.sdk.auth.providers.oidc import OIDCProviderAdapter


CONFIG_URL = "http://oidc.test/.well-known/openid-configuration"


def _discovery_payload(*, include_userinfo: bool = True) -> dict[str, str]:
    payload = {
        "issuer": "http://oidc.test",
        "authorization_endpoint": "http://oidc.test/authorize",
        "token_endpoint": "http://oidc.test/token",
    }
    if include_userinfo:
        payload["userinfo_endpoint"] = "http://oidc.test/userinfo"
    return payload


def _make_adapter() -> OIDCProviderAdapter:
    return OIDCProviderAdapter(
        OIDCAuthConfigModel(
            config_url=CONFIG_URL,
            client_id="client-id",
            client_secret="client-secret",
            scope="openid email",
            callback_path="/oidc/callback",
        )
    )


@respx.mock
@pytest.mark.asyncio
async def test_oidc_adapter_happy_path() -> None:
    discovery = respx.get(CONFIG_URL).respond(200, json=_discovery_payload())
    token_route = respx.post("http://oidc.test/token").respond(
        200,
        json={
            "access_token": "mock-at",
            "refresh_token": "mock-rt",
            "expires_in": 3600,
            "scope": "openid email",
            "token_type": "Bearer",
        },
    )
    userinfo = respx.get("http://oidc.test/userinfo").respond(
        200, json={"sub": "user-1", "email": "user@example.com"}
    )

    adapter = _make_adapter()
    await adapter.ensure_ready()
    grant = await adapter.exchange_code(
        code="TEST_CODE",
        redirect_uri="http://mxcp.test/callback",
        code_verifier="verifier",
        scopes=["openid"],
    )
    user = await adapter.fetch_user_info(access_token=grant.access_token)

    assert discovery.called
    assert token_route.called
    assert userinfo.called

    assert adapter.auth_url == "http://oidc.test/authorize"
    assert adapter.token_url == "http://oidc.test/token"
    assert adapter.userinfo_url == "http://oidc.test/userinfo"
    assert adapter.pkce_methods_supported == ["S256"]

    assert grant.access_token == "mock-at"
    assert grant.refresh_token == "mock-rt"
    assert grant.provider_scopes_granted == ["openid", "email"]
    assert grant.token_type == "Bearer"
    assert user.user_id == "user-1"
    assert user.email == "user@example.com"

    token_request = token_route.calls[0].request
    form = parse_qs(token_request.content.decode())
    assert form["grant_type"] == ["authorization_code"]
    assert form["code"] == ["TEST_CODE"]
    assert form["client_id"] == ["client-id"]
    assert form["client_secret"] == ["client-secret"]
    assert form["redirect_uri"] == ["http://mxcp.test/callback"]
    assert form["code_verifier"] == ["verifier"]
    assert token_request.headers.get("content-type", "").startswith(
        "application/x-www-form-urlencoded"
    )

    userinfo_request = userinfo.calls[0].request
    assert userinfo_request.headers.get("authorization") == "Bearer mock-at"


@respx.mock
@pytest.mark.asyncio
async def test_oidc_adapter_discovery_non_200() -> None:
    discovery = respx.get(CONFIG_URL).respond(500, json={"error": "boom"})

    adapter = _make_adapter()
    with pytest.raises(ProviderError) as excinfo:
        await adapter.ensure_ready()

    assert discovery.called
    assert excinfo.value.error == "server_error"


@respx.mock
@pytest.mark.asyncio
async def test_oidc_adapter_discovery_missing_userinfo() -> None:
    discovery = respx.get(CONFIG_URL).respond(200, json=_discovery_payload(include_userinfo=False))

    adapter = _make_adapter()
    with pytest.raises(ProviderError) as excinfo:
        await adapter.ensure_ready()

    assert discovery.called
    assert excinfo.value.error == "server_error"


@respx.mock
@pytest.mark.asyncio
async def test_oidc_adapter_token_error() -> None:
    discovery = respx.get(CONFIG_URL).respond(200, json=_discovery_payload())
    token_route = respx.post("http://oidc.test/token").respond(400, json={"error": "invalid_grant"})

    adapter = _make_adapter()
    await adapter.ensure_ready()
    with pytest.raises(ProviderError) as excinfo:
        await adapter.exchange_code(
            code="TEST_CODE",
            redirect_uri="http://mxcp.test/callback",
            scopes=["openid"],
        )

    assert discovery.called
    assert token_route.called
    assert excinfo.value.error == "invalid_grant"


@respx.mock
@pytest.mark.asyncio
async def test_oidc_adapter_userinfo_missing_sub() -> None:
    discovery = respx.get(CONFIG_URL).respond(200, json=_discovery_payload())
    respx.post("http://oidc.test/token").respond(
        200,
        json={
            "access_token": "mock-at",
            "expires_in": 3600,
            "scope": "openid",
            "token_type": "Bearer",
        },
    )
    userinfo = respx.get("http://oidc.test/userinfo").respond(200, json={"email": "x"})

    adapter = _make_adapter()
    await adapter.ensure_ready()
    grant = await adapter.exchange_code(
        code="TEST_CODE",
        redirect_uri="http://mxcp.test/callback",
        scopes=["openid"],
    )

    with pytest.raises(ProviderError) as excinfo:
        await adapter.fetch_user_info(access_token=grant.access_token)

    assert discovery.called
    assert userinfo.called
    assert excinfo.value.error == "invalid_token"
