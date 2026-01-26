import asyncio
import time

import pytest
import pytest_asyncio

from mxcp.sdk.auth.contracts import UserInfo
from mxcp.sdk.auth.session_manager import SessionManager
from mxcp.sdk.auth.storage import TokenStore


@pytest_asyncio.fixture
async def session_manager(token_store: TokenStore) -> SessionManager:
    return SessionManager(token_store)


@pytest.mark.asyncio
async def test_state_create_and_consume_once(session_manager: SessionManager) -> None:
    # State can be consumed exactly once; carries PKCE and scopes.
    record = await session_manager.create_state(
        client_id="client-1",
        redirect_uri="http://localhost/redirect",
        code_challenge="challenge",
        code_challenge_method="S256",
        scopes=["a", "b"],
    )

    loaded = await session_manager.consume_state(record.state)
    assert loaded is not None
    assert loaded.state == record.state
    assert loaded.code_challenge == "challenge"
    assert loaded.scopes == ["a", "b"]
    assert await session_manager.consume_state(record.state) is None


@pytest.mark.asyncio
async def test_state_expiry_respected(session_manager: SessionManager) -> None:
    # Expired state cannot be consumed.
    record = await session_manager.create_state(
        client_id=None,
        redirect_uri=None,
        code_challenge=None,
        code_challenge_method=None,
        scopes=None,
        ttl_seconds=0,
    )

    await asyncio.sleep(0.1)
    assert await session_manager.consume_state(record.state) is None


@pytest.mark.asyncio
async def test_auth_code_create_and_consume_once(session_manager: SessionManager) -> None:
    # Auth code can be consumed exactly once.
    code = await session_manager.create_auth_code(
        session_id="session-1",
        client_id="client-1",
        redirect_uri="http://localhost/redirect",
        code_challenge=None,
        code_challenge_method=None,
        scopes=["x"],
    )

    loaded = await session_manager.load_auth_code(code.code)
    assert loaded is not None
    assert loaded.session_id == "session-1"
    assert loaded.scopes == ["x"]
    assert await session_manager.try_delete_auth_code(code.code) is True
    assert await session_manager.try_delete_auth_code(code.code) is False
    assert await session_manager.load_auth_code(code.code) is None


@pytest.mark.asyncio
async def test_issue_get_and_revoke_session(session_manager: SessionManager) -> None:
    # Session issuance, retrieval by access token, and revocation.
    user_info = UserInfo(
        provider="dummy",
        user_id="u1",
        username="u1",
        provider_scopes_granted=["s1"],
    )
    session = await session_manager.issue_session(
        provider="dummy",
        user_info=user_info,
        provider_access_token="provider_token",
        provider_refresh_token="provider_refresh",
        provider_expires_at=time.time() + 300,
        scopes=["s1"],
    )

    loaded = await session_manager.get_session(session.access_token)
    assert loaded is not None
    assert loaded.session_id == session.session_id
    assert loaded.provider_access_token == "provider_token"
    assert loaded.scopes == ["s1"]

    await session_manager.revoke_session(session.access_token)
    assert await session_manager.get_session(session.access_token) is None


@pytest.mark.asyncio
async def test_cleanup_expired_session(session_manager: SessionManager) -> None:
    # Cleanup removes expired sessions.
    session = await session_manager.issue_session(
        provider="dummy",
        user_info=UserInfo(provider="dummy", user_id="u", username="u"),
        provider_access_token=None,
        provider_refresh_token=None,
        provider_expires_at=None,
        scopes=None,
        access_token_ttl_seconds=0,
    )

    await asyncio.sleep(0.05)
    counts = await session_manager.cleanup()
    assert counts["sessions"] >= 1
    assert await session_manager.get_session(session.access_token) is None


@pytest.mark.asyncio
async def test_issue_and_load_session(session_manager: SessionManager) -> None:
    # Session issuance and lookup by access token, with provider metadata.
    now = time.time()
    user_info = UserInfo(
        provider="dummy",
        user_id="u1",
        username="u1",
        provider_scopes_granted=["a"],
    )

    session = await session_manager.issue_session(
        provider="dummy",
        user_info=user_info,
        provider_access_token="prov-token",
        provider_refresh_token="prov-refresh",
        provider_expires_at=now + 100,
        scopes=["a"],
    )

    loaded = await session_manager.get_session(session.access_token)
    assert loaded is not None
    assert loaded.session_id == session.session_id
    assert loaded.provider_access_token == "prov-token"
    assert loaded.user_info.user_id == "u1"


@pytest.mark.asyncio
async def test_expired_session_returns_none(session_manager: SessionManager) -> None:
    # Expired sessions are not returned.
    user_info = UserInfo(provider="dummy", user_id="expired", username="expired")
    session = await session_manager.issue_session(
        provider="dummy",
        user_info=user_info,
        provider_access_token=None,
        provider_refresh_token=None,
        provider_expires_at=None,
        scopes=None,
        access_token_ttl_seconds=-1,
    )

    assert await session_manager.get_session(session.access_token) is None


@pytest.mark.asyncio
async def test_cleanup_clears_expired_items(session_manager: SessionManager) -> None:
    # Cleanup removes expired states/auth codes.
    await session_manager.create_state(
        client_id=None,
        redirect_uri=None,
        code_challenge=None,
        code_challenge_method=None,
        scopes=None,
        ttl_seconds=-1,
    )
    await session_manager.create_auth_code(
        session_id="cleanup-session",
        client_id="client-1",
        redirect_uri=None,
        code_challenge=None,
        code_challenge_method=None,
        scopes=None,
        ttl_seconds=-1,
    )

    counts = await session_manager.cleanup()
    assert counts["states"] >= 1
    assert counts["auth_codes"] >= 1


@pytest.mark.asyncio
async def test_auth_code_load_and_delete(session_manager: SessionManager) -> None:
    # Auth code can be loaded without consuming, then explicitly deleted.
    code = await session_manager.create_auth_code(
        session_id="session-load",
        client_id="client-1",
        redirect_uri=None,
        code_challenge="challenge",
        code_challenge_method="S256",
        scopes=["y"],
    )

    loaded = await session_manager.load_auth_code(code.code)
    assert loaded is not None and loaded.code_challenge == "challenge"

    # Load should not consume
    loaded_again = await session_manager.load_auth_code(code.code)
    assert loaded_again is not None

    await session_manager.delete_auth_code(code.code)
    assert await session_manager.load_auth_code(code.code) is None
