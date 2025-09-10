"""OAuth persistence backends for MXCP authentication."""

import asyncio
import json
import logging
import sqlite3
import threading
import time
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class PersistedAccessToken:
    """Persisted access token data."""

    token: str
    client_id: str
    external_token: str | None
    refresh_token: str | None  # refresh token for renewing external_token
    scopes: list[str]
    expires_at: float | None
    created_at: float


@dataclass
class PersistedAuthCode:
    """Persisted authorization code data."""

    code: str
    client_id: str
    redirect_uri: str
    redirect_uri_provided_explicitly: bool
    expires_at: float
    scopes: list[str]
    code_challenge: str | None
    created_at: float


@dataclass
class PersistedClient:
    """Persisted OAuth client data."""

    client_id: str
    client_secret: str | None
    redirect_uris: list[str]
    grant_types: list[str]
    response_types: list[str]
    scope: str
    client_name: str
    created_at: float


class AuthPersistenceBackend(ABC):
    """Abstract interface for OAuth authentication persistence."""

    @abstractmethod
    async def initialize(self) -> None:
        """Initialize the persistence backend."""
        pass

    @abstractmethod
    async def close(self) -> None:
        """Close the persistence backend."""
        pass

    # Token operations
    @abstractmethod
    async def store_token(self, token_data: PersistedAccessToken) -> None:
        """Store an access token."""
        pass

    @abstractmethod
    async def load_token(self, token: str) -> PersistedAccessToken | None:
        """Load an access token by token string."""
        pass

    @abstractmethod
    async def delete_token(self, token: str) -> None:
        """Delete an access token."""
        pass

    @abstractmethod
    async def cleanup_expired_tokens(self) -> int:
        """Remove expired tokens and return count of deleted tokens."""
        pass

    # Authorization code operations
    @abstractmethod
    async def store_auth_code(self, code_data: PersistedAuthCode) -> None:
        """Store an authorization code."""
        pass

    @abstractmethod
    async def load_auth_code(self, code: str) -> PersistedAuthCode | None:
        """Load an authorization code by code string."""
        pass

    @abstractmethod
    async def delete_auth_code(self, code: str) -> None:
        """Delete an authorization code."""
        pass

    @abstractmethod
    async def cleanup_expired_auth_codes(self) -> int:
        """Remove expired authorization codes and return count of deleted codes."""
        pass

    # Client operations
    @abstractmethod
    async def store_client(self, client_data: PersistedClient) -> None:
        """Store an OAuth client."""
        pass

    @abstractmethod
    async def load_client(self, client_id: str) -> PersistedClient | None:
        """Load an OAuth client by client ID."""
        pass

    @abstractmethod
    async def delete_client(self, client_id: str) -> None:
        """Delete an OAuth client."""
        pass

    @abstractmethod
    async def list_clients(self) -> list[PersistedClient]:
        """List all stored OAuth clients."""
        pass


class SQLiteAuthPersistence(AuthPersistenceBackend):
    """SQLite-based OAuth authentication persistence."""

    def __init__(self, db_path: Path):
        """Initialize SQLite persistence backend.

        Args:
            db_path: Path to the SQLite database file
        """
        self.db_path = db_path
        self.conn: sqlite3.Connection | None = None
        self._lock = threading.RLock()  # Reentrant lock for nested calls
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="oauth-db")
        self._initialized = False

    async def initialize(self) -> None:
        """Initialize the SQLite database and create tables."""
        if self._initialized:
            return

        await asyncio.get_event_loop().run_in_executor(self._executor, self._sync_initialize)

    def _sync_initialize(self) -> None:
        """Synchronous initialization method."""
        with self._lock:
            if self._initialized:
                return

            # Ensure directory exists
            self.db_path.parent.mkdir(parents=True, exist_ok=True)

            # Connect to database
            self.conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
            self.conn.row_factory = sqlite3.Row  # Enable column access by name

            # Create tables
            self._create_tables_sync()

            self._initialized = True
            logger.info(f"Initialized SQLite OAuth persistence at {self.db_path}")

    async def close(self) -> None:
        """Close the database connection."""
        await asyncio.get_event_loop().run_in_executor(self._executor, self._sync_close)
        # Shutdown the executor
        self._executor.shutdown(wait=True)

    def _sync_close(self) -> None:
        """Synchronous close method."""
        with self._lock:
            if self.conn:
                self.conn.close()
                self.conn = None
                logger.info("Closed SQLite OAuth persistence connection")

    def _create_tables_sync(self) -> None:
        """Create the necessary database tables (synchronous)."""
        assert self.conn is not None, "Connection must be initialized"
        cursor = self.conn.cursor()

        # Access tokens table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS access_tokens (
                token TEXT PRIMARY KEY,
                client_id TEXT NOT NULL,
                external_token TEXT,
                refresh_token TEXT,
                scopes TEXT NOT NULL,
                expires_at REAL,
                created_at REAL NOT NULL
            )
        """
        )

        # Create index separately for better compatibility
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_access_tokens_expires_at
            ON access_tokens(expires_at)
        """
        )

        # Authorization codes table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS auth_codes (
                code TEXT PRIMARY KEY,
                client_id TEXT NOT NULL,
                redirect_uri TEXT NOT NULL,
                redirect_uri_provided_explicitly INTEGER NOT NULL,
                expires_at REAL NOT NULL,
                scopes TEXT NOT NULL,
                code_challenge TEXT,
                created_at REAL NOT NULL
            )
        """
        )

        # Create index separately
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_auth_codes_expires_at
            ON auth_codes(expires_at)
        """
        )

        # OAuth clients table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS oauth_clients (
                client_id TEXT PRIMARY KEY,
                client_secret TEXT,
                redirect_uris TEXT NOT NULL,
                grant_types TEXT NOT NULL,
                response_types TEXT NOT NULL,
                scope TEXT NOT NULL,
                client_name TEXT NOT NULL,
                created_at REAL NOT NULL
            )
        """
        )

        self.conn.commit()

    # Token operations
    async def store_token(self, token_data: PersistedAccessToken) -> None:
        """Store an access token."""
        await asyncio.get_event_loop().run_in_executor(
            self._executor, self._sync_store_token, token_data
        )

    def _sync_store_token(self, token_data: PersistedAccessToken) -> None:
        """Synchronous token storage."""
        with self._lock:
            assert self.conn is not None, "Connection must be initialized"
            cursor = self.conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO access_tokens
                (token, client_id, external_token, refresh_token, scopes, expires_at, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    token_data.token,
                    token_data.client_id,
                    token_data.external_token,
                    token_data.refresh_token,
                    json.dumps(token_data.scopes),
                    token_data.expires_at,
                    token_data.created_at,
                ),
            )
            self.conn.commit()

    async def load_token(self, token: str) -> PersistedAccessToken | None:
        """Load an access token by token string."""
        return await asyncio.get_event_loop().run_in_executor(
            self._executor, self._sync_load_token, token
        )

    def _sync_load_token(self, token: str) -> PersistedAccessToken | None:
        """Synchronous token loading."""
        with self._lock:
            assert self.conn is not None, "Connection must be initialized"
            cursor = self.conn.cursor()
            cursor.execute(
                """
                SELECT token, client_id, external_token, refresh_token, scopes, expires_at, created_at
                FROM access_tokens WHERE token = ?
            """,
                (token,),
            )

            row = cursor.fetchone()
            if not row:
                return None

            return PersistedAccessToken(
                token=row["token"],
                client_id=row["client_id"],
                external_token=row["external_token"],
                refresh_token=row["refresh_token"],
                scopes=json.loads(row["scopes"]),
                expires_at=row["expires_at"],
                created_at=row["created_at"],
            )

    async def delete_token(self, token: str) -> None:
        """Delete an access token."""
        await asyncio.get_event_loop().run_in_executor(
            self._executor, self._sync_delete_token, token
        )

    def _sync_delete_token(self, token: str) -> None:
        """Synchronous token deletion."""
        with self._lock:
            assert self.conn is not None, "Connection must be initialized"
            cursor = self.conn.cursor()
            cursor.execute("DELETE FROM access_tokens WHERE token = ?", (token,))
            self.conn.commit()

    async def cleanup_expired_tokens(self) -> int:
        """Remove expired tokens and return count of deleted tokens."""
        return await asyncio.get_event_loop().run_in_executor(
            self._executor, self._sync_cleanup_expired_tokens
        )

    def _sync_cleanup_expired_tokens(self) -> int:
        """Synchronous expired token cleanup."""
        current_time = time.time()
        with self._lock:
            assert self.conn is not None, "Connection must be initialized"
            cursor = self.conn.cursor()
            cursor.execute(
                """
                DELETE FROM access_tokens
                WHERE expires_at IS NOT NULL AND expires_at < ?
            """,
                (current_time,),
            )
            deleted_count = cursor.rowcount
            self.conn.commit()
            return deleted_count

    # Authorization code operations
    async def store_auth_code(self, code_data: PersistedAuthCode) -> None:
        """Store an authorization code."""
        await asyncio.get_event_loop().run_in_executor(
            self._executor, self._sync_store_auth_code, code_data
        )

    def _sync_store_auth_code(self, code_data: PersistedAuthCode) -> None:
        """Synchronous auth code storage."""
        with self._lock:
            assert self.conn is not None, "Connection must be initialized"
            cursor = self.conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO auth_codes
                (code, client_id, redirect_uri, redirect_uri_provided_explicitly,
                 expires_at, scopes, code_challenge, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    code_data.code,
                    code_data.client_id,
                    code_data.redirect_uri,
                    int(code_data.redirect_uri_provided_explicitly),
                    code_data.expires_at,
                    json.dumps(code_data.scopes),
                    code_data.code_challenge,
                    code_data.created_at,
                ),
            )
            self.conn.commit()

    async def load_auth_code(self, code: str) -> PersistedAuthCode | None:
        """Load an authorization code by code string."""
        return await asyncio.get_event_loop().run_in_executor(
            self._executor, self._sync_load_auth_code, code
        )

    def _sync_load_auth_code(self, code: str) -> PersistedAuthCode | None:
        """Synchronous auth code loading."""
        with self._lock:
            assert self.conn is not None, "Connection must be initialized"
            cursor = self.conn.cursor()
            cursor.execute(
                """
                SELECT code, client_id, redirect_uri, redirect_uri_provided_explicitly,
                       expires_at, scopes, code_challenge, created_at
                FROM auth_codes WHERE code = ?
            """,
                (code,),
            )

            row = cursor.fetchone()
            if not row:
                return None

            return PersistedAuthCode(
                code=row["code"],
                client_id=row["client_id"],
                redirect_uri=row["redirect_uri"],
                redirect_uri_provided_explicitly=bool(row["redirect_uri_provided_explicitly"]),
                expires_at=row["expires_at"],
                scopes=json.loads(row["scopes"]),
                code_challenge=row["code_challenge"],
                created_at=row["created_at"],
            )

    async def delete_auth_code(self, code: str) -> None:
        """Delete an authorization code."""
        await asyncio.get_event_loop().run_in_executor(
            self._executor, self._sync_delete_auth_code, code
        )

    def _sync_delete_auth_code(self, code: str) -> None:
        """Synchronous auth code deletion."""
        with self._lock:
            assert self.conn is not None, "Connection must be initialized"
            cursor = self.conn.cursor()
            cursor.execute("DELETE FROM auth_codes WHERE code = ?", (code,))
            self.conn.commit()

    async def cleanup_expired_auth_codes(self) -> int:
        """Remove expired authorization codes and return count of deleted codes."""
        return await asyncio.get_event_loop().run_in_executor(
            self._executor, self._sync_cleanup_expired_auth_codes
        )

    def _sync_cleanup_expired_auth_codes(self) -> int:
        """Synchronous expired auth code cleanup."""
        current_time = time.time()
        with self._lock:
            assert self.conn is not None, "Connection must be initialized"
            cursor = self.conn.cursor()
            cursor.execute(
                """
                DELETE FROM auth_codes WHERE expires_at < ?
            """,
                (current_time,),
            )
            deleted_count = cursor.rowcount
            self.conn.commit()
            return deleted_count

    # Client operations
    async def store_client(self, client_data: PersistedClient) -> None:
        """Store an OAuth client."""
        await asyncio.get_event_loop().run_in_executor(
            self._executor, self._sync_store_client, client_data
        )

    def _sync_store_client(self, client_data: PersistedClient) -> None:
        """Synchronous client storage."""
        with self._lock:
            assert self.conn is not None, "Connection must be initialized"
            cursor = self.conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO oauth_clients
                (client_id, client_secret, redirect_uris, grant_types,
                 response_types, scope, client_name, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    client_data.client_id,
                    client_data.client_secret,
                    json.dumps(client_data.redirect_uris),
                    json.dumps(client_data.grant_types),
                    json.dumps(client_data.response_types),
                    client_data.scope,
                    client_data.client_name,
                    client_data.created_at,
                ),
            )
            self.conn.commit()

    async def load_client(self, client_id: str) -> PersistedClient | None:
        """Load an OAuth client by client ID."""
        return await asyncio.get_event_loop().run_in_executor(
            self._executor, self._sync_load_client, client_id
        )

    def _sync_load_client(self, client_id: str) -> PersistedClient | None:
        """Synchronous client loading."""
        with self._lock:
            assert self.conn is not None, "Connection must be initialized"
            cursor = self.conn.cursor()
            cursor.execute(
                """
                SELECT client_id, client_secret, redirect_uris, grant_types,
                       response_types, scope, client_name, created_at
                FROM oauth_clients WHERE client_id = ?
            """,
                (client_id,),
            )

            row = cursor.fetchone()
            if not row:
                return None

            return PersistedClient(
                client_id=row["client_id"],
                client_secret=row["client_secret"],
                redirect_uris=json.loads(row["redirect_uris"]),
                grant_types=json.loads(row["grant_types"]),
                response_types=json.loads(row["response_types"]),
                scope=row["scope"],
                client_name=row["client_name"],
                created_at=row["created_at"],
            )

    async def delete_client(self, client_id: str) -> None:
        """Delete an OAuth client."""
        await asyncio.get_event_loop().run_in_executor(
            self._executor, self._sync_delete_client, client_id
        )

    def _sync_delete_client(self, client_id: str) -> None:
        """Synchronous client deletion."""
        with self._lock:
            assert self.conn is not None, "Connection must be initialized"
            cursor = self.conn.cursor()
            cursor.execute("DELETE FROM oauth_clients WHERE client_id = ?", (client_id,))
            self.conn.commit()

    async def list_clients(self) -> list[PersistedClient]:
        """List all stored OAuth clients."""
        return await asyncio.get_event_loop().run_in_executor(
            self._executor, self._sync_list_clients
        )

    def _sync_list_clients(self) -> list[PersistedClient]:
        """Synchronous client listing."""
        with self._lock:
            assert self.conn is not None, "Connection must be initialized"
            cursor = self.conn.cursor()
            cursor.execute(
                """
                SELECT client_id, client_secret, redirect_uris, grant_types,
                       response_types, scope, client_name, created_at
                FROM oauth_clients ORDER BY created_at DESC
            """
            )

            clients = []
            for row in cursor.fetchall():
                clients.append(
                    PersistedClient(
                        client_id=row["client_id"],
                        client_secret=row["client_secret"],
                        redirect_uris=json.loads(row["redirect_uris"]),
                        grant_types=json.loads(row["grant_types"]),
                        response_types=json.loads(row["response_types"]),
                        scope=row["scope"],
                        client_name=row["client_name"],
                        created_at=row["created_at"],
                    )
                )
            return clients


def create_persistence_backend(
    persistence_config: dict[str, Any] | None,
) -> AuthPersistenceBackend | None:
    """Create a persistence backend based on configuration.

    Args:
        persistence_config: Persistence configuration from user config

    Returns:
        Persistence backend instance or None if disabled
    """
    if not persistence_config:
        # No persistence configured
        return None

    backend_type = persistence_config["type"]  # Should always be present due to config defaults

    if backend_type == "sqlite":
        db_path = Path(
            persistence_config["path"]
        )  # Should always be present due to config defaults
        return SQLiteAuthPersistence(db_path)
    else:
        raise ValueError(f"Unsupported persistence backend type: {backend_type}")
