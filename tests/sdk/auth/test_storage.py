"""Tests for SqliteTokenStore and TokenEncryption classes.

This module tests the token storage functionality from mxcp.sdk.auth.storage.
"""

import pytest
import time
from pathlib import Path

from mxcp.sdk.auth.sessions import Session
from mxcp.sdk.auth.storage import (
    SqliteTokenStore,
    TokenEncryption,
    create_token_store,
)

# Check if cryptography is available
try:
    from cryptography.fernet import Fernet
    HAS_CRYPTOGRAPHY = True
except ImportError:
    HAS_CRYPTOGRAPHY = False


class TestTokenEncryption:
    """Tests for the TokenEncryption class."""

    def test_encryption_disabled_by_default(self) -> None:
        """TokenEncryption should pass through values when no key provided."""
        encryption = TokenEncryption()

        plaintext = "my-secret-token"
        result = encryption.encrypt(plaintext)

        assert result == plaintext

    def test_decryption_disabled_by_default(self) -> None:
        """TokenEncryption should pass through values when no key provided."""
        encryption = TokenEncryption()

        ciphertext = "my-secret-token"
        result = encryption.decrypt(ciphertext)

        assert result == ciphertext

    def test_encryption_none_value(self) -> None:
        """TokenEncryption should handle None values."""
        encryption = TokenEncryption()

        assert encryption.encrypt(None) is None
        assert encryption.decrypt(None) is None


@pytest.mark.skipif(not HAS_CRYPTOGRAPHY, reason="cryptography package not installed")
class TestTokenEncryptionWithKey:
    """Tests for TokenEncryption with actual encryption."""

    @pytest.fixture
    def fernet_key(self) -> str:
        """Generate a valid Fernet key for testing."""
        return Fernet.generate_key().decode()

    def test_encrypt_decrypt_roundtrip(self, fernet_key: str) -> None:
        """Encrypted values should decrypt to original."""
        encryption = TokenEncryption(fernet_key)

        plaintext = "my-secret-token-12345"
        ciphertext = encryption.encrypt(plaintext)
        decrypted = encryption.decrypt(ciphertext)

        assert ciphertext != plaintext  # Should be encrypted
        assert decrypted == plaintext

    def test_encrypted_values_are_different(self, fernet_key: str) -> None:
        """Same plaintext should produce different ciphertext (due to IV)."""
        encryption = TokenEncryption(fernet_key)

        plaintext = "my-secret-token"
        cipher1 = encryption.encrypt(plaintext)
        cipher2 = encryption.encrypt(plaintext)

        # Fernet uses random IV, so ciphertexts should differ
        assert cipher1 != cipher2

        # But both should decrypt to same value
        assert encryption.decrypt(cipher1) == plaintext
        assert encryption.decrypt(cipher2) == plaintext


class TestSqliteTokenStore:
    """Tests for SqliteTokenStore."""

    @pytest.fixture
    def db_path(self, tmp_path: Path) -> Path:
        """Create a temporary database path."""
        return tmp_path / "test_oauth.db"

    @pytest.mark.asyncio
    async def test_initialize(self, db_path: Path) -> None:
        """SqliteTokenStore should initialize database."""
        store = SqliteTokenStore(db_path)
        await store.initialize()

        assert db_path.exists()

        await store.close()

    @pytest.mark.asyncio
    async def test_store_and_load_session(self, db_path: Path) -> None:
        """SqliteTokenStore should store and retrieve sessions."""
        store = SqliteTokenStore(db_path)
        await store.initialize()

        session = Session.create(
            client_id="test-client",
            provider_token="google-token-xyz",
            scopes=["read", "write"],
            expires_in=3600,
        )

        await store.store_session(session)

        loaded = await store.load_session_by_token_hash(session.mxcp_token_hash)

        assert loaded is not None
        assert loaded.session_id == session.session_id
        assert loaded.client_id == "test-client"
        assert loaded.provider_token == "google-token-xyz"
        assert loaded.scopes == ["read", "write"]

        await store.close()

    @pytest.mark.skipif(not HAS_CRYPTOGRAPHY, reason="cryptography package not installed")
    @pytest.mark.asyncio
    async def test_encrypted_session_storage(self, db_path: Path) -> None:
        """SqliteTokenStore should encrypt provider tokens."""
        fernet_key = Fernet.generate_key().decode()
        store = SqliteTokenStore(db_path, encryption_key=fernet_key)
        await store.initialize()

        session = Session.create(
            client_id="test",
            provider_token="secret-google-token",
        )

        await store.store_session(session)

        # Load and verify decryption works
        loaded = await store.load_session_by_token_hash(session.mxcp_token_hash)
        assert loaded is not None
        assert loaded.provider_token == "secret-google-token"

        await store.close()

    @pytest.mark.asyncio
    async def test_delete_session(self, db_path: Path) -> None:
        """SqliteTokenStore should delete sessions."""
        store = SqliteTokenStore(db_path)
        await store.initialize()

        session = Session.create(client_id="test")
        await store.store_session(session)

        # Verify exists
        assert await store.load_session_by_id(session.session_id) is not None

        # Delete
        await store.delete_session(session.session_id)

        # Verify deleted
        assert await store.load_session_by_id(session.session_id) is None

        await store.close()

    @pytest.mark.asyncio
    async def test_cleanup_expired_sessions(self, db_path: Path) -> None:
        """SqliteTokenStore should clean up expired sessions."""
        store = SqliteTokenStore(db_path)
        await store.initialize()

        # Create expired session
        expired = Session.create(client_id="expired", expires_in=0)
        await store.store_session(expired)
        time.sleep(0.01)

        # Create valid session
        valid = Session.create(client_id="valid", expires_in=3600)
        await store.store_session(valid)

        # Cleanup
        deleted = await store.cleanup_expired_sessions()

        assert deleted >= 1

        # Valid should still exist
        assert await store.load_session_by_token_hash(valid.mxcp_token_hash) is not None

        await store.close()

    @pytest.mark.asyncio
    async def test_list_sessions(self, db_path: Path) -> None:
        """SqliteTokenStore should list all sessions."""
        store = SqliteTokenStore(db_path)
        await store.initialize()

        session1 = Session.create(client_id="client1")
        session2 = Session.create(client_id="client2")

        await store.store_session(session1)
        await store.store_session(session2)

        sessions = await store.list_sessions()

        assert len(sessions) == 2
        client_ids = {s.client_id for s in sessions}
        assert "client1" in client_ids
        assert "client2" in client_ids

        await store.close()


class TestCreateTokenStore:
    """Tests for the create_token_store factory function."""

    def test_create_sqlite_store(self, tmp_path: Path) -> None:
        """create_token_store should create SqliteTokenStore."""
        config = {
            "type": "sqlite",
            "path": str(tmp_path / "oauth.db"),
        }

        store = create_token_store(config)

        assert store is not None
        assert isinstance(store, SqliteTokenStore)

    @pytest.mark.skipif(not HAS_CRYPTOGRAPHY, reason="cryptography package not installed")
    def test_create_store_with_encryption_key(self, tmp_path: Path) -> None:
        """create_token_store should pass encryption key."""
        key = Fernet.generate_key().decode()

        config = {
            "type": "sqlite",
            "path": str(tmp_path / "oauth.db"),
            "encryption_key": key,
        }

        store = create_token_store(config)

        assert store is not None
        assert store._encryption._fernet is not None

    def test_create_store_none_config(self) -> None:
        """create_token_store should return None for no config."""
        store = create_token_store(None)
        assert store is None

    def test_create_store_unsupported_type(self) -> None:
        """create_token_store should raise for unsupported types."""
        config = {"type": "redis", "url": "redis://localhost"}

        with pytest.raises(ValueError, match="Unsupported token store type"):
            create_token_store(config)

