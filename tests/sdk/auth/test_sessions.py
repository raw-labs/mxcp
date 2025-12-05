"""Tests for SessionManager, Session, and OAuthState classes.

This module tests the session management functionality from mxcp.sdk.auth.sessions.
"""

import pytest
import time

from mxcp.sdk.auth.sessions import OAuthState, Session, SessionManager


class TestSession:
    """Tests for the Session dataclass."""

    def test_create_session(self) -> None:
        """Session.create() should generate unique tokens and IDs."""
        session = Session.create(
            client_id="test-client",
            provider_token="provider-token-123",
            scopes=["read", "write"],
            expires_in=3600,
        )

        assert session.session_id is not None
        assert session.mxcp_token.startswith("mcp_")
        assert session.mxcp_token_hash is not None
        assert session.client_id == "test-client"
        assert session.provider_token == "provider-token-123"
        assert session.scopes == ["read", "write"]
        assert session.expires_at is not None

    def test_session_hash_token(self) -> None:
        """Session.hash_token() should produce consistent hashes."""
        token = "mcp_test_token_12345"
        hash1 = Session.hash_token(token)
        hash2 = Session.hash_token(token)

        assert hash1 == hash2
        assert len(hash1) == 64  # SHA-256 hex digest

    def test_session_hash_token_different_inputs(self) -> None:
        """Different tokens should produce different hashes."""
        hash1 = Session.hash_token("token1")
        hash2 = Session.hash_token("token2")

        assert hash1 != hash2

    def test_session_is_expired_false(self) -> None:
        """Session should not be expired before expiry time."""
        session = Session.create(
            client_id="test",
            expires_in=3600,
        )

        assert session.is_expired() is False

    def test_session_is_expired_true(self) -> None:
        """Session should be expired after expiry time."""
        session = Session.create(
            client_id="test",
            expires_in=0,  # Expires immediately
        )
        time.sleep(0.01)  # Ensure time has passed

        assert session.is_expired() is True

    def test_session_no_expiry(self) -> None:
        """Session with no expiry should never expire."""
        session = Session.create(
            client_id="test",
            expires_in=None,
        )

        assert session.expires_at is None
        assert session.is_expired() is False

    def test_session_touch(self) -> None:
        """Session.touch() should update last_accessed_at."""
        session = Session.create(client_id="test")
        original_time = session.last_accessed_at

        time.sleep(0.01)
        session.touch()

        assert session.last_accessed_at > original_time


class TestSessionManager:
    """Tests for the SessionManager class."""

    @pytest.mark.asyncio
    async def test_create_session(self) -> None:
        """SessionManager should create and store sessions."""
        manager = SessionManager()
        await manager.initialize()

        session = await manager.create_session(
            client_id="test-client",
            provider_token="provider-token",
            scopes=["read"],
            expires_in=3600,
        )

        assert session.client_id == "test-client"
        assert session.provider_token == "provider-token"

        await manager.close()

    @pytest.mark.asyncio
    async def test_get_session(self) -> None:
        """SessionManager should retrieve sessions by token."""
        manager = SessionManager()
        await manager.initialize()

        created = await manager.create_session(
            client_id="test-client",
            provider_token="provider-token",
        )

        retrieved = await manager.get_session(created.mxcp_token)

        assert retrieved is not None
        assert retrieved.session_id == created.session_id
        assert retrieved.provider_token == "provider-token"

        await manager.close()

    @pytest.mark.asyncio
    async def test_get_session_not_found(self) -> None:
        """SessionManager should return None for unknown tokens."""
        manager = SessionManager()
        await manager.initialize()

        result = await manager.get_session("nonexistent-token")

        assert result is None

        await manager.close()

    @pytest.mark.asyncio
    async def test_get_provider_token(self) -> None:
        """SessionManager should return provider token for valid session."""
        manager = SessionManager()
        await manager.initialize()

        session = await manager.create_session(
            client_id="test",
            provider_token="google-access-token-xyz",
        )

        provider_token = await manager.get_provider_token(session.mxcp_token)

        assert provider_token == "google-access-token-xyz"

        await manager.close()

    @pytest.mark.asyncio
    async def test_delete_session(self) -> None:
        """SessionManager should delete sessions."""
        manager = SessionManager()
        await manager.initialize()

        session = await manager.create_session(client_id="test")

        # Verify session exists
        assert await manager.get_session(session.mxcp_token) is not None

        # Delete session
        deleted = await manager.delete_session(session.mxcp_token)
        assert deleted is True

        # Verify session is gone
        assert await manager.get_session(session.mxcp_token) is None

        await manager.close()

    @pytest.mark.asyncio
    async def test_cleanup_expired_sessions(self) -> None:
        """SessionManager should clean up expired sessions."""
        manager = SessionManager()
        await manager.initialize()

        # Create an expired session
        await manager.create_session(
            client_id="test",
            expires_in=0,  # Expires immediately
        )
        time.sleep(0.01)  # Ensure expiry

        # Create a valid session
        valid_session = await manager.create_session(
            client_id="test",
            expires_in=3600,
        )

        # Cleanup
        deleted_count = await manager.cleanup_expired_sessions()

        assert deleted_count >= 1

        # Valid session should still exist
        assert await manager.get_session(valid_session.mxcp_token) is not None

        await manager.close()

    @pytest.mark.asyncio
    async def test_expired_session_not_returned(self) -> None:
        """SessionManager should not return expired sessions."""
        manager = SessionManager()
        await manager.initialize()

        session = await manager.create_session(
            client_id="test",
            expires_in=0,
        )
        time.sleep(0.01)

        result = await manager.get_session(session.mxcp_token)

        assert result is None

        await manager.close()


class TestSessionManagerAuthCodes:
    """Tests for SessionManager authorization code methods."""

    def test_store_and_get_auth_code(self) -> None:
        """store_auth_code should store code -> session mapping."""
        manager = SessionManager()

        manager.store_auth_code("mcp_code_123", "session_abc")

        result = manager.get_auth_code("mcp_code_123")
        assert result == "session_abc"

    def test_get_auth_code_not_found(self) -> None:
        """get_auth_code should return None for unknown codes."""
        manager = SessionManager()

        result = manager.get_auth_code("unknown_code")
        assert result is None

    def test_consume_auth_code(self) -> None:
        """consume_auth_code should return and remove the code."""
        manager = SessionManager()

        manager.store_auth_code("mcp_code_123", "session_abc")
        result = manager.consume_auth_code("mcp_code_123")

        assert result == "session_abc"
        # Code should be consumed (removed)
        assert manager.get_auth_code("mcp_code_123") is None

    def test_auth_code_expiry(self) -> None:
        """Expired auth codes should return None."""
        manager = SessionManager()

        # Store with 0 second expiry (already expired)
        manager.store_auth_code("mcp_code_123", "session_abc", expires_in=0)

        # Wait a tiny bit to ensure expiry
        import time
        time.sleep(0.01)

        result = manager.get_auth_code("mcp_code_123")
        assert result is None

    def test_cleanup_expired_auth_codes(self) -> None:
        """cleanup_expired_auth_codes should remove expired codes."""
        manager = SessionManager()

        # Store with 0 second expiry
        manager.store_auth_code("code1", "session1", expires_in=0)
        manager.store_auth_code("code2", "session2", expires_in=3600)

        import time
        time.sleep(0.01)

        cleaned = manager.cleanup_expired_auth_codes()

        assert cleaned == 1
        assert manager.get_auth_code("code1") is None
        assert manager.get_auth_code("code2") == "session2"


class TestOAuthState:
    """Tests for OAuthState dataclass."""

    def test_create_oauth_state(self) -> None:
        """OAuthState should store all required fields."""
        state = OAuthState(
            state="abc123",
            client_id="test-client",
            redirect_uri="http://localhost/callback",
            callback_url="http://localhost:8000/auth/callback",
            code_challenge="challenge",
            code_verifier="verifier",
        )

        assert state.state == "abc123"
        assert state.client_id == "test-client"
        assert state.redirect_uri == "http://localhost/callback"
        assert state.callback_url == "http://localhost:8000/auth/callback"
        assert state.code_challenge == "challenge"
        assert state.code_verifier == "verifier"

    def test_oauth_state_is_expired_false(self) -> None:
        """OAuthState should not be expired before expiry time."""
        state = OAuthState(
            state="test",
            client_id="test",
            redirect_uri="http://localhost",
            callback_url="http://localhost:8000/callback",
            expires_at=time.time() + 600,
        )

        assert state.is_expired() is False

    def test_oauth_state_is_expired_true(self) -> None:
        """OAuthState should be expired after expiry time."""
        state = OAuthState(
            state="test",
            client_id="test",
            redirect_uri="http://localhost",
            callback_url="http://localhost:8000/callback",
            expires_at=time.time() - 1,
        )

        assert state.is_expired() is True


class TestSessionManagerOAuthState:
    """Tests for SessionManager OAuth state management."""

    def test_create_oauth_state(self) -> None:
        """SessionManager should create and store OAuth state."""
        manager = SessionManager()

        oauth_state = manager.create_oauth_state(
            client_id="test-client",
            redirect_uri="http://localhost/callback",
            callback_url="http://localhost:8000/auth/callback",
            code_challenge="challenge",
            code_verifier="verifier",
            provider="google",
        )

        assert oauth_state.state is not None
        assert len(oauth_state.state) == 32  # hex(16)
        assert oauth_state.client_id == "test-client"
        assert oauth_state.provider == "google"

    def test_get_oauth_state(self) -> None:
        """SessionManager should retrieve OAuth state."""
        manager = SessionManager()

        created = manager.create_oauth_state(
            client_id="test-client",
            redirect_uri="http://localhost/callback",
            callback_url="http://localhost:8000/auth/callback",
        )

        retrieved = manager.get_oauth_state(created.state)

        assert retrieved is not None
        assert retrieved.client_id == "test-client"

    def test_get_oauth_state_not_found(self) -> None:
        """SessionManager should return None for unknown state."""
        manager = SessionManager()

        result = manager.get_oauth_state("nonexistent-state")

        assert result is None

    def test_get_oauth_state_expired(self) -> None:
        """SessionManager should return None for expired state."""
        manager = SessionManager()

        # Create state with 0 expiry (already expired)
        oauth_state = manager.create_oauth_state(
            client_id="test-client",
            redirect_uri="http://localhost/callback",
            callback_url="http://localhost:8000/auth/callback",
            expires_in=0,
        )
        time.sleep(0.01)

        result = manager.get_oauth_state(oauth_state.state)

        assert result is None

    def test_consume_oauth_state(self) -> None:
        """SessionManager should consume (get and remove) OAuth state."""
        manager = SessionManager()

        created = manager.create_oauth_state(
            client_id="test-client",
            redirect_uri="http://localhost/callback",
            callback_url="http://localhost:8000/auth/callback",
        )

        # First consume should return the state
        consumed = manager.consume_oauth_state(created.state)
        assert consumed is not None
        assert consumed.client_id == "test-client"

        # Second consume should return None (already consumed)
        second = manager.consume_oauth_state(created.state)
        assert second is None

    def test_cleanup_expired_oauth_states(self) -> None:
        """SessionManager should clean up expired OAuth states."""
        manager = SessionManager()

        # Create expired state
        manager.create_oauth_state(
            client_id="expired",
            redirect_uri="http://localhost/callback",
            callback_url="http://localhost:8000/auth/callback",
            expires_in=0,
        )
        time.sleep(0.01)

        # Create valid state
        valid = manager.create_oauth_state(
            client_id="valid",
            redirect_uri="http://localhost/callback",
            callback_url="http://localhost:8000/auth/callback",
            expires_in=600,
        )

        # Cleanup
        deleted_count = manager.cleanup_expired_oauth_states()

        assert deleted_count >= 1

        # Valid state should still exist
        assert manager.get_oauth_state(valid.state) is not None

