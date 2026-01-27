"""AuthService orchestrates issuer-mode OAuth using provider adapters and SessionManager."""

from __future__ import annotations

import base64
import hashlib
import logging
import secrets
import time
from collections.abc import Mapping, Sequence

from mxcp.sdk.auth.contracts import GrantResult, ProviderAdapter, ProviderError
from mxcp.sdk.auth.session_manager import SessionManager
from mxcp.sdk.auth.storage import AuthCodeRecord, StateRecord, StoredSession
from mxcp.sdk.models import SdkBaseModel

logger = logging.getLogger(__name__)


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
        client_state: str | None = None,
        extra_params: Mapping[str, str] | None = None,
    ) -> tuple[str, StateRecord]:
        """Create state and return provider authorize URL."""
        # Redirect URI validation is enforced by IssuerOAuthAuthorizationServer.authorize()
        # against persisted OAuth clients (TokenStore). AuthService should not depend on
        # in-memory client registries for security decisions.

        # PKCE note (two threat models):
        # - client ↔ MXCP PKCE protects the MXCP /token exchange from interception of the
        #   *MXCP* authorization code.
        # - MXCP ↔ provider PKCE protects the provider token exchange from interception of the
        #   *provider* authorization code delivered to our callback.
        #
        # These are independent. If the upstream provider supports PKCE, we enable it as
        # defense-in-depth regardless of whether the downstream MCP client uses PKCE.
        provider_code_verifier: str | None = None
        provider_code_challenge: str | None = None
        provider_code_challenge_method: str | None = None

        supports_s256 = any(
            method.upper() == "S256" for method in self.provider_adapter.pkce_methods_supported
        )
        if supports_s256:
            # Generate provider code_verifier (43-128 chars, base64url).
            # Never log this value (or the derived challenge).
            provider_code_verifier = (
                base64.urlsafe_b64encode(secrets.token_bytes(32)).decode("utf-8").rstrip("=")
            )
            # Generate provider code_challenge using S256.
            challenge_bytes = hashlib.sha256(provider_code_verifier.encode("utf-8")).digest()
            provider_code_challenge = (
                base64.urlsafe_b64encode(challenge_bytes).decode("utf-8").rstrip("=")
            )
            provider_code_challenge_method = "S256"

        # First touchpoint for a new client request: persist a one-time state
        # (client/redirect/PKCE/scopes). The client PKCE challenge is stored so
        # the MCP token handler can verify code_verifier during /token exchange.
        # No session is created until the IdP callback succeeds.
        state_record = await self.session_manager.create_state(
            client_id=client_id,
            redirect_uri=redirect_uri,
            code_challenge=code_challenge,  # MCP client's challenge (for MXCP ↔ client)
            code_challenge_method=code_challenge_method,
            provider_code_verifier=provider_code_verifier,  # Our verifier (for MXCP ↔ provider)
            client_state=client_state,  # Original state from MCP client
            scopes=scopes,
        )

        authorize_url = self.provider_adapter.build_authorize_url(
            redirect_uri=self.callback_url,
            state=state_record.state,
            scopes=scopes,
            code_challenge=provider_code_challenge,  # Use our challenge for provider PKCE
            code_challenge_method=provider_code_challenge_method,
            extra_params=extra_params,
        )
        logger.info(
            "authorize: issued state",
            extra={
                "client_id": client_id,
                "redirect_uri": redirect_uri,
                "scopes": list(scopes) if scopes else [],
            },
        )
        return authorize_url, state_record

    async def handle_callback(
        self, *, code: str, state: str
    ) -> tuple[AuthCodeRecord, StoredSession, str | None]:
        """Process provider callback, creating session and issuing auth code.

        Returns:
            Tuple of (auth_code, session, client_state) where client_state is the
            original state from the MCP client to be returned in the redirect.
        """
        # Resume the flow using the stored state. This is the first moment we
        # create an MCP session—only after the provider code exchange succeeds.
        state_record = await self.session_manager.consume_state(state)
        if not state_record:
            logger.warning("handle_callback: state not found or expired")
            raise ProviderError("invalid_state", "State not found or expired", status_code=400)

        if not state_record.redirect_uri:
            raise ProviderError(
                "invalid_state",
                "State record missing redirect_uri",
                status_code=400,
            )

        # Use the provider's code_verifier from state for upstream PKCE.
        grant: GrantResult = await self.provider_adapter.exchange_code(
            code=code,
            redirect_uri=self.callback_url,
            code_verifier=state_record.provider_code_verifier,  # Use stored provider verifier
            scopes=state_record.scopes,
        )

        user_info = await self.provider_adapter.fetch_user_info(access_token=grant.access_token)

        # We have provider user info; this is the right place to derive MXCP scopes
        # (via a shared mapper) and persist them in the session.

        access_ttl = None
        if grant.expires_at:
            access_ttl = max(0, int(grant.expires_at - time.time()))

        session = await self.session_manager.issue_session(
            provider=self.provider_adapter.provider_name,
            user_info=user_info,
            provider_access_token=grant.access_token,
            provider_refresh_token=grant.refresh_token,
            provider_expires_at=grant.expires_at,
            access_token_ttl_seconds=access_ttl,
        )

        auth_code = await self.session_manager.create_auth_code(
            session_id=session.session_id,
            client_id=state_record.client_id,
            redirect_uri=state_record.redirect_uri,
            code_challenge=state_record.code_challenge,
            code_challenge_method=state_record.code_challenge_method,
            scopes=grant.provider_scopes_granted,
        )

        return auth_code, session, state_record.client_state

    async def exchange_token(
        self,
        *,
        auth_code: str,
        client_id: str | None = None,
        redirect_uri: str | None = None,
    ) -> AccessTokenResponse:
        """Exchange an auth code for MXCP tokens.

        Note: Client PKCE verification is handled upstream by the MCP token handler
        before this method is called. This method focuses on business logic:
        validating the code, checking client/redirect binding, and issuing tokens.

        Args:
            auth_code: The authorization code to exchange
            client_id: Client ID for validation
            redirect_uri: Redirect URI for validation
        """
        code_record = await self.session_manager.load_auth_code(auth_code)
        if not code_record:
            raise ProviderError(
                "invalid_grant", "Authorization code invalid or expired", status_code=400
            )

        # Enforce client and redirect binding if provided or stored.
        if code_record.client_id and (not client_id or client_id != code_record.client_id):
            raise ProviderError("invalid_grant", "Client mismatch for authorization code", 400)
        if code_record.redirect_uri and (
            not redirect_uri or redirect_uri != code_record.redirect_uri
        ):
            raise ProviderError("invalid_grant", "Redirect URI mismatch", 400)

        # PKCE verification is handled upstream by the MCP token handler
        # before exchange_authorization_code() is called
        deleted = await self.session_manager.try_delete_auth_code(auth_code)
        if not deleted:
            raise ProviderError("invalid_grant", "Authorization code already used", status_code=400)

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
