"""Token storage backends for MXCP authentication.

This module provides the `TokenStore` protocol and implementations for
persisting authentication sessions.

The default `SqliteTokenStore` implementation provides:
- Encrypted storage for provider tokens (using Fernet symmetric encryption)
- Hashed MXCP tokens (one-way, for secure lookup)
- Session lifecycle management
"""

import asyncio
import base64
import hashlib
import json
import logging
import sqlite3
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Protocol, runtime_checkable

from .sessions import Session

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# TokenStore Protocol
# ─────────────────────────────────────────────────────────────────────────────


@runtime_checkable
class TokenStore(Protocol):
    """Protocol for token storage backends.

    Implementations must provide async methods for storing and retrieving
    sessions.

    Security requirements for implementations:
    - MXCP tokens should be stored as hashes (one-way, for lookup only)
    - Provider tokens should be encrypted at rest
    - The encryption key should be provided externally (not stored with data)
    """

    async def initialize(self) -> None:
        """Initialize the storage backend."""
        ...

    async def close(self) -> None:
        """Close the storage backend and release resources."""
        ...

    # Session operations
    async def store_session(self, session: Session) -> None:
        """Store a session."""
        ...

    async def load_session_by_token_hash(self, token_hash: str) -> Session | None:
        """Load a session by MXCP token hash."""
        ...

    async def load_session_by_id(self, session_id: str) -> Session | None:
        """Load a session by session ID."""
        ...

    async def delete_session(self, session_id: str) -> None:
        """Delete a session by session ID."""
        ...

    async def cleanup_expired_sessions(self) -> int:
        """Remove expired sessions and return count of deleted sessions."""
        ...

    async def list_sessions(self) -> list[Session]:
        """List all active sessions."""
        ...


# ─────────────────────────────────────────────────────────────────────────────
# Encryption utilities
# ─────────────────────────────────────────────────────────────────────────────


class TokenEncryption:
    """Encryption utility for provider tokens.

    Uses Fernet symmetric encryption when a key is provided.
    Falls back to no encryption (plaintext) if no key is available.

    The encryption key should be:
    - A URL-safe base64-encoded 32-byte key
    - Provided via configuration (resolved through config resolvers)
    - Not stored alongside the encrypted data
    """

    def __init__(self, encryption_key: str | None = None):
        """Initialize encryption with optional key.

        Args:
            encryption_key: URL-safe base64-encoded Fernet key.
                           If None, encryption is disabled.
        """
        self._fernet = None

        if encryption_key:
            try:
                # Import cryptography only if encryption is enabled
                from cryptography.fernet import Fernet

                self._fernet = Fernet(encryption_key.encode())
                logger.info("Token encryption enabled")
            except ImportError:
                logger.warning(
                    "cryptography package not installed, encryption disabled"
                )
            except Exception as e:
                logger.error(f"Failed to initialize encryption: {e}")

    def encrypt(self, plaintext: str | None) -> str | None:
        """Encrypt a string value.

        Args:
            plaintext: The string to encrypt.

        Returns:
            Encrypted string (base64), or original if encryption disabled.
        """
        if plaintext is None:
            return None

        if self._fernet is None:
            return plaintext

        return self._fernet.encrypt(plaintext.encode()).decode()

    def decrypt(self, ciphertext: str | None) -> str | None:
        """Decrypt an encrypted string.

        Args:
            ciphertext: The encrypted string (base64).

        Returns:
            Decrypted string, or original if encryption disabled.
        """
        if ciphertext is None:
            return None

        if self._fernet is None:
            return ciphertext

        try:
            return self._fernet.decrypt(ciphertext.encode()).decode()
        except Exception as e:
            logger.error(f"Decryption failed: {e}")
            # Return original value on decryption failure
            # (might be unencrypted data from before encryption was enabled)
            return ciphertext

    @staticmethod
    def generate_key() -> str:
        """Generate a new encryption key.

        Returns:
            URL-safe base64-encoded 32-byte key.
        """
        from cryptography.fernet import Fernet

        return Fernet.generate_key().decode()


# ─────────────────────────────────────────────────────────────────────────────
# SQLite implementation
# ─────────────────────────────────────────────────────────────────────────────


class SqliteTokenStore:
    """SQLite-based token storage with encryption support.

    Provider tokens are encrypted using Fernet symmetric encryption.
    MXCP tokens are stored as SHA-256 hashes for secure lookup.

    The encryption key can be provided via configuration and resolved
    using the existing config resolvers (vault://, op://, ${ENV}).
    """

    def __init__(self, db_path: Path, encryption_key: str | None = None):
        """Initialize SQLite token store.

        Args:
            db_path: Path to SQLite database file.
            encryption_key: Optional encryption key for provider tokens.
        """
        self.db_path = db_path
        self._encryption = TokenEncryption(encryption_key)
        self._executor = ThreadPoolExecutor(max_workers=1)
        self._lock = threading.Lock()
        self.conn: sqlite3.Connection | None = None

    async def initialize(self) -> None:
        """Initialize the database."""
        await asyncio.get_event_loop().run_in_executor(
            self._executor, self._sync_initialize
        )

    def _sync_initialize(self) -> None:
        """Synchronous database initialization."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row

        cursor = self.conn.cursor()

        # Sessions table (new format with token hashing)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                mxcp_token_hash TEXT UNIQUE NOT NULL,
                client_id TEXT NOT NULL,
                provider_token_encrypted TEXT,
                provider_refresh_token_encrypted TEXT,
                scopes TEXT NOT NULL,
                expires_at REAL,
                created_at REAL NOT NULL,
                last_accessed_at REAL NOT NULL
            )
        """)

        # Index for token hash lookup
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_sessions_token_hash
            ON sessions(mxcp_token_hash)
        """)

        # Index for expiry cleanup
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_sessions_expires_at
            ON sessions(expires_at)
        """)

        self.conn.commit()
        logger.info(f"SQLite token store initialized at {self.db_path}")

    async def close(self) -> None:
        """Close the database connection."""
        await asyncio.get_event_loop().run_in_executor(self._executor, self._sync_close)
        self._executor.shutdown(wait=True)

    def _sync_close(self) -> None:
        """Synchronous database close."""
        if self.conn:
            self.conn.close()
            self.conn = None
        logger.info("SQLite token store closed")

    # ─────────────────────────────────────────────────────────────────────────
    # Session operations
    # ─────────────────────────────────────────────────────────────────────────

    async def store_session(self, session: Session) -> None:
        """Store a session."""
        await asyncio.get_event_loop().run_in_executor(
            self._executor, self._sync_store_session, session
        )

    def _sync_store_session(self, session: Session) -> None:
        """Synchronous session storage."""
        with self._lock:
            assert self.conn is not None
            cursor = self.conn.cursor()

            # Encrypt provider tokens
            provider_token_encrypted = self._encryption.encrypt(session.provider_token)
            provider_refresh_encrypted = self._encryption.encrypt(
                session.provider_refresh_token
            )

            cursor.execute(
                """
                INSERT OR REPLACE INTO sessions
                (session_id, mxcp_token_hash, client_id, provider_token_encrypted,
                 provider_refresh_token_encrypted, scopes, expires_at, created_at, last_accessed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    session.session_id,
                    session.mxcp_token_hash,
                    session.client_id,
                    provider_token_encrypted,
                    provider_refresh_encrypted,
                    json.dumps(session.scopes),
                    session.expires_at,
                    session.created_at,
                    session.last_accessed_at,
                ),
            )
            self.conn.commit()

    async def load_session_by_token_hash(self, token_hash: str) -> Session | None:
        """Load a session by MXCP token hash."""
        return await asyncio.get_event_loop().run_in_executor(
            self._executor, self._sync_load_session_by_token_hash, token_hash
        )

    def _sync_load_session_by_token_hash(self, token_hash: str) -> Session | None:
        """Synchronous session loading by token hash."""
        with self._lock:
            assert self.conn is not None
            cursor = self.conn.cursor()
            cursor.execute(
                """
                SELECT session_id, mxcp_token_hash, client_id, provider_token_encrypted,
                       provider_refresh_token_encrypted, scopes, expires_at, created_at, last_accessed_at
                FROM sessions WHERE mxcp_token_hash = ?
            """,
                (token_hash,),
            )

            row = cursor.fetchone()
            if not row:
                return None

            # Decrypt provider tokens
            provider_token = self._encryption.decrypt(row["provider_token_encrypted"])
            provider_refresh = self._encryption.decrypt(
                row["provider_refresh_token_encrypted"]
            )

            return Session(
                session_id=row["session_id"],
                mxcp_token="",  # Token is not stored, only hash
                mxcp_token_hash=row["mxcp_token_hash"],
                client_id=row["client_id"],
                provider_token=provider_token,
                provider_refresh_token=provider_refresh,
                scopes=json.loads(row["scopes"]),
                expires_at=row["expires_at"],
                created_at=row["created_at"],
                last_accessed_at=row["last_accessed_at"],
            )

    async def load_session_by_id(self, session_id: str) -> Session | None:
        """Load a session by session ID."""
        return await asyncio.get_event_loop().run_in_executor(
            self._executor, self._sync_load_session_by_id, session_id
        )

    def _sync_load_session_by_id(self, session_id: str) -> Session | None:
        """Synchronous session loading by ID."""
        with self._lock:
            assert self.conn is not None
            cursor = self.conn.cursor()
            cursor.execute(
                """
                SELECT session_id, mxcp_token_hash, client_id, provider_token_encrypted,
                       provider_refresh_token_encrypted, scopes, expires_at, created_at, last_accessed_at
                FROM sessions WHERE session_id = ?
            """,
                (session_id,),
            )

            row = cursor.fetchone()
            if not row:
                return None

            provider_token = self._encryption.decrypt(row["provider_token_encrypted"])
            provider_refresh = self._encryption.decrypt(
                row["provider_refresh_token_encrypted"]
            )

            return Session(
                session_id=row["session_id"],
                mxcp_token="",
                mxcp_token_hash=row["mxcp_token_hash"],
                client_id=row["client_id"],
                provider_token=provider_token,
                provider_refresh_token=provider_refresh,
                scopes=json.loads(row["scopes"]),
                expires_at=row["expires_at"],
                created_at=row["created_at"],
                last_accessed_at=row["last_accessed_at"],
            )

    async def delete_session(self, session_id: str) -> None:
        """Delete a session by session ID."""
        await asyncio.get_event_loop().run_in_executor(
            self._executor, self._sync_delete_session, session_id
        )

    def _sync_delete_session(self, session_id: str) -> None:
        """Synchronous session deletion."""
        with self._lock:
            assert self.conn is not None
            cursor = self.conn.cursor()
            cursor.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
            self.conn.commit()

    async def cleanup_expired_sessions(self) -> int:
        """Remove expired sessions."""
        return await asyncio.get_event_loop().run_in_executor(
            self._executor, self._sync_cleanup_expired_sessions
        )

    def _sync_cleanup_expired_sessions(self) -> int:
        """Synchronous expired session cleanup."""
        current_time = time.time()
        with self._lock:
            assert self.conn is not None
            cursor = self.conn.cursor()
            cursor.execute(
                "DELETE FROM sessions WHERE expires_at IS NOT NULL AND expires_at < ?",
                (current_time,),
            )
            deleted_count = cursor.rowcount
            self.conn.commit()
            return deleted_count

    async def list_sessions(self) -> list[Session]:
        """List all active sessions."""
        return await asyncio.get_event_loop().run_in_executor(
            self._executor, self._sync_list_sessions
        )

    def _sync_list_sessions(self) -> list[Session]:
        """Synchronous session listing."""
        with self._lock:
            assert self.conn is not None
            cursor = self.conn.cursor()
            cursor.execute(
                """
                SELECT session_id, mxcp_token_hash, client_id, provider_token_encrypted,
                       provider_refresh_token_encrypted, scopes, expires_at, created_at, last_accessed_at
                FROM sessions ORDER BY created_at DESC
            """
            )

            sessions = []
            for row in cursor.fetchall():
                provider_token = self._encryption.decrypt(row["provider_token_encrypted"])
                provider_refresh = self._encryption.decrypt(
                    row["provider_refresh_token_encrypted"]
                )

                sessions.append(
                    Session(
                        session_id=row["session_id"],
                        mxcp_token="",
                        mxcp_token_hash=row["mxcp_token_hash"],
                        client_id=row["client_id"],
                        provider_token=provider_token,
                        provider_refresh_token=provider_refresh,
                        scopes=json.loads(row["scopes"]),
                        expires_at=row["expires_at"],
                        created_at=row["created_at"],
                        last_accessed_at=row["last_accessed_at"],
                    )
                )
            return sessions


# ─────────────────────────────────────────────────────────────────────────────
# Factory function
# ─────────────────────────────────────────────────────────────────────────────


def create_token_store(
    store_config: dict[str, any] | None,
) -> SqliteTokenStore | None:
    """Create a token store based on configuration.

    Args:
        store_config: Storage configuration dict with keys:
            - type: "sqlite" (required)
            - path: Path to SQLite database (required for sqlite)
            - encryption_key: Optional encryption key for provider tokens

    Returns:
        TokenStore instance or None if no config provided.
    """
    if not store_config:
        return None

    store_type = store_config.get("type", "sqlite")

    if store_type == "sqlite":
        db_path = Path(store_config.get("path", "~/.mxcp/oauth.db")).expanduser()
        encryption_key = store_config.get("encryption_key")
        return SqliteTokenStore(db_path, encryption_key)
    else:
        raise ValueError(f"Unsupported token store type: {store_type}")
