"""Token storage implementations for the issuer-mode auth stack.

This module is **security critical**. It persists:
- OAuth **state** (one-time, expiring)
- MXCP **authorization codes** (one-time, expiring)
- MXCP **sessions** (opaque access/refresh tokens + user info)
- OAuth **client registrations** (preconfigured + DCR), used for redirect binding

## Storage invariants (“do not break”)

- **State** and **auth codes** must be consumed/deleted on use and rejected when expired.
- **Sessions** must be keyed by a hashed access token and must not be returned once expired.
- **Client registrations** are persisted and are the source of truth for redirect validation.

## At-rest protection

Implementations should store tokens hashed and/or encrypted. Do not log token values,
secrets, SQL queries, or user identifiers.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import sqlite3
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Literal, Protocol

from cryptography.fernet import Fernet, InvalidToken

from mxcp.sdk.auth.contracts import Session, UserInfo
from mxcp.sdk.models import SdkBaseModel

# RFC 7591 / RFC 6749 token endpoint client auth methods supported by MCP.
TokenEndpointAuthMethod = Literal[
    "none",
    "client_secret_post",
    "client_secret_basic",
    "private_key_jwt",
]


class StateRecord(SdkBaseModel):
    """Persisted OAuth state used for PKCE and redirect validation."""

    state: str  # MXCP-generated state (used for Google callback)
    client_id: str | None = None
    redirect_uri: str | None = None
    code_challenge: str | None = None
    code_challenge_method: str | None = None
    provider_code_verifier: str | None = None  # Code verifier for provider (Google) PKCE
    client_state: str | None = None  # Original state from MCP client (returned in redirect)
    scopes: list[str] | None = None
    expires_at: float
    created_at: float


class AuthCodeRecord(SdkBaseModel):
    """Persisted authorization code bound to a session."""

    code: str
    session_id: str
    client_id: str | None = None
    redirect_uri: str | None = None
    code_challenge: str | None = None
    code_challenge_method: str | None = None
    scopes: list[str] | None = None
    expires_at: float
    created_at: float


class StoredSession(Session):
    """Session persisted in the token store."""

    created_at: float


class ClientRecord(SdkBaseModel):
    """Persisted OAuth client record (configured or dynamically registered).

    Note: this represents OAuth client metadata for issuer-mode only. It must not be
    confused with MXCP permissions. The `scope` field is stored as client metadata
    (useful for compatibility/inspection) but is not used to drive upstream IdP scopes.
    """

    client_id: str
    client_secret: str | None = None
    # How the client authenticates to the token endpoint (RFC 7591).
    # This is required by the MCP token endpoint middleware; if unset, callers
    # may fail with "Unsupported auth method: None".
    token_endpoint_auth_method: TokenEndpointAuthMethod | None = None
    redirect_uris: list[str]
    grant_types: list[str]
    response_types: list[str]
    scope: str | None = None
    client_name: str | None = None
    created_at: float


class TokenStore(Protocol):
    """Abstract interface for token persistence.

    Backends must ensure:
    - States and auth codes are one-time use and honor expiry.
    - Sessions are keyed by hashed access token; returning an expired session must
      delete it and return None.
    - Storage operations are async-safe (thread-safe if using sync engines).
    """

    async def initialize(self) -> None: ...

    async def close(self) -> None: ...

    async def store_state(self, record: StateRecord) -> None: ...

    async def consume_state(self, state: str) -> StateRecord | None: ...

    async def store_auth_code(self, record: AuthCodeRecord) -> None: ...

    # Auth codes should be loaded, validated, then explicitly deleted.
    async def load_auth_code(self, code: str) -> AuthCodeRecord | None: ...

    async def delete_auth_code(self, code: str) -> None: ...
    async def try_delete_auth_code(self, code: str) -> bool: ...

    async def store_session(self, record: StoredSession) -> None: ...

    async def load_session_by_token(self, access_token: str) -> StoredSession | None: ...

    async def load_session_by_id(self, session_id: str) -> StoredSession | None: ...

    async def load_session_by_refresh_token(self, refresh_token: str) -> StoredSession | None: ...

    async def delete_session_by_token(self, access_token: str) -> None: ...

    async def cleanup_expired(self) -> dict[str, int]: ...

    # OAuth client registry (for Dynamic Client Registration)
    async def store_client(self, record: ClientRecord) -> None: ...

    async def load_client(self, client_id: str) -> ClientRecord | None: ...

    async def list_clients(self) -> list[ClientRecord]: ...

    async def delete_client(self, client_id: str) -> None: ...


class SqliteTokenStore(TokenStore):
    """SQLite-backed TokenStore with hashing and optional Fernet encryption."""

    def __init__(
        self,
        db_path: Path,
        encryption_key: str | bytes | None = None,
        *,
        allow_plaintext_tokens: bool = False,
    ) -> None:
        self.db_path = db_path
        self.allow_plaintext_tokens = allow_plaintext_tokens
        self._logger = logging.getLogger(__name__)
        self._conn: sqlite3.Connection | None = None
        self._lock = threading.RLock()
        self._executor: ThreadPoolExecutor | None = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="auth-store"
        )
        self._initialized = False
        self._fernet = self._build_fernet(encryption_key) if encryption_key else None
        if not self._fernet and self.allow_plaintext_tokens:
            self._logger.warning(
                "Storing auth tokens in plaintext because allow_plaintext_tokens=True and no "
                "encryption key was provided. This disables at-rest protection."
            )

    async def initialize(self) -> None:
        if self._initialized:
            return
        executor = self._ensure_executor()
        await asyncio.get_running_loop().run_in_executor(executor, self._sync_initialize)

    async def close(self) -> None:
        if self._executor:
            await asyncio.get_running_loop().run_in_executor(self._executor, self._sync_close)
            self._executor.shutdown(wait=True)
        self._executor = None
        self._initialized = False

    # ── State ──────────────────────────────────────────────────────────────────
    async def store_state(self, record: StateRecord) -> None:
        payload = {
            "state": record.state,
            "client_id": record.client_id,
            "redirect_uri": record.redirect_uri,
            "code_challenge": record.code_challenge,
            "code_challenge_method": record.code_challenge_method,
            "provider_code_verifier": record.provider_code_verifier,
            "client_state": record.client_state,
            "scopes": json.dumps(record.scopes or []),
            "expires_at": record.expires_at,
            "created_at": record.created_at,
        }
        await asyncio.get_running_loop().run_in_executor(
            self._executor, self._sync_store_state, payload
        )

    async def consume_state(self, state: str) -> StateRecord | None:
        return await asyncio.get_running_loop().run_in_executor(
            self._executor, self._sync_consume_state, state
        )

    # ── Auth codes ─────────────────────────────────────────────────────────────
    async def store_auth_code(self, record: AuthCodeRecord) -> None:
        payload = {
            "code": record.code,
            "session_id": record.session_id,
            "client_id": record.client_id,
            "redirect_uri": record.redirect_uri,
            "code_challenge": record.code_challenge,
            "code_challenge_method": record.code_challenge_method,
            "scopes": json.dumps(record.scopes or []),
            "expires_at": record.expires_at,
            "created_at": record.created_at,
        }
        await asyncio.get_running_loop().run_in_executor(
            self._executor, self._sync_store_auth_code, payload
        )

    async def load_auth_code(self, code: str) -> AuthCodeRecord | None:
        return await asyncio.get_running_loop().run_in_executor(
            self._executor, self._sync_load_auth_code, code
        )

    async def delete_auth_code(self, code: str) -> None:
        await asyncio.get_running_loop().run_in_executor(
            self._executor, self._sync_delete_auth_code, code
        )

    async def try_delete_auth_code(self, code: str) -> bool:
        return await asyncio.get_running_loop().run_in_executor(
            self._executor, self._sync_try_delete_auth_code, code
        )

    # ── Sessions ───────────────────────────────────────────────────────────────
    async def store_session(self, record: StoredSession) -> None:
        payload = self._serialize_session(record)
        await asyncio.get_running_loop().run_in_executor(
            self._executor, self._sync_store_session, payload
        )

    async def load_session_by_token(self, access_token: str) -> StoredSession | None:
        hashed = self._hash_token(access_token)
        return await asyncio.get_running_loop().run_in_executor(
            self._executor, self._sync_load_session_by_hash, hashed
        )

    async def load_session_by_id(self, session_id: str) -> StoredSession | None:
        return await asyncio.get_running_loop().run_in_executor(
            self._executor, self._sync_load_session_by_id, session_id
        )

    async def load_session_by_refresh_token(self, refresh_token: str) -> StoredSession | None:
        hashed = self._hash_token(refresh_token)
        return await asyncio.get_running_loop().run_in_executor(
            self._executor, self._sync_load_session_by_refresh_hash, hashed
        )

    async def delete_session_by_token(self, access_token: str) -> None:
        hashed = self._hash_token(access_token)
        await asyncio.get_running_loop().run_in_executor(
            self._executor, self._sync_delete_session_by_hash, hashed
        )

    # ── OAuth clients ──────────────────────────────────────────────────────────
    async def store_client(self, record: ClientRecord) -> None:
        payload = {
            "client_id": record.client_id,
            "client_secret": self._encrypt(record.client_secret),
            "token_endpoint_auth_method": record.token_endpoint_auth_method,
            "redirect_uris": json.dumps(record.redirect_uris),
            "grant_types": json.dumps(record.grant_types),
            "response_types": json.dumps(record.response_types),
            "scope": record.scope,
            "client_name": record.client_name,
            "created_at": record.created_at,
        }
        await asyncio.get_running_loop().run_in_executor(
            self._executor, self._sync_store_client, payload
        )

    async def load_client(self, client_id: str) -> ClientRecord | None:
        return await asyncio.get_running_loop().run_in_executor(
            self._executor, self._sync_load_client, client_id
        )

    async def list_clients(self) -> list[ClientRecord]:
        return await asyncio.get_running_loop().run_in_executor(
            self._executor, self._sync_list_clients
        )

    async def delete_client(self, client_id: str) -> None:
        await asyncio.get_running_loop().run_in_executor(
            self._executor, self._sync_delete_client, client_id
        )

    # ── Cleanup ────────────────────────────────────────────────────────────────
    async def cleanup_expired(self) -> dict[str, int]:
        return await asyncio.get_running_loop().run_in_executor(
            self._executor, self._sync_cleanup_expired
        )

    # ── Internals (sync) ───────────────────────────────────────────────────────
    def _sync_initialize(self) -> None:
        with self._lock:
            if self._initialized:
                return
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            self._create_tables()
            self._initialized = True

    def _sync_close(self) -> None:
        with self._lock:
            if self._conn:
                self._conn.close()
                self._conn = None
            self._initialized = False

    def _create_tables(self) -> None:
        assert self._conn is not None
        cursor = self._conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS states (
                state TEXT PRIMARY KEY,
                client_id TEXT,
                redirect_uri TEXT,
                code_challenge TEXT,
                code_challenge_method TEXT,
                provider_code_verifier TEXT,
                client_state TEXT,
                scopes TEXT NOT NULL,
                expires_at REAL NOT NULL,
                created_at REAL NOT NULL
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS auth_codes (
                code TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                client_id TEXT,
                redirect_uri TEXT,
                code_challenge TEXT,
                code_challenge_method TEXT,
                scopes TEXT NOT NULL,
                expires_at REAL NOT NULL,
                created_at REAL NOT NULL
            )
            """
        )
        self._ensure_auth_code_columns()
        self._ensure_state_columns()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                access_token_hash TEXT PRIMARY KEY,
                access_token_encrypted TEXT NOT NULL,
                refresh_token_hash TEXT,
                refresh_token_encrypted TEXT,
                session_id TEXT NOT NULL UNIQUE,
                provider TEXT NOT NULL,
                user_info TEXT NOT NULL,
                provider_access_token TEXT,
                provider_refresh_token TEXT,
                provider_expires_at REAL,
                expires_at REAL,
                created_at REAL NOT NULL
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS oauth_clients (
                client_id TEXT PRIMARY KEY,
                client_secret TEXT,
                token_endpoint_auth_method TEXT,
                redirect_uris TEXT NOT NULL,
                grant_types TEXT NOT NULL,
                response_types TEXT NOT NULL,
                scope TEXT,
                client_name TEXT,
                created_at REAL NOT NULL
            )
            """
        )
        self._ensure_oauth_client_columns()
        self._conn.commit()

    def _ensure_auth_code_columns(self) -> None:
        """Add missing auth_code columns when upgrading existing db."""
        assert self._conn is not None
        cursor = self._conn.cursor()
        cursor.execute("PRAGMA table_info(auth_codes)")
        columns = [row[1] for row in cursor.fetchall()]
        if "code_challenge" not in columns:
            cursor.execute("ALTER TABLE auth_codes ADD COLUMN code_challenge TEXT")
        if "code_challenge_method" not in columns:
            cursor.execute("ALTER TABLE auth_codes ADD COLUMN code_challenge_method TEXT")
        if "client_id" not in columns:
            cursor.execute("ALTER TABLE auth_codes ADD COLUMN client_id TEXT")

    def _ensure_state_columns(self) -> None:
        """Add missing state columns when upgrading existing db."""
        assert self._conn is not None
        cursor = self._conn.cursor()
        cursor.execute("PRAGMA table_info(states)")
        columns = [row[1] for row in cursor.fetchall()]
        if "provider_code_verifier" not in columns:
            cursor.execute("ALTER TABLE states ADD COLUMN provider_code_verifier TEXT")
        if "client_state" not in columns:
            cursor.execute("ALTER TABLE states ADD COLUMN client_state TEXT")

    def _ensure_oauth_client_columns(self) -> None:
        """Add missing oauth_client columns when upgrading existing db."""
        assert self._conn is not None
        cursor = self._conn.cursor()
        cursor.execute("PRAGMA table_info(oauth_clients)")
        columns = [row[1] for row in cursor.fetchall()]
        if "token_endpoint_auth_method" not in columns:
            cursor.execute("ALTER TABLE oauth_clients ADD COLUMN token_endpoint_auth_method TEXT")

    # State helpers
    def _sync_store_state(self, payload: dict[str, Any]) -> None:
        assert self._conn is not None
        with self._lock:
            self._conn.execute(
                """
                INSERT OR REPLACE INTO states
                (state, client_id, redirect_uri, code_challenge, code_challenge_method, provider_code_verifier, client_state, scopes, expires_at, created_at)
                VALUES (:state, :client_id, :redirect_uri, :code_challenge, :code_challenge_method, :provider_code_verifier, :client_state, :scopes, :expires_at, :created_at)
                """,
                payload,
            )
            self._conn.commit()

    def _sync_consume_state(self, state: str) -> StateRecord | None:
        assert self._conn is not None
        with self._lock:
            row = self._conn.execute("SELECT * FROM states WHERE state = ?", (state,)).fetchone()
            if not row:
                return None

            if row["expires_at"] < time.time():
                self._conn.execute("DELETE FROM states WHERE state = ?", (state,))
                self._conn.commit()
                return None

            self._conn.execute("DELETE FROM states WHERE state = ?", (state,))
            self._conn.commit()

            # Handle provider_code_verifier and client_state which may not exist in older databases
            from contextlib import suppress

            provider_code_verifier = None
            with suppress(KeyError, IndexError):
                provider_code_verifier = row["provider_code_verifier"]

            client_state = None
            with suppress(KeyError, IndexError):
                client_state = row["client_state"]

            return StateRecord(
                state=row["state"],
                client_id=row["client_id"],
                redirect_uri=row["redirect_uri"],
                code_challenge=row["code_challenge"],
                code_challenge_method=row["code_challenge_method"],
                provider_code_verifier=provider_code_verifier,
                client_state=client_state,
                scopes=json.loads(row["scopes"]),
                expires_at=row["expires_at"],
                created_at=row["created_at"],
            )

    # Auth code helpers
    def _sync_store_auth_code(self, payload: dict[str, Any]) -> None:
        assert self._conn is not None
        with self._lock:
            self._conn.execute(
                """
                INSERT OR REPLACE INTO auth_codes
                (code, session_id, client_id, redirect_uri, code_challenge, code_challenge_method, scopes, expires_at, created_at)
                VALUES (:code, :session_id, :client_id, :redirect_uri, :code_challenge, :code_challenge_method, :scopes, :expires_at, :created_at)
                """,
                payload,
            )
            self._conn.commit()

    def _sync_load_auth_code(self, code: str) -> AuthCodeRecord | None:
        """Load auth code without consuming; expires-on-read."""
        assert self._conn is not None
        with self._lock:
            row = self._conn.execute("SELECT * FROM auth_codes WHERE code = ?", (code,)).fetchone()
            if not row:
                return None
            if row["expires_at"] < time.time():
                self._conn.execute("DELETE FROM auth_codes WHERE code = ?", (code,))
                self._conn.commit()
                return None
            return AuthCodeRecord(
                code=row["code"],
                session_id=row["session_id"],
                client_id=row["client_id"],
                redirect_uri=row["redirect_uri"],
                code_challenge=row["code_challenge"],
                code_challenge_method=row["code_challenge_method"],
                scopes=json.loads(row["scopes"]),
                expires_at=row["expires_at"],
                created_at=row["created_at"],
            )

    def _sync_delete_auth_code(self, code: str) -> None:
        assert self._conn is not None
        with self._lock:
            self._conn.execute("DELETE FROM auth_codes WHERE code = ?", (code,))
            self._conn.commit()

    def _sync_try_delete_auth_code(self, code: str) -> bool:
        """Attempt to delete an auth code; returns True if a row was removed."""
        assert self._conn is not None
        with self._lock:
            cur = self._conn.execute("DELETE FROM auth_codes WHERE code = ?", (code,))
            self._conn.commit()
            return cur.rowcount > 0

    # Session helpers
    def _sync_store_session(self, payload: dict[str, Any]) -> None:
        assert self._conn is not None
        with self._lock:
            self._conn.execute(
                """
                INSERT OR REPLACE INTO sessions
                (access_token_hash, access_token_encrypted, refresh_token_hash, refresh_token_encrypted,
                 session_id, provider, user_info, provider_access_token, provider_refresh_token,
                 provider_expires_at, expires_at, created_at)
                VALUES (:access_token_hash, :access_token_encrypted, :refresh_token_hash, :refresh_token_encrypted,
                        :session_id, :provider, :user_info, :provider_access_token, :provider_refresh_token,
                        :provider_expires_at, :expires_at, :created_at)
                """,
                payload,
            )
            self._conn.commit()

    def _sync_load_session_by_hash(self, access_token_hash: str) -> StoredSession | None:
        assert self._conn is not None
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM sessions WHERE access_token_hash = ?", (access_token_hash,)
            ).fetchone()
            if not row:
                return None

            if self._is_expired_row(row):
                self._conn.execute(
                    "DELETE FROM sessions WHERE access_token_hash = ?", (access_token_hash,)
                )
                self._conn.commit()
                return None

            return self._row_to_session(row)

    def _sync_load_session_by_id(self, session_id: str) -> StoredSession | None:
        assert self._conn is not None
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM sessions WHERE session_id = ? LIMIT 1", (session_id,)
            ).fetchone()
            if not row:
                return None

            if self._is_expired_row(row):
                self._conn.execute(
                    "DELETE FROM sessions WHERE access_token_hash = ?", (row["access_token_hash"],)
                )
                self._conn.commit()
                return None

            return self._row_to_session(row)

    def _sync_load_session_by_refresh_hash(self, refresh_token_hash: str) -> StoredSession | None:
        assert self._conn is not None
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM sessions WHERE refresh_token_hash = ?", (refresh_token_hash,)
            ).fetchone()
            if not row:
                return None

            if self._is_expired_row(row):
                self._conn.execute(
                    "DELETE FROM sessions WHERE access_token_hash = ?", (row["access_token_hash"],)
                )
                self._conn.commit()
                return None

            return self._row_to_session(row)

    def _sync_delete_session_by_hash(self, access_token_hash: str) -> None:
        assert self._conn is not None
        with self._lock:
            self._conn.execute(
                "DELETE FROM sessions WHERE access_token_hash = ?", (access_token_hash,)
            )
            self._conn.commit()

    # ── OAuth client helpers ───────────────────────────────────────────────────
    def _sync_store_client(self, payload: dict[str, Any]) -> None:
        assert self._conn is not None
        with self._lock:
            self._conn.execute(
                """
                INSERT OR REPLACE INTO oauth_clients
                (client_id, client_secret, token_endpoint_auth_method, redirect_uris, grant_types, response_types, scope, client_name, created_at)
                VALUES (:client_id, :client_secret, :token_endpoint_auth_method, :redirect_uris, :grant_types, :response_types, :scope, :client_name, :created_at)
                """,
                payload,
            )
            self._conn.commit()

    def _sync_load_client(self, client_id: str) -> ClientRecord | None:
        assert self._conn is not None
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM oauth_clients WHERE client_id = ? LIMIT 1", (client_id,)
            ).fetchone()
            if not row:
                return None
            try:
                return ClientRecord(
                    client_id=row["client_id"],
                    client_secret=self._decrypt(row["client_secret"]),
                    token_endpoint_auth_method=row["token_endpoint_auth_method"],
                    redirect_uris=json.loads(row["redirect_uris"]),
                    grant_types=json.loads(row["grant_types"]),
                    response_types=json.loads(row["response_types"]),
                    scope=row["scope"],
                    client_name=row["client_name"],
                    created_at=row["created_at"],
                )
            except Exception as exc:
                # Fail-closed: treat invalid persisted client rows as missing.
                # This prevents corrupted/legacy values from being interpreted as valid
                # OAuth client metadata.
                self._logger.warning(
                    "Failed to load stored OAuth client record; treating as missing",
                    extra={"client_id": row["client_id"], "error": type(exc).__name__},
                )
                return None

    def _sync_list_clients(self) -> list[ClientRecord]:
        assert self._conn is not None
        with self._lock:
            rows = self._conn.execute("SELECT * FROM oauth_clients").fetchall()
            records: list[ClientRecord] = []
            for row in rows:
                try:
                    records.append(
                        ClientRecord(
                            client_id=row["client_id"],
                            client_secret=self._decrypt(row["client_secret"]),
                            token_endpoint_auth_method=row["token_endpoint_auth_method"],
                            redirect_uris=json.loads(row["redirect_uris"]),
                            grant_types=json.loads(row["grant_types"]),
                            response_types=json.loads(row["response_types"]),
                            scope=row["scope"],
                            client_name=row["client_name"],
                            created_at=row["created_at"],
                        )
                    )
                except Exception as exc:
                    self._logger.warning(
                        "Skipping invalid stored OAuth client record",
                        extra={"client_id": row["client_id"], "error": type(exc).__name__},
                    )
                    continue
            return records

    def _sync_delete_client(self, client_id: str) -> None:
        assert self._conn is not None
        with self._lock:
            self._conn.execute("DELETE FROM oauth_clients WHERE client_id = ?", (client_id,))
            self._conn.commit()

    def _sync_cleanup_expired(self) -> dict[str, int]:
        assert self._conn is not None
        counts = {"states": 0, "auth_codes": 0, "sessions": 0}
        now = time.time()
        with self._lock:
            for table in counts:
                cur = self._conn.execute(
                    f"DELETE FROM {table} WHERE expires_at IS NOT NULL AND expires_at < ?",
                    (now,),
                )
                counts[table] = cur.rowcount
            self._conn.commit()
        return counts

    # ── Utility helpers ────────────────────────────────────────────────────────
    def _is_expired_row(self, row: sqlite3.Row) -> bool:
        return row["expires_at"] is not None and row["expires_at"] < time.time()

    def _row_to_session(self, row: sqlite3.Row) -> StoredSession:
        user_info_dict = json.loads(row["user_info"])
        user_info = UserInfo.model_validate(user_info_dict)

        # access_token_encrypted is NOT NULL in schema, so _decrypt should never return None
        access_token = self._decrypt(row["access_token_encrypted"])
        assert (
            access_token is not None
        ), "access_token_encrypted is NOT NULL, decryption should never return None"

        return StoredSession(
            session_id=row["session_id"],
            provider=row["provider"],
            user_info=user_info,
            access_token=access_token,
            refresh_token=(
                self._decrypt(row["refresh_token_encrypted"])
                if row["refresh_token_encrypted"]
                else None
            ),
            provider_access_token=(
                self._decrypt(row["provider_access_token"])
                if row["provider_access_token"]
                else None
            ),
            provider_refresh_token=(
                self._decrypt(row["provider_refresh_token"])
                if row["provider_refresh_token"]
                else None
            ),
            provider_expires_at=row["provider_expires_at"],
            expires_at=row["expires_at"],
            created_at=row["created_at"],
            issued_at=row["created_at"],
        )

    def _hash_token(self, token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    def _ensure_executor(self) -> ThreadPoolExecutor:
        if self._executor is None:
            self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="auth-store")
        return self._executor

    def _build_fernet(self, encryption_key: str | bytes) -> Fernet:
        """Normalize and validate a Fernet key (accepts bytes or str)."""
        key_bytes = (
            encryption_key.encode("utf-8") if isinstance(encryption_key, str) else encryption_key
        )
        try:
            return Fernet(key_bytes)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                "Invalid Fernet key: expected urlsafe base64-encoded 32-byte value. "
                "Pass the raw bytes from Fernet.generate_key() or the same value as a string."
            ) from exc

    def _encrypt(self, value: str | None) -> str | None:
        if value is None:
            return None
        if self._fernet:
            return self._fernet.encrypt(value.encode("utf-8")).decode("utf-8")
        if not self.allow_plaintext_tokens:
            raise ValueError(
                "Token encryption key is required; set allow_plaintext_tokens=True to store "
                "tokens in plaintext."
            )
        return value

    def _decrypt(self, value: str | None) -> str | None:
        if value is None:
            return None
        if self._fernet:
            try:
                return self._fernet.decrypt(value.encode("utf-8")).decode("utf-8")
            except InvalidToken as exc:
                raise ValueError("Failed to decrypt stored token") from exc
        if not self.allow_plaintext_tokens:
            raise ValueError(
                "Token encryption key is required to decrypt stored tokens; plaintext tokens "
                "are disabled."
            )
        return value

    def _serialize_session(self, record: StoredSession) -> dict[str, Any]:
        access_token = record.access_token
        refresh_token = record.refresh_token
        if record.expires_at is None:
            raise ValueError("Session expires_at is required for persistence.")
        return {
            "access_token_hash": self._hash_token(access_token),
            "access_token_encrypted": self._encrypt(access_token) or "",
            "refresh_token_hash": self._hash_token(refresh_token) if refresh_token else None,
            "refresh_token_encrypted": self._encrypt(refresh_token),
            "session_id": record.session_id,
            "provider": record.provider,
            "user_info": record.user_info.model_dump_json(),
            "provider_access_token": self._encrypt(record.provider_access_token),
            "provider_refresh_token": self._encrypt(record.provider_refresh_token),
            "provider_expires_at": record.provider_expires_at,
            "expires_at": record.expires_at,
            "created_at": record.created_at,
        }


__all__ = [
    "AuthCodeRecord",
    "ClientRecord",
    "SqliteTokenStore",
    "StateRecord",
    "StoredSession",
    "TokenStore",
]
