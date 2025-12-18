from pathlib import Path
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
async def test_end_to_end_authorize_to_token(tmp_path: Path) -> None:
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
    assert client.client_id is not None

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


@pytest.mark.asyncio
async def test_authorize_ignores_client_requested_scopes(tmp_path: Path) -> None:
    """Issuer-mode must not forward client-requested OAuth scopes upstream.

    The `scope` parameter on the MXCP authorize request is treated as client input
    and must not influence what the upstream provider is asked for.
    """
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
    assert client.client_id is not None

    server = IssuerOAuthAuthorizationServer(
        auth_service=auth_service,
        session_manager=session_manager,
        clients={client.client_id: client},
    )

    params = AuthorizationParams(
        state=None,
        scopes=["evil.scope"],
        code_challenge="test_challenge",
        redirect_uri=AnyUrl("https://client/app"),
        redirect_uri_provided_explicitly=True,
    )

    authorize_url = await server.authorize(client, params)
    # DummyProviderAdapter encodes the scopes passed into the authorize URL. We must
    # not see client-provided scopes (nor the client-registered scope) forwarded.
    assert "evil.scope" not in authorize_url
    assert "dummy.read" not in authorize_url


@pytest.mark.asyncio
async def test_dcr_client_persists_across_restart(tmp_path: Path) -> None:
    """DCR-registered clients must survive process restarts (TokenStore-backed)."""
    db_path = tmp_path / "oauth.db"

    # First "process": register a DCR client and persist it.
    adapter1 = DummyProviderAdapter()
    token_store1 = SqliteTokenStore(db_path, allow_plaintext_tokens=True)
    session_manager1 = SessionManager(token_store1)
    auth_service1 = AuthService(
        provider_adapter=adapter1,
        session_manager=session_manager1,
        callback_url="https://server/callback",
    )
    server1 = IssuerOAuthAuthorizationServer(
        auth_service=auth_service1,
        session_manager=session_manager1,
    )

    dcr_client = OAuthClientInformationFull(
        client_id="dcr-client-1",
        client_secret="secret",
        redirect_uris=[AnyUrl("https://client/app")],
        grant_types=["authorization_code"],
        response_types=["code"],
        scope="client-metadata-scope",
        client_name="DCR Client",
    )
    await server1.register_client(dcr_client)
    await token_store1.close()

    # Second "process": new TokenStore + SessionManager, should be able to load client.
    adapter2 = DummyProviderAdapter()
    token_store2 = SqliteTokenStore(db_path, allow_plaintext_tokens=True)
    session_manager2 = SessionManager(token_store2)
    auth_service2 = AuthService(
        provider_adapter=adapter2,
        session_manager=session_manager2,
        callback_url="https://server/callback",
    )
    server2 = IssuerOAuthAuthorizationServer(
        auth_service=auth_service2,
        session_manager=session_manager2,
    )

    loaded = await server2.get_client("dcr-client-1")
    assert loaded is not None
    assert loaded.client_id == "dcr-client-1"
    assert loaded.client_secret == "secret"
    assert loaded.token_endpoint_auth_method == "client_secret_post"

    # Verify the loaded client can complete authorize().
    params = AuthorizationParams(
        state=None,
        scopes=["ignored"],
        code_challenge="test_challenge",
        redirect_uri=AnyUrl("https://client/app"),
        redirect_uri_provided_explicitly=True,
    )
    authorize_url = await server2.authorize(loaded, params)
    assert "state=" in authorize_url
    await token_store2.close()


@pytest.mark.asyncio
async def test_config_clients_are_bootstrapped_into_token_store(tmp_path: Path) -> None:
    """Configured clients passed in constructor are persisted and retrievable."""
    adapter = DummyProviderAdapter()
    token_store = SqliteTokenStore(tmp_path / "oauth.db", allow_plaintext_tokens=True)
    session_manager = SessionManager(token_store)
    auth_service = AuthService(
        provider_adapter=adapter,
        session_manager=session_manager,
        callback_url="https://server/callback",
    )

    configured = OAuthClientInformationFull(
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
        clients={configured.client_id or "": configured},
    )

    loaded = await server.get_client("client-1")
    assert loaded is not None
    assert loaded.client_id == "client-1"
    assert loaded.token_endpoint_auth_method == "client_secret_post"
    await token_store.close()
