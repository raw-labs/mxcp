"""AuthService orchestrates issuer-mode OAuth using provider adapters and SessionManager."""

from __future__ import annotations

import time
from typing import Mapping, Sequence

from mxcp.sdk.auth.contracts import GrantResult, ProviderAdapter, ProviderError
from mxcp.sdk.auth.session_manager import SessionManager
from mxcp.sdk.auth.storage import AuthCodeRecord, StateRecord, StoredSession
from mxcp.sdk.models import SdkBaseModel


class AccessTokenResponse(SdkBaseModel):
    """Response returned when exchanging an auth code for MXCP tokens."""

    access_token: str
    token_type: str = "Bearer"
    expires_in: int | None = None
    refresh_token: str | None = None
    provider_access_token: str | None = None
    provider_refresh_token: str | None = None
    provider_expires_at: float | None = None


class AuthService:
    """Issuer-mode auth coordinator."""

    def __init__(
        self,
        *,
        provider_adapter: ProviderAdapter,
        session_manager: SessionManager,
        callback_url: str,
    ):
        self.provider_adapter = provider_adapter
        self.session_manager = session_manager
        self.callback_url = callback_url.rstrip("/")

    async def authorize(
        self,
        *,
        client_id: str,
        redirect_uri: str,
        scopes: Sequence[str],
        code_challenge: str | None = None,
        code_challenge_method: str | None = None,
        extra_params: Mapping[str, str] | None = None,
    ) -> tuple[str, StateRecord]:
        """Create state and return provider authorize URL."""
        state_record = await self.session_manager.create_state(
            client_id=client_id,
            redirect_uri=redirect_uri,
            code_challenge=code_challenge,
            code_challenge_method=code_challenge_method,
            scopes=scopes,
        )

        authorize_url = self.provider_adapter.build_authorize_url(
            redirect_uri=self.callback_url,
            state=state_record.state,
            scopes=scopes,
            code_challenge=code_challenge,
            code_challenge_method=code_challenge_method,
            extra_params=extra_params,
        )
        return authorize_url, state_record

    async def handle_callback(
        self, *, code: str, state: str, code_verifier: str | None = None
    ) -> tuple[AuthCodeRecord, StoredSession]:
        """Process provider callback, creating session and issuing auth code."""
        state_record = await self.session_manager.consume_state(state)
        if not state_record:
            raise ProviderError("invalid_state", "State not found or expired", status_code=400)

        grant: GrantResult = await self.provider_adapter.exchange_code(
            code=code,
            redirect_uri=self.callback_url,
            code_verifier=code_verifier,
            scopes=state_record.scopes,
        )

        user_info = await self.provider_adapter.fetch_user_info(access_token=grant.access_token)

        access_ttl = None
        if grant.expires_at:
            access_ttl = max(0, int(grant.expires_at - time.time()))

        session = await self.session_manager.issue_session(
            provider=self.provider_adapter.provider_name,
            user_info=user_info,
            provider_access_token=grant.access_token,
            provider_refresh_token=grant.refresh_token,
            provider_expires_at=grant.expires_at,
            scopes=grant.provider_scopes_granted,
            access_token_ttl_seconds=access_ttl,
        )

        auth_code = await self.session_manager.create_auth_code(
            session_id=session.session_id,
            redirect_uri=state_record.redirect_uri,
            scopes=grant.provider_scopes_granted,
        )

        return auth_code, session

    async def exchange_token(self, *, auth_code: str) -> AccessTokenResponse:
        """Exchange an auth code for MXCP tokens."""
        code_record = await self.session_manager.consume_auth_code(auth_code)
        if not code_record:
            raise ProviderError(
                "invalid_grant", "Authorization code invalid or expired", status_code=400
            )

        session = await self.session_manager.get_session_by_id(code_record.session_id)
        if not session:
            raise ProviderError(
                "invalid_grant", "Session not found for authorization code", status_code=400
            )

        expires_in = None
        if session.expires_at:
            expires_in = max(0, int(session.expires_at - time.time()))

        return AccessTokenResponse(
            access_token=session.access_token,
            refresh_token=session.refresh_token,
            expires_in=expires_in,
            provider_access_token=session.provider_access_token,
            provider_refresh_token=session.provider_refresh_token,
            provider_expires_at=session.provider_expires_at,
        )


__all__ = ["AccessTokenResponse", "AuthService"]
