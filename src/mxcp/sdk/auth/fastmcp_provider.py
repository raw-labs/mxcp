"""FastMCP OAuth provider adapter.

This module provides an adapter that bridges the MXCP auth architecture
to FastMCP's OAuthAuthorizationServerProvider interface.

FastMCP expects an auth_server_provider that handles OAuth token endpoints.
This adapter implements that interface using SessionManager for token storage.
"""

import logging
import secrets
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from mcp.server.auth.provider import (
    AccessToken,
    AuthorizationCode,
    AuthorizationParams,
    OAuthAuthorizationServerProvider,
    RefreshToken,
    construct_redirect_uri,
)
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken
from pydantic import AnyUrl

if TYPE_CHECKING:
    from .adapter import ProviderAdapter
    from .sessions import SessionManager

logger = logging.getLogger(__name__)


@dataclass
class MXCPAuthCode:
    """MXCP authorization code data."""

    code: str
    client_id: str
    redirect_uri: str
    redirect_uri_provided_explicitly: bool
    scopes: list[str]
    expires_at: float
    code_challenge: str | None = None


@dataclass
class MXCPClient:
    """MXCP OAuth client information."""

    client_id: str
    client_secret: str | None
    redirect_uris: list[str] = field(default_factory=list)
    name: str | None = None


class FastMCPAuthProvider(OAuthAuthorizationServerProvider[MXCPClient, MXCPAuthCode, str]):
    """Adapter that implements FastMCP's OAuthAuthorizationServerProvider.

    This bridges MXCP's SessionManager-based token storage to the
    interface required by FastMCP for OAuth endpoints.
    """

    def __init__(
        self,
        session_manager: "SessionManager",
        provider_adapter: "ProviderAdapter | None" = None,
    ):
        """Initialize the FastMCP auth provider adapter.

        Args:
            session_manager: SessionManager for token storage.
            provider_adapter: Optional provider adapter for user context.
        """
        self.session_manager = session_manager
        self.provider_adapter = provider_adapter

        # In-memory storage for auth codes and clients
        # (auth codes are short-lived, clients are configured)
        self._auth_codes: dict[str, MXCPAuthCode] = {}
        self._clients: dict[str, MXCPClient] = {}

    async def get_client(self, client_id: str) -> MXCPClient | None:
        """Get OAuth client by ID."""
        return self._clients.get(client_id)

    async def register_client(self, client_info: OAuthClientInformationFull) -> MXCPClient:
        """Register a new OAuth client."""
        client = MXCPClient(
            client_id=client_info.client_id,
            client_secret=client_info.client_secret,
            redirect_uris=[str(uri) for uri in (client_info.redirect_uris or [])],
            name=client_info.client_name,
        )
        self._clients[client.client_id] = client
        logger.info(f"Registered OAuth client: {client.client_id}")
        return client

    async def authorize(
        self,
        client: MXCPClient,
        params: AuthorizationParams,
    ) -> str:
        """Handle authorization request.

        This creates an authorization code and returns the redirect URL.
        In MXCP, the actual IdP authorization is triggered separately via
        the provider adapter.
        """
        # Generate authorization code
        code = f"mcp_{secrets.token_hex(16)}"

        # Store the code
        auth_code = MXCPAuthCode(
            code=code,
            client_id=client.client_id,
            redirect_uri=str(params.redirect_uri) if params.redirect_uri else "",
            redirect_uri_provided_explicitly=params.redirect_uri_provided_explicitly,
            scopes=list(params.scopes) if params.scopes else [],
            expires_at=time.time() + 600,  # 10 minute expiry
            code_challenge=params.code_challenge,
        )
        self._auth_codes[code] = auth_code

        # Create OAuth state in session manager if we have a provider
        if self.session_manager and self.provider_adapter:
            callback_url = str(params.redirect_uri) if params.redirect_uri else ""
            oauth_state = self.session_manager.create_oauth_state(
                client_id=client.client_id,
                redirect_uri=callback_url,
                callback_url=callback_url,
                code_challenge=params.code_challenge,
                provider=self.provider_adapter.provider_name,
                scopes=list(params.scopes) if params.scopes else [],
            )

            # Build the IdP authorization URL
            authorize_url = await self.provider_adapter.build_authorize_url(
                redirect_uri=callback_url,
                state=oauth_state.state,
                scopes=list(params.scopes) if params.scopes else None,
                code_challenge=params.code_challenge,
            )
            return authorize_url

        # Fallback: construct redirect with our code
        redirect_uri = construct_redirect_uri(
            params.redirect_uri or AnyUrl("http://localhost/callback"),
            code,
            params.state,
        )
        return str(redirect_uri)

    async def load_authorization_code(
        self,
        client: MXCPClient,
        authorization_code: str,
    ) -> MXCPAuthCode | None:
        """Load and validate an authorization code."""
        auth_code = self._auth_codes.get(authorization_code)
        if not auth_code:
            return None

        # Check expiry
        if time.time() > auth_code.expires_at:
            self._auth_codes.pop(authorization_code, None)
            return None

        # Verify client
        if auth_code.client_id != client.client_id:
            return None

        return auth_code

    async def exchange_authorization_code(
        self,
        client: MXCPClient,
        authorization_code: MXCPAuthCode,
        code_verifier: str | None,
    ) -> OAuthToken:
        """Exchange authorization code for tokens."""
        # Remove the auth code (one-time use)
        self._auth_codes.pop(authorization_code.code, None)

        # Create a session
        session = await self.session_manager.create_session(
            client_id=client.client_id,
            scopes=authorization_code.scopes,
            expires_in=3600,  # 1 hour default
        )

        return OAuthToken(
            access_token=session.mxcp_token,
            token_type="Bearer",
            expires_in=3600,
            scope=" ".join(authorization_code.scopes) if authorization_code.scopes else None,
        )

    async def load_access_token(self, token: str) -> AccessToken | None:
        """Load and validate an access token."""
        session = await self.session_manager.get_session(token)
        if not session:
            return None

        return AccessToken(
            token=token,
            client_id=session.client_id,
            scopes=session.scopes,
            expires_at=int(session.expires_at) if session.expires_at else None,
        )

    async def load_refresh_token(
        self,
        client: MXCPClient,
        refresh_token: str,
    ) -> RefreshToken | None:
        """Load a refresh token (not yet implemented)."""
        # Refresh tokens are handled at the session level
        return None

    async def exchange_refresh_token(
        self,
        client: MXCPClient,
        refresh_token: RefreshToken,
        scopes: list[str],
    ) -> OAuthToken:
        """Exchange refresh token for new tokens (not yet implemented)."""
        raise NotImplementedError("Refresh token exchange not yet implemented")

    async def revoke_token(
        self,
        token: str,
        token_type_hint: str | None = None,
    ) -> None:
        """Revoke a token."""
        await self.session_manager.delete_session(token)
        logger.info("Token revoked")


