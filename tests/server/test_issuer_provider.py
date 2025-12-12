from urllib.parse import parse_qs, urlparse

import pytest
from mcp.server.auth.provider import AuthorizationParams
from mcp.shared.auth import OAuthClientInformationFull
from pydantic import AnyUrl

from mxcp.sdk.auth.auth_service import AuthService
from mxcp.sdk.auth.providers.dummy import DummyProviderAdapter
from mxcp.sdk.auth.session_manager import SessionManager
from mxcp.sdk.auth.storage import SqliteTokenStore
from mxcp.server.core.auth.issuer_provider import IssuerOAuthAuthorizationServer


@pytest.mark.asyncio
async def test_end_to_end_authorize_to_token(tmp_path) -> None:
    adapter = DummyProviderAdapter()
    token_store = SqliteTokenStore(tmp_path / "oauth.db", allow_plaintext_tokens=True)
    session_manager = SessionManager(token_store)
    auth_service = AuthService(
        provider_adapter=adapter,
        session_manager=session_manager,
        callback_url="https://server/callback",
    )

    client = OAuthClientInformationFull(
        client_id="client-1",
        client_secret="secret",
        redirect_uris=[AnyUrl("https://client/app")],
        grant_types=["authorization_code"],
        response_types=["code"],
        scope="dummy.read",
    )

    server = IssuerOAuthAuthorizationServer(
        auth_service=auth_service,
        session_manager=session_manager,
        clients={client.client_id: client},
    )

    params = AuthorizationParams(
        state=None,
        scopes=["dummy.read"],
        # MCP requires PKCE for authorization_code flow; provide any non-empty challenge.
        code_challenge="test_challenge",
        redirect_uri=AnyUrl("https://client/app"),
        redirect_uri_provided_explicitly=True,
    )

    authorize_url = await server.authorize(client, params)
    parsed = urlparse(authorize_url)
    state = parse_qs(parsed.query)["state"][0]

    redirect_uri = await server.handle_callback("TEST_CODE_OK", state)
    redirect_query = parse_qs(urlparse(redirect_uri).query)
    # If the MCP client did not provide an original state, we must not leak the
    # internal MXCP/IdP state back to the client.
    assert "state" not in redirect_query
    code = redirect_query["code"][0]

    loaded = await server.load_authorization_code(client, code)
    assert loaded is not None

    token = await server.exchange_authorization_code(client, loaded)
    assert token.access_token
    assert token.refresh_token

    access = await server.load_access_token(token.access_token)
    assert access is not None

    await server.revoke_token(access)
    revoked = await server.load_access_token(token.access_token)
    assert revoked is None
