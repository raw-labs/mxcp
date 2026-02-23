from __future__ import annotations

from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest
import respx
from cryptography.fernet import Fernet
from mcp.server.auth.provider import AuthorizationParams
from mcp.shared.auth import OAuthClientInformationFull
from pydantic import AnyUrl

from mxcp.sdk.auth.auth_service import AuthService
from mxcp.sdk.auth.models import OIDCAuthConfigModel
from mxcp.sdk.auth.providers.oidc import OIDCProviderAdapter
from mxcp.sdk.auth.session_manager import SessionManager
from mxcp.sdk.auth.storage import SqliteTokenStore
from mxcp.server.core.auth.issuer_provider import IssuerOAuthAuthorizationServer


CONFIG_URL = "http://oidc.test/.well-known/openid-configuration"


def _discovery_payload() -> dict[str, str]:
    return {
        "issuer": "http://oidc.test",
        "authorization_endpoint": "http://oidc.test/authorize",
        "token_endpoint": "http://oidc.test/token",
        "userinfo_endpoint": "http://oidc.test/userinfo",
    }


@respx.mock
@pytest.mark.asyncio
async def test_oidc_issuer_flow(tmp_path: Path) -> None:
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
    userinfo = respx.get("http://oidc.test/userinfo").respond(200, json={"sub": "user-1"})

    adapter = OIDCProviderAdapter(
        OIDCAuthConfigModel(
            config_url=CONFIG_URL,
            client_id="client-id",
            client_secret="client-secret",
            scope="openid email",
            callback_path="/oidc/callback",
        )
    )
    await adapter.ensure_ready()

    db_path = tmp_path / "oauth.db"
    token_store = SqliteTokenStore(db_path, encryption_key=Fernet.generate_key())
    session_manager = SessionManager(token_store)
    auth_service = AuthService(
        provider_adapter=adapter,
        session_manager=session_manager,
        callback_url="https://server/oidc/callback",
    )

    client = OAuthClientInformationFull(
        client_id="client-1",
        client_secret="secret",
        redirect_uris=[AnyUrl("https://client/app")],
        grant_types=["authorization_code"],
        response_types=["code"],
        scope="openid email",
    )
    assert client.client_id is not None

    server = IssuerOAuthAuthorizationServer(
        auth_service=auth_service,
        session_manager=session_manager,
        clients={client.client_id: client},
    )
    await server.initialize()

    try:
        params = AuthorizationParams(
            state="client-state",
            scopes=["openid"],
            code_challenge="test_challenge",
            redirect_uri=AnyUrl("https://client/app"),
            redirect_uri_provided_explicitly=True,
        )

        authorize_url = await server.authorize(client, params)
        state = parse_qs(urlparse(authorize_url).query)["state"][0]

        redirect_uri = await server.handle_callback("TEST_CODE", state)
        redirect_query = parse_qs(urlparse(redirect_uri).query)
        code = redirect_query["code"][0]

        loaded = await server.load_authorization_code(client, code)
        assert loaded is not None

        token = await server.exchange_authorization_code(client, loaded)
        assert token.access_token
        assert token.refresh_token
    finally:
        await server.close()

    assert discovery.called
    assert token_route.called
    assert userinfo.called

    token_request = token_route.calls[0].request
    form = parse_qs(token_request.content.decode())
    assert form["grant_type"] == ["authorization_code"]
    assert form["code"] == ["TEST_CODE"]
    assert form["client_id"] == ["client-id"]
    assert form["client_secret"] == ["client-secret"]
    assert form["redirect_uri"] == ["https://server/oidc/callback"]
    assert "code_verifier" in form

    userinfo_request = userinfo.calls[0].request
    assert userinfo_request.headers.get("authorization") == "Bearer mock-at"
