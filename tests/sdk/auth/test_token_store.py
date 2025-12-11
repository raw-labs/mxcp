import logging
import sqlite3
import time
from pathlib import Path

import pytest
from cryptography.fernet import Fernet

from mxcp.sdk.auth.contracts import UserInfo
from mxcp.sdk.auth.storage import AuthCodeRecord, SqliteTokenStore, StateRecord, StoredSession


def _db_row(db_path: Path, query: str) -> sqlite3.Row | None:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(query).fetchone()
        return row
    finally:
        conn.close()


@pytest.mark.asyncio
async def test_state_round_trip(token_store) -> None:
    # States persist and can be consumed exactly once.
    store = token_store

    now = time.time()
    record = StateRecord(
        state="state-1",
        client_id="client-1",
        redirect_uri="http://localhost/callback",
        code_challenge="challenge",
        code_challenge_method="S256",
        scopes=["a", "b"],
        expires_at=now + 5,
        created_at=now,
    )

    await store.store_state(record)
    loaded = await store.consume_state("state-1")
    assert loaded == record
    assert await store.consume_state("state-1") is None


@pytest.mark.asyncio
async def test_state_expiry(token_store) -> None:
    # Expired states are rejected and removed.
    store = token_store

    expired = StateRecord(
        state="expired",
        client_id=None,
        redirect_uri=None,
        code_challenge=None,
        code_challenge_method=None,
        scopes=None,
        expires_at=time.time() - 1,
        created_at=time.time() - 2,
    )
    await store.store_state(expired)
    assert await store.consume_state("expired") is None


@pytest.mark.asyncio
async def test_auth_code_round_trip(token_store) -> None:
    # Auth codes persist and can be consumed exactly once.
    store = token_store

    now = time.time()
    code = AuthCodeRecord(
        code="auth-code-1",
        session_id="session-1",
        redirect_uri="http://localhost/redirect",
        scopes=["x", "y"],
        expires_at=now + 30,
        created_at=now,
    )
    await store.store_auth_code(code)
    loaded = await store.load_auth_code("auth-code-1")
    assert loaded == code
    assert await store.try_delete_auth_code("auth-code-1") is True
    # Second delete should fail (already deleted)
    assert await store.try_delete_auth_code("auth-code-1") is False
    assert await store.load_auth_code("auth-code-1") is None


@pytest.mark.asyncio
async def test_session_store_and_load_with_encryption(token_store) -> None:
    # Sessions persist with encryption/hashing and round-trip correctly.
    store = token_store

    now = time.time()
    user_info = UserInfo(
        provider="dummy",
        user_id="user-1",
        username="user-1",
        email="user@example.com",
        provider_scopes_granted=["s1"],
    )
    session = StoredSession(
        session_id="session-1",
        provider="dummy",
        user_info=user_info,
        access_token="mcp_token",
        refresh_token="mcp_refresh",
        provider_access_token="provider_token",
        provider_refresh_token="provider_refresh",
        provider_expires_at=now + 300,
        expires_at=now + 600,
        created_at=now,
        issued_at=now,
        scopes=["s1"],
    )

    await store.store_session(session)
    loaded = await store.load_session_by_token("mcp_token")

    assert loaded is not None
    assert loaded == session
    assert loaded.access_token == "mcp_token"
    assert loaded.refresh_token == "mcp_refresh"
    assert loaded.provider_access_token == "provider_token"
    assert loaded.provider_refresh_token == "provider_refresh"
    assert loaded.user_info.user_id == "user-1"

    row = _db_row(
        store.db_path, "SELECT access_token_encrypted, refresh_token_encrypted FROM sessions"
    )
    assert row is not None
    assert row["access_token_encrypted"] != "mcp_token"
    assert row["refresh_token_encrypted"] != "mcp_refresh"


@pytest.mark.asyncio
async def test_session_scopes_are_preserved(token_store) -> None:
    # Session scopes should survive a reload and not be replaced by provider scopes.
    store = token_store

    now = time.time()
    user_info = UserInfo(
        provider="dummy",
        user_id="user-1",
        username="user-1",
        provider_scopes_granted=["provider.scope"],
    )
    session = StoredSession(
        session_id="session-1",
        provider="dummy",
        user_info=user_info,
        access_token="mxcp_token",
        refresh_token="mxcp_refresh",
        provider_access_token="provider_token",
        provider_refresh_token="provider_refresh",
        provider_expires_at=now + 300,
        expires_at=now + 600,
        created_at=now,
        issued_at=now,
        scopes=["mxcp.read"],
    )

    await store.store_session(session)
    loaded = await store.load_session_by_token("mxcp_token")

    assert loaded is not None
    assert loaded.scopes == ["mxcp.read"]
    assert loaded.user_info.provider_scopes_granted == ["provider.scope"]


@pytest.mark.asyncio
async def test_store_isolation_for_multiple_records(token_store) -> None:
    # Multiple states, auth codes, and sessions remain isolated and retrievable.
    store = token_store

    now = time.time()

    # States
    state1 = StateRecord(
        state="state-1",
        client_id="c1",
        redirect_uri=None,
        code_challenge=None,
        code_challenge_method=None,
        scopes=["s1"],
        expires_at=now + 60,
        created_at=now,
    )
    state2 = StateRecord(
        state="state-2",
        client_id="c2",
        redirect_uri=None,
        code_challenge=None,
        code_challenge_method=None,
        scopes=["s2"],
        expires_at=now + 60,
        created_at=now,
    )
    await store.store_state(state1)
    await store.store_state(state2)
    assert await store.consume_state("state-1") == state1
    assert await store.consume_state("state-1") is None
    assert await store.consume_state("state-2") == state2

    # Auth codes
    code1 = AuthCodeRecord(
        code="code-1",
        session_id="s1",
        redirect_uri=None,
        scopes=["a"],
        expires_at=now + 60,
        created_at=now,
    )
    code2 = AuthCodeRecord(
        code="code-2",
        session_id="s2",
        redirect_uri=None,
        scopes=["b"],
        expires_at=now + 60,
        created_at=now,
    )
    await store.store_auth_code(code1)
    await store.store_auth_code(code2)
    assert await store.load_auth_code("code-1") == code1
    assert await store.try_delete_auth_code("code-1") is True
    assert await store.try_delete_auth_code("code-1") is False
    assert await store.load_auth_code("code-1") is None
    assert await store.load_auth_code("code-2") == code2
    assert await store.try_delete_auth_code("code-2") is True

    # Sessions
    user_info_a = UserInfo(
        provider="dummy", user_id="u1", username="u1", provider_scopes_granted=["pa"]
    )
    user_info_b = UserInfo(
        provider="dummy", user_id="u2", username="u2", provider_scopes_granted=["pb"]
    )
    session_a = StoredSession(
        session_id="session-a",
        provider="dummy",
        user_info=user_info_a,
        access_token="token-a",
        refresh_token="refresh-a",
        provider_access_token="provider-a",
        provider_refresh_token=None,
        provider_expires_at=now + 300,
        expires_at=now + 400,
        created_at=now,
        issued_at=now,
        scopes=["mxcp.a"],
    )
    session_b = StoredSession(
        session_id="session-b",
        provider="dummy",
        user_info=user_info_b,
        access_token="token-b",
        refresh_token=None,
        provider_access_token=None,
        provider_refresh_token="provider-refresh-b",
        provider_expires_at=now + 500,
        expires_at=now + 600,
        created_at=now,
        issued_at=now,
        scopes=["mxcp.b"],
    )

    await store.store_session(session_a)
    await store.store_session(session_b)

    loaded_a = await store.load_session_by_token("token-a")
    loaded_b = await store.load_session_by_token("token-b")
    assert (
        loaded_a is not None
        and loaded_a.session_id == "session-a"
        and loaded_a.scopes == ["mxcp.a"]
    )
    assert (
        loaded_b is not None
        and loaded_b.session_id == "session-b"
        and loaded_b.scopes == ["mxcp.b"]
    )

    loaded_a_by_id = await store.load_session_by_id("session-a")
    loaded_b_by_id = await store.load_session_by_id("session-b")
    assert loaded_a_by_id is not None and loaded_a_by_id.access_token == "token-a"
    assert loaded_b_by_id is not None and loaded_b_by_id.access_token == "token-b"


@pytest.mark.asyncio
async def test_session_store_requires_encryption_key_by_default(tmp_path: Path) -> None:
    # Storing tokens without a key should fail unless explicitly allowed.
    db_path = tmp_path / "auth.db"
    store = SqliteTokenStore(db_path)
    await store.initialize()

    now = time.time()
    user_info = UserInfo(provider="dummy", user_id="u", username="u")
    session = StoredSession(
        session_id="session-plain",
        provider="dummy",
        user_info=user_info,
        access_token="plain_token",
        refresh_token=None,
        provider_access_token=None,
        provider_refresh_token=None,
        provider_expires_at=None,
        expires_at=now + 10,
        created_at=now,
        issued_at=now,
        scopes=None,
    )

    with pytest.raises(ValueError, match="Token encryption key is required"):
        await store.store_session(session)

    await store.close()


@pytest.mark.asyncio
async def test_session_store_plaintext_opt_in(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    # Plaintext storage is only allowed with explicit opt-in and logs a warning.
    caplog.set_level(logging.WARNING)
    db_path = tmp_path / "auth.db"
    store = SqliteTokenStore(db_path, allow_plaintext_tokens=True)
    await store.initialize()

    now = time.time()
    user_info = UserInfo(provider="dummy", user_id="u", username="u")
    session = StoredSession(
        session_id="session-plain",
        provider="dummy",
        user_info=user_info,
        access_token="plain_token",
        refresh_token="plain_refresh",
        provider_access_token="provider_plain",
        provider_refresh_token=None,
        provider_expires_at=None,
        expires_at=now + 10,
        created_at=now,
        issued_at=now,
        scopes=None,
    )

    await store.store_session(session)
    loaded = await store.load_session_by_token(session.access_token)

    assert loaded is not None
    assert loaded.access_token == "plain_token"
    assert loaded.refresh_token == "plain_refresh"
    assert loaded.provider_access_token == "provider_plain"

    row = _db_row(
        db_path,
        "SELECT access_token_encrypted, refresh_token_encrypted, provider_access_token FROM sessions",
    )
    assert row is not None
    assert row["access_token_encrypted"] == "plain_token"
    assert row["refresh_token_encrypted"] == "plain_refresh"
    assert row["provider_access_token"] == "provider_plain"
    assert any("plaintext" in message for message in caplog.messages)

    await store.close()


@pytest.mark.asyncio
async def test_auth_code_load_and_delete(token_store) -> None:
    # Auth codes can be loaded without consumption and deleted explicitly.
    store = token_store

    now = time.time()
    code = AuthCodeRecord(
        code="loadable-code",
        session_id="session-1",
        redirect_uri=None,
        code_challenge="challenge",
        code_challenge_method="S256",
        scopes=["x"],
        expires_at=now + 30,
        created_at=now,
    )

    await store.store_auth_code(code)

    loaded = await store.load_auth_code("loadable-code")
    assert loaded is not None
    # Load should not consume
    loaded_again = await store.load_auth_code("loadable-code")
    assert loaded_again is not None

    await store.delete_auth_code("loadable-code")
    assert await store.load_auth_code("loadable-code") is None


@pytest.mark.asyncio
async def test_auth_code_load_expires_on_read(token_store) -> None:
    # Expired codes are dropped on load.
    store = token_store
    now = time.time()
    code = AuthCodeRecord(
        code="expired-code",
        session_id="session-1",
        redirect_uri=None,
        code_challenge=None,
        code_challenge_method=None,
        scopes=None,
        expires_at=now - 1,
        created_at=now - 2,
    )

    await store.store_auth_code(code)
    assert await store.load_auth_code("expired-code") is None
    # Ensure it was deleted
    assert await store.load_auth_code("expired-code") is None


@pytest.mark.asyncio
async def test_session_store_accepts_string_fernet_key(tmp_path: Path) -> None:
    # String form of Fernet key should be accepted for ergonomics.
    key_str = Fernet.generate_key().decode("utf-8")
    db_path = tmp_path / "auth.db"
    store = SqliteTokenStore(db_path, encryption_key=key_str)
    await store.initialize()

    now = time.time()
    user_info = UserInfo(provider="dummy", user_id="u", username="u")
    session = StoredSession(
        session_id="session-str-key",
        provider="dummy",
        user_info=user_info,
        access_token="plain_token",
        refresh_token=None,
        provider_access_token=None,
        provider_refresh_token=None,
        provider_expires_at=None,
        expires_at=now + 10,
        created_at=now,
        issued_at=now,
        scopes=None,
    )

    await store.store_session(session)
    loaded = await store.load_session_by_token(session.access_token)

    assert loaded is not None and loaded.session_id == "session-str-key"
    await store.close()


@pytest.mark.asyncio
async def test_store_can_reinitialize_after_close(tmp_path: Path) -> None:
    # Store can be closed and reinitialized for reuse.
    db_path = tmp_path / "auth.db"
    key = Fernet.generate_key()
    store = SqliteTokenStore(db_path, encryption_key=key)

    await store.initialize()
    await store.close()

    await store.initialize()
    now = time.time()
    state = StateRecord(
        state="reinit",
        client_id=None,
        redirect_uri=None,
        code_challenge=None,
        code_challenge_method=None,
        scopes=None,
        expires_at=now + 5,
        created_at=now,
    )
    await store.store_state(state)
    assert await store.consume_state("reinit") is not None

    await store.close()


@pytest.mark.asyncio
async def test_session_expiry_and_cleanup(tmp_path: Path) -> None:
    # Expired sessions are cleaned up and not returned.
    db_path = tmp_path / "auth.db"
    store = SqliteTokenStore(db_path, encryption_key=Fernet.generate_key())
    await store.initialize()

    now = time.time()
    session = StoredSession(
        session_id="session-expired",
        provider="dummy",
        user_info=UserInfo(provider="dummy", user_id="u", username="u"),
        access_token="expired_token",
        refresh_token=None,
        provider_access_token=None,
        provider_refresh_token=None,
        provider_expires_at=None,
        expires_at=now - 1,
        created_at=now - 10,
        issued_at=now - 10,
        scopes=None,
    )
    await store.store_session(session)

    counts = await store.cleanup_expired()
    assert counts["sessions"] >= 1
    assert await store.load_session_by_token("expired_token") is None

    await store.close()


@pytest.mark.asyncio
async def test_load_session_by_refresh_token(token_store) -> None:
    # Sessions can be loaded by refresh token.
    store = token_store

    now = time.time()
    user_info = UserInfo(provider="dummy", user_id="u", username="u")
    session = StoredSession(
        session_id="session-refresh",
        provider="dummy",
        user_info=user_info,
        access_token="access_token_1",
        refresh_token="refresh_token_1",
        provider_access_token=None,
        provider_refresh_token=None,
        provider_expires_at=None,
        expires_at=now + 600,
        created_at=now,
        issued_at=now,
        scopes=["read"],
    )

    await store.store_session(session)
    loaded = await store.load_session_by_refresh_token("refresh_token_1")

    assert loaded is not None
    assert loaded.session_id == "session-refresh"
    assert loaded.access_token == "access_token_1"
    assert loaded.refresh_token == "refresh_token_1"


@pytest.mark.asyncio
async def test_load_session_by_refresh_token_not_found(token_store) -> None:
    # Unknown refresh token returns None.
    store = token_store

    loaded = await store.load_session_by_refresh_token("nonexistent_refresh")
    assert loaded is None


@pytest.mark.asyncio
async def test_load_session_by_refresh_token_no_refresh_token(token_store) -> None:
    # Session without refresh token cannot be found by refresh token.
    store = token_store

    now = time.time()
    user_info = UserInfo(provider="dummy", user_id="u", username="u")
    session = StoredSession(
        session_id="session-no-refresh",
        provider="dummy",
        user_info=user_info,
        access_token="access_only",
        refresh_token=None,
        provider_access_token=None,
        provider_refresh_token=None,
        provider_expires_at=None,
        expires_at=now + 600,
        created_at=now,
        issued_at=now,
        scopes=None,
    )

    await store.store_session(session)

    # Cannot find by None refresh token
    loaded = await store.load_session_by_refresh_token("access_only")
    assert loaded is None


@pytest.mark.asyncio
async def test_load_session_by_refresh_token_expired(tmp_path: Path) -> None:
    # Expired sessions are not returned when loading by refresh token.
    db_path = tmp_path / "auth.db"
    store = SqliteTokenStore(db_path, encryption_key=Fernet.generate_key())
    await store.initialize()

    now = time.time()
    session = StoredSession(
        session_id="session-expired-refresh",
        provider="dummy",
        user_info=UserInfo(provider="dummy", user_id="u", username="u"),
        access_token="expired_access",
        refresh_token="expired_refresh",
        provider_access_token=None,
        provider_refresh_token=None,
        provider_expires_at=None,
        expires_at=now - 1,
        created_at=now - 10,
        issued_at=now - 10,
        scopes=None,
    )
    await store.store_session(session)

    loaded = await store.load_session_by_refresh_token("expired_refresh")
    assert loaded is None

    await store.close()
