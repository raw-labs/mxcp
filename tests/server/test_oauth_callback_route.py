"""
Tests for the OAuth provider callback route behavior.

These tests focus on the *HTTP callback endpoint* that an upstream provider (e.g., Google)
redirects the user-agent to after the user approves/denies access.

Key scenario we want to preserve:
- On success (code+state), the callback redirects the browser back to the MCP client's
  redirect_uri with an authorization code.

Key scenario we want to improve:
- On provider error (error+state), the callback should *also* redirect the browser back
  to the MCP client's redirect_uri with standard OAuth error query parameters.

We intentionally do NOT boot a real HTTP server. Instead we:
- instantiate RAWMCP in-process
- register the callback route
- build the ASGI app via FastMCP's streamable-http app factory
- exercise the route via TestClient
"""

from __future__ import annotations

import asyncio
import contextlib
import os
from collections.abc import Iterator, Mapping, Sequence
from pathlib import Path

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from mxcp.sdk.auth.auth_service import AuthService
from mxcp.sdk.auth.contracts import GrantResult, UserInfo
from mxcp.sdk.auth.session_manager import SessionManager
from mxcp.sdk.auth.storage import SqliteTokenStore
from mxcp.server.core.auth.issuer_provider import IssuerOAuthAuthorizationServer
from mxcp.server.interfaces.server.mcp import RAWMCP

IssuerModeServerFixture = tuple[RAWMCP, SqliteTokenStore, SessionManager]


class _ProviderAdapterStub:
    """Minimal ProviderAdapter stub.

    The callback error redirect tests do not exercise any provider network calls,
    but AuthService requires a provider adapter instance.
    """

    provider_name = "stub"
    pkce_methods_supported: Sequence[str] = []

    def build_authorize_url(
        self,
        *,
        redirect_uri: str,
        state: str,
        scopes: Sequence[str],
        code_challenge: str | None = None,
        code_challenge_method: str | None = None,
        extra_params: Mapping[str, str] | None = None,
    ) -> str:  # pragma: no cover
        raise AssertionError("build_authorize_url should not be called in these tests")

    async def exchange_code(
        self,
        *,
        code: str,
        redirect_uri: str,
        code_verifier: str | None = None,
        scopes: Sequence[str] | None = None,
    ) -> GrantResult:  # pragma: no cover
        raise AssertionError("exchange_code should not be called in these tests")

    async def refresh_token(
        self, *, refresh_token: str, scopes: Sequence[str] | None = None
    ) -> GrantResult:  # pragma: no cover
        raise AssertionError("refresh_token should not be called in these tests")

    async def fetch_user_info(self, *, access_token: str) -> UserInfo:  # pragma: no cover
        raise AssertionError("fetch_user_info should not be called in these tests")


@pytest.fixture(scope="session", autouse=True)
def set_mxcp_config_env() -> None:
    # Use the server test repository config to allow RAWMCP initialization.
    os.environ["MXCP_CONFIG"] = str(Path(__file__).parent / "fixtures" / "mcp" / "mxcp-config.yml")


@pytest.fixture
def mcp_repo_path() -> Path:
    """Path to the server test repository used by other server tests."""
    return Path(__file__).parent / "fixtures" / "mcp"


@pytest.fixture(autouse=True)
def change_to_mcp_repo(mcp_repo_path: Path) -> Iterator[None]:
    """RAWMCP loads site config relative to the repo; mirror existing server tests."""
    original_dir = os.getcwd()
    os.chdir(mcp_repo_path)
    try:
        yield
    finally:
        os.chdir(original_dir)


@pytest.fixture
def issuer_mode_server(
    tmp_path: Path, mcp_repo_path: Path
) -> Iterator[tuple[RAWMCP, SqliteTokenStore, SessionManager]]:
    """Create an in-process RAWMCP instance with issuer-mode auth objects injected."""
    server = RAWMCP(
        site_config_path=mcp_repo_path,
        stateless_http=True,
        json_response=True,
        host="localhost",
        port=8000,
    )

    # Use a temp sqlite database so tests do not touch ~/.mxcp/oauth.db.
    token_store = SqliteTokenStore(tmp_path / "oauth.db", encryption_key=Fernet.generate_key())
    asyncio.run(token_store.initialize())
    session_manager = SessionManager(token_store)

    # AuthService is required by IssuerOAuthAuthorizationServer. For these tests we only
    # use it for redirect validation; no provider calls should occur.
    auth_service = AuthService(
        provider_adapter=_ProviderAdapterStub(),
        session_manager=session_manager,
        callback_url="http://localhost/oauth/callback",
    )
    oauth_server = IssuerOAuthAuthorizationServer(
        auth_service=auth_service,
        session_manager=session_manager,
        clients={},
    )

    # Inject issuer-mode pieces so _register_oauth_routes() will register the callback.
    server.oauth_server = oauth_server
    server.session_manager = session_manager
    server.auth_service = auth_service
    server.provider_adapter = type(
        "_CallbackPathOnly",
        (),
        {"callback_path": "/oauth/callback"},
    )()

    # Register the callback route on the FastMCP instance.
    server._register_oauth_routes()

    try:
        yield server, token_store, session_manager
    finally:
        with contextlib.suppress(Exception):
            asyncio.run(token_store.close())
        with contextlib.suppress(Exception):
            asyncio.run(server.shutdown())


def test_callback_provider_error_with_state_redirects_back_to_client(
    issuer_mode_server: IssuerModeServerFixture,
) -> None:
    """Simulate a provider redirecting back to our callback with an OAuth error.

    In real life, this is what happens when the user denies consent (or another
    provider-side issue occurs):

      Google -> (browser) -> GET /oauth/callback?error=access_denied&state=...

    Our callback handler should not leave the browser on a JSON 400 page. Instead,
    it should redirect the browser back to the MCP client's redirect_uri, carrying
    the error parameters so the client app can display a friendly message and
    resume control of the flow.
    """

    server, token_store, session_manager = issuer_mode_server

    # Persist an MXCP-generated state that records the *client* redirect URI and its
    # original client_state. This is the only safe source of the redirect target.
    state_record = asyncio.run(
        session_manager.create_state(
            client_id="client_1",
            redirect_uri="https://client.example/cb",
            code_challenge=None,
            code_challenge_method=None,
            client_state="orig_state",
            scopes=[],
        )
    )

    app = server.mcp.streamable_http_app()
    client = TestClient(app)

    resp = client.get(
        "/oauth/callback",
        params={
            "error": "access_denied",
            "error_description": "Denied by user",
            "state": state_record.state,
        },
        follow_redirects=False,
    )

    # Desired behavior: 3xx redirect back to the stored redirect_uri with error params.
    assert resp.status_code in {301, 302, 303, 307, 308}
    location = resp.headers["location"]
    assert location.startswith("https://client.example/cb")
    assert "error=access_denied" in location
    assert "error_description=Denied+by+user" in location
    assert "state=orig_state" in location


def test_callback_provider_error_without_state_returns_json_400(
    issuer_mode_server: IssuerModeServerFixture,
) -> None:
    """If we cannot safely determine the client redirect target, we keep JSON 400.

    Without state, redirecting would risk an open redirect or leaking errors to the
    wrong client. The current contract is a JSON 400 in this case.
    """

    server, _token_store, _session_manager = issuer_mode_server
    app = server.mcp.streamable_http_app()
    client = TestClient(app)

    resp = client.get(
        "/oauth/callback",
        params={"error": "access_denied", "error_description": "Denied by user"},
        follow_redirects=False,
    )
    assert resp.status_code == 400
    assert resp.json()["error"] == "access_denied"


def test_callback_missing_code_or_state_returns_invalid_request_json_400(
    issuer_mode_server: IssuerModeServerFixture,
) -> None:
    """Missing required query parameters should return a safe JSON error."""

    server, _token_store, _session_manager = issuer_mode_server
    app = server.mcp.streamable_http_app()
    client = TestClient(app)

    resp = client.get("/oauth/callback", follow_redirects=False)
    assert resp.status_code == 400
    assert resp.json()["error"] == "invalid_request"
