"""Session manager built on top of the TokenStore."""

from __future__ import annotations

import secrets
import time
from typing import Sequence

from mxcp.sdk.auth.contracts import UserInfo
from mxcp.sdk.auth.storage import (
    AuthCodeRecord,
    StateRecord,
    StoredSession,
    TokenStore,
)


class SessionManager:
    """Orchestrates state, auth-code, and session lifecycles."""

    def __init__(
        self,
        token_store: TokenStore,
        *,
        state_ttl_seconds: int = 300,
        auth_code_ttl_seconds: int = 300,
        access_token_ttl_seconds: int = 3600,
    ):
        self.token_store = token_store
        self.state_ttl_seconds = state_ttl_seconds
        self.auth_code_ttl_seconds = auth_code_ttl_seconds
        self.access_token_ttl_seconds = access_token_ttl_seconds

    async def create_state(
        self,
        *,
        client_id: str | None,
        redirect_uri: str | None,
        code_challenge: str | None,
        code_challenge_method: str | None,
        scopes: Sequence[str] | None = None,
        ttl_seconds: int | None = None,
    ) -> StateRecord:
        state = secrets.token_urlsafe(16)
        now = time.time()
        record = StateRecord(
            state=state,
            client_id=client_id,
            redirect_uri=redirect_uri,
            code_challenge=code_challenge,
            code_challenge_method=code_challenge_method,
            scopes=list(scopes) if scopes is not None else None,
            expires_at=now + (ttl_seconds or self.state_ttl_seconds),
            created_at=now,
        )
        await self.token_store.store_state(record)
        return record

    async def consume_state(self, state: str) -> StateRecord | None:
        return await self.token_store.consume_state(state)

    async def create_auth_code(
        self,
        *,
        session_id: str,
        redirect_uri: str | None,
        code_challenge: str | None,
        code_challenge_method: str | None,
        scopes: Sequence[str] | None = None,
        ttl_seconds: int | None = None,
    ) -> AuthCodeRecord:
        code = f"mcp_{secrets.token_hex(16)}"
        now = time.time()
        record = AuthCodeRecord(
            code=code,
            session_id=session_id,
            redirect_uri=redirect_uri,
            code_challenge=code_challenge,
            code_challenge_method=code_challenge_method,
            scopes=list(scopes) if scopes is not None else None,
            expires_at=now + (ttl_seconds or self.auth_code_ttl_seconds),
            created_at=now,
        )
        await self.token_store.store_auth_code(record)
        return record

    async def load_auth_code(self, code: str) -> AuthCodeRecord | None:
        return await self.token_store.load_auth_code(code)

    async def delete_auth_code(self, code: str) -> None:
        await self.token_store.delete_auth_code(code)

    async def try_delete_auth_code(self, code: str) -> bool:
        return await self.token_store.try_delete_auth_code(code)

    async def issue_session(
        self,
        *,
        provider: str,
        user_info: UserInfo,
        provider_access_token: str | None,
        provider_refresh_token: str | None,
        provider_expires_at: float | None,
        scopes: Sequence[str] | None,
        access_token: str | None = None,
        refresh_token: str | None = None,
        session_id: str | None = None,
        access_token_ttl_seconds: int | None = None,
    ) -> StoredSession:
        now = time.time()
        session = StoredSession(
            session_id=session_id or secrets.token_hex(16),
            provider=provider,
            user_info=user_info,
            access_token=access_token or f"mcp_{secrets.token_hex(32)}",
            refresh_token=refresh_token or f"mcp_refresh_{secrets.token_hex(32)}",
            provider_access_token=provider_access_token,
            provider_refresh_token=provider_refresh_token,
            provider_expires_at=provider_expires_at,
            expires_at=now + (access_token_ttl_seconds or self.access_token_ttl_seconds),
            created_at=now,
            issued_at=now,
            scopes=list(scopes) if scopes is not None else None,
        )
        await self.token_store.store_session(session)
        return session

    async def get_session(self, access_token: str) -> StoredSession | None:
        return await self.token_store.load_session_by_token(access_token)

    async def get_session_by_id(self, session_id: str) -> StoredSession | None:
        return await self.token_store.load_session_by_id(session_id)

    async def revoke_session(self, access_token: str) -> None:
        await self.token_store.delete_session_by_token(access_token)

    async def cleanup(self) -> dict[str, int]:
        return await self.token_store.cleanup_expired()


__all__ = ["SessionManager"]
