"""AuthService orchestrates issuer-mode OAuth using provider adapters and SessionManager."""

from __future__ import annotations

import base64
import hashlib
import logging
import secrets
import time
from collections.abc import Mapping, Sequence
from fnmatch import fnmatch

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
        client_registry: Mapping[str, Sequence[str]] | None = None,
        allowed_redirect_patterns: Sequence[str] | None = None,
    ):
        self.provider_adapter = provider_adapter
        self.session_manager = session_manager
        self.callback_url = callback_url.rstrip("/")
        self.client_registry = {k: list(v) for k, v in (client_registry or {}).items()}
        self.allowed_redirect_patterns = list(allowed_redirect_patterns or [])

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
        self._validate_client_redirect(client_id, redirect_uri)

        # Generate PKCE pair for provider (Google) if needed
        # The MCP client's code_challenge is for MXCP ↔ MCP client flow
        # We need our own PKCE pair for MXCP ↔ Google flow
        provider_code_verifier: str | None = None
        provider_code_challenge: str | None = None
        provider_code_challenge_method: str | None = None

        if code_challenge:  # If MCP client uses PKCE, we should too with Google
            # Generate code_verifier (43-128 chars, base64url)
            provider_code_verifier = (
                base64.urlsafe_b64encode(secrets.token_bytes(32)).decode("utf-8").rstrip("=")
            )
            # Generate code_challenge using S256
            challenge_bytes = hashlib.sha256(provider_code_verifier.encode("utf-8")).digest()
            provider_code_challenge = (
                base64.urlsafe_b64encode(challenge_bytes).decode("utf-8").rstrip("=")
            )
            provider_code_challenge_method = "S256"

        # First touchpoint for a new client request: persist a one-time state
        # (client/redirect/PKCE/scopes). No session is created until the IdP
        # callback succeeds.
        state_record = await self.session_manager.create_state(
            client_id=client_id,
            redirect_uri=redirect_uri,
            code_challenge=code_challenge,  # MCP client's challenge (for MXCP ↔ client)
            code_challenge_method=code_challenge_method,
            provider_code_verifier=provider_code_verifier,  # Our verifier (for MXCP ↔ Google)
            client_state=client_state,  # Original state from MCP client
            scopes=scopes,
        )

        authorize_url = self.provider_adapter.build_authorize_url(
            redirect_uri=self.callback_url,
            state=state_record.state,
            scopes=scopes,
            code_challenge=provider_code_challenge,  # Use our challenge for Google
            code_challenge_method=provider_code_challenge_method,
            extra_params=extra_params,
        )
        logger.info(
            "authorize: issued state",
            extra={
                "client_id": client_id,
                "redirect_uri": redirect_uri,
                "state": state_record.state,
                "scopes": list(scopes) if scopes else [],
            },
        )
        return authorize_url, state_record

    async def handle_callback(
        self, *, code: str, state: str, code_verifier: str | None = None
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
            logger.warning("handle_callback: state not found or expired", extra={"state": state})
            raise ProviderError("invalid_state", "State not found or expired", status_code=400)

        # Re-validate client and redirect from the stored state.
        self._validate_client_redirect(state_record.client_id, state_record.redirect_uri)

        # Use the provider's code_verifier (for Google), not the MCP client's
        grant: GrantResult = await self.provider_adapter.exchange_code(
            code=code,
            redirect_uri=self.callback_url,
            code_verifier=state_record.provider_code_verifier,  # Use stored provider verifier
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
        code_verifier: str | None = None,
        client_id: str | None = None,
        redirect_uri: str | None = None,
    ) -> AccessTokenResponse:
        """Exchange an auth code for MXCP tokens.

        Note: PKCE verification is handled upstream by the MCP token handler
        before this method is called. This method focuses on business logic:
        validating the code, checking client/redirect binding, and issuing tokens.

        Args:
            auth_code: The authorization code to exchange
            code_verifier: Deprecated - PKCE is verified upstream by MCP framework
            client_id: Client ID for validation
            redirect_uri: Redirect URI for validation
        """
        code_record = await self.session_manager.load_auth_code(auth_code)
        if not code_record:
            raise ProviderError(
                "invalid_grant", "Authorization code invalid or expired", status_code=400
            )

        # Enforce client and redirect binding if provided or stored.
        if code_record.client_id and client_id and client_id != code_record.client_id:
            raise ProviderError("invalid_grant", "Client mismatch for authorization code", 400)
        if redirect_uri and code_record.redirect_uri and redirect_uri != code_record.redirect_uri:
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

    def _verify_pkce(self, code_record: AuthCodeRecord, code_verifier: str | None) -> None:
        """Enforce PKCE at MXCP auth-code redemption time.

        Note: In issuer mode, PKCE verification is handled upstream by the MCP
        token handler before exchange_token() is called. This method is kept
        for potential future use cases or testing scenarios where direct PKCE
        verification might be needed.
        """
        if not code_record.code_challenge:
            return
        if code_verifier is None:
            raise ProviderError(
                "invalid_grant",
                "code_verifier is required for this authorization code",
                status_code=400,
            )

        method = (code_record.code_challenge_method or "plain").upper()
        if method == "PLAIN":
            valid = code_verifier == code_record.code_challenge
        elif method == "S256":
            digest = hashlib.sha256(code_verifier.encode("utf-8")).digest()
            computed = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("utf-8")
            valid = computed == code_record.code_challenge
        else:
            raise ProviderError(
                "invalid_request",
                f"Unsupported code_challenge_method {code_record.code_challenge_method}",
                status_code=400,
            )

        if not valid:
            raise ProviderError("invalid_grant", "PKCE verification failed", status_code=400)

    def _validate_client_redirect(self, client_id: str | None, redirect_uri: str | None) -> None:
        """Ensure client is registered and redirect URI matches allowed patterns."""
        if not client_id or not redirect_uri:
            # Backward-compatible: if no allowlists configured, allow all.
            if not self.client_registry and not self.allowed_redirect_patterns:
                return
            raise ProviderError("invalid_request", "client_id and redirect_uri are required", 400)

        patterns = self.client_registry.get(client_id)
        if patterns is None:
            # DCR-friendly: fall back to global allowed patterns if provided.
            if not self.allowed_redirect_patterns:
                # If no allowlists at all, allow all (legacy behavior).
                if not self.client_registry:
                    return
                raise ProviderError(
                    "invalid_client", f"Unknown client_id {client_id}", status_code=400
                )
            patterns = self.allowed_redirect_patterns

        matched = any(fnmatch(redirect_uri, pattern) for pattern in patterns)
        if not matched:
            raise ProviderError(
                "invalid_request",
                f"redirect_uri not allowed for client {client_id}",
                status_code=400,
            )


__all__ = ["AccessTokenResponse", "AuthService"]
