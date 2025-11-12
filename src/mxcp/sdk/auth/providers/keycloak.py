"""Keycloak OAuth provider implementation for MXCP authentication."""

import base64
import hashlib
import logging
import secrets
from dataclasses import dataclass
from typing import Any, cast
from urllib.parse import urlencode

from mcp.server.auth.provider import AuthorizationParams
from mcp.shared._httpx_utils import create_mcp_http_client
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse, Response

from .._types import (
    ExternalUserInfo,
    HttpTransportConfig,
    KeycloakAuthConfig,
    RefreshTokenResponse,
    StateMeta,
    UserContext,
)
from ..base import ExternalOAuthHandler, GeneralOAuthAuthorizationServer
from ..url_utils import URLBuilder

logger = logging.getLogger(__name__)


@dataclass
class KeycloakStateMeta(StateMeta):
    """Extended state metadata for Keycloak OAuth flow with PKCE support."""

    keycloak_code_verifier: str | None = None  # For Keycloak token exchange


def _generate_pkce_pair() -> tuple[str, str]:
    """Generate PKCE code verifier and challenge pair.

    Returns:
        Tuple of (code_verifier, code_challenge)
    """
    # Generate a cryptographically random code_verifier (43-128 chars)
    code_verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode("utf-8").rstrip("=")

    # Generate code_challenge using S256 method
    challenge_bytes = hashlib.sha256(code_verifier.encode("utf-8")).digest()
    code_challenge = base64.urlsafe_b64encode(challenge_bytes).decode("utf-8").rstrip("=")

    return code_verifier, code_challenge


class KeycloakOAuthHandler(ExternalOAuthHandler):
    """Keycloak OAuth provider implementation."""

    def __init__(
        self,
        keycloak_config: KeycloakAuthConfig,
        transport_config: HttpTransportConfig | None = None,
        host: str = "localhost",
        port: int = 8000,
    ):
        """Initialize Keycloak OAuth handler.

        Args:
            keycloak_config: Keycloak-specific OAuth configuration
            transport_config: HTTP transport configuration for URL building
            host: The server host for callback URLs
            port: The server port for callback URLs
        """
        logger.info(f"KeycloakOAuthHandler init: {keycloak_config}")

        # Required fields are enforced by TypedDict structure
        self.client_id = keycloak_config["client_id"]
        self.client_secret = keycloak_config["client_secret"]
        self.realm = keycloak_config["realm"]
        self.server_url = keycloak_config["server_url"].rstrip("/")
        self.scope = keycloak_config.get("scope", "openid profile email offline_access")
        self._callback_path = keycloak_config["callback_path"]

        # Construct Keycloak OAuth endpoints
        realm_base = f"{self.server_url}/realms/{self.realm}/protocol/openid-connect"
        self.auth_url = f"{realm_base}/auth"
        self.token_url = f"{realm_base}/token"
        self.userinfo_url = f"{realm_base}/userinfo"

        self.host = host
        self.port = port

        # Create URL builder
        self.url_builder = URLBuilder(transport_config)

        # Internal state management
        self._state_store: dict[str, KeycloakStateMeta] = {}

    @property
    def callback_path(self) -> str:
        """Return the callback path for OAuth flow."""
        return self._callback_path

    def get_authorize_url(self, client_id: str, params: AuthorizationParams) -> str:
        """Generate the authorization URL for Keycloak."""
        state = params.state or secrets.token_hex(16)

        # Use URL builder to construct callback URL with proper scheme detection
        full_callback_url = self.url_builder.build_callback_url(
            self._callback_path, host=self.host, port=self.port
        )

        # Generate PKCE pair for Keycloak (always required)
        keycloak_code_verifier, keycloak_code_challenge = _generate_pkce_pair()

        # Store the original redirect URI, callback URL, and both PKCE flows
        self._state_store[state] = KeycloakStateMeta(
            redirect_uri=str(params.redirect_uri),
            code_challenge=params.code_challenge,  # MCP client's original (for internal MCP flow)
            redirect_uri_provided_explicitly=params.redirect_uri_provided_explicitly,
            client_id=client_id,
            callback_url=full_callback_url,
            keycloak_code_verifier=keycloak_code_verifier,  # For Keycloak token exchange
        )

        logger.info(
            f"Keycloak OAuth authorize URL: client_id={self.client_id}, redirect_uri={full_callback_url}, scope={self.scope}"
        )

        # Prepare authorization parameters
        auth_params = {
            "client_id": self.client_id,
            "response_type": "code",
            "redirect_uri": full_callback_url,
            "scope": self.scope,
            "state": state,
            "code_challenge": keycloak_code_challenge,  # Always use our generated challenge for Keycloak
            "code_challenge_method": "S256",
        }

        # Note: prompt and login_hint are not standard AuthorizationParams attributes
        # They would need to be passed through a different mechanism if needed

        # Construct the full authorization URL
        auth_url = f"{self.auth_url}?{urlencode(auth_params)}"
        logger.debug(f"Generated authorization URL: {auth_url}")

        return auth_url

    async def exchange_code(
        self, code: str, state: str
    ) -> tuple[ExternalUserInfo, KeycloakStateMeta]:
        """Exchange authorization code for tokens."""
        # Validate state parameter and get metadata
        state_meta = self._get_state_metadata(state)

        # Use the stored callback URL from state metadata
        full_callback_url = state_meta.callback_url
        if not full_callback_url:
            # Fallback to constructing it using URL builder
            full_callback_url = self.url_builder.build_callback_url(
                self._callback_path, host=self.host, port=self.port
            )

        logger.info(
            f"Keycloak OAuth token exchange: code={code[:10]}..., redirect_uri={full_callback_url}"
        )

        # Prepare token exchange request
        token_data = {
            "grant_type": "authorization_code",
            "code": code,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "redirect_uri": full_callback_url,
        }

        # Add Keycloak-specific PKCE code_verifier (required for PKCE flow)
        if state_meta.keycloak_code_verifier:
            token_data["code_verifier"] = state_meta.keycloak_code_verifier
            logger.debug("Added Keycloak PKCE code_verifier to token exchange request")

        # Exchange code for tokens
        async with create_mcp_http_client() as client:
            response = await client.post(
                self.token_url,
                data=token_data,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )

            if response.status_code != 200:
                logger.error(f"Token exchange failed: {response.status_code} - {response.text}")
                raise HTTPException(400, "Failed to exchange authorization code")

            token_response = response.json()

        # Extract the access token and refresh token
        access_token = token_response.get("access_token")
        if not access_token:
            raise HTTPException(400, "No access token received")

        refresh_token = token_response.get("refresh_token")  # May be None if not requested

        # Get user info using the access token
        user_profile = await self._get_user_info(access_token)

        # Map Keycloak claims to ExternalUserInfo
        # Keycloak typically uses 'sub' as the unique user identifier
        user_id = user_profile.get("sub", "")

        # Extract scopes from the token response or use default
        scopes = token_response.get("scope", self.scope).split()

        logger.info(f"Keycloak OAuth token exchange successful for user: {user_id}")

        user_info = ExternalUserInfo(
            id=user_id,
            scopes=scopes,
            raw_token=access_token,
            provider="keycloak",
            refresh_token=refresh_token,
        )

        return user_info, state_meta

    async def _get_user_info(self, access_token: str) -> dict[str, Any]:
        """Get user information from Keycloak userinfo endpoint."""
        async with create_mcp_http_client() as client:
            response = await client.get(
                self.userinfo_url, headers={"Authorization": f"Bearer {access_token}"}
            )

            if response.status_code != 200:
                logger.error(f"Failed to get user info: {response.status_code}")
                # Preserve the original status code (e.g., 401 for expired tokens)
                raise HTTPException(response.status_code, "Failed to get user information")

            return cast(dict[str, Any], response.json())

    async def refresh_access_token(self, refresh_token: str) -> RefreshTokenResponse:
        """Refresh an expired access token using the refresh token.

        Args:
            refresh_token: The refresh token to use for getting a new access token

        Returns:
            RefreshTokenResponse with new access_token and possibly new refresh_token

        Raises:
            HTTPException: If refresh fails
        """
        refresh_data = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
        }

        async with create_mcp_http_client() as client:
            response = await client.post(
                self.token_url,
                data=refresh_data,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )

            if response.status_code != 200:
                logger.error(f"Token refresh failed: {response.status_code} - {response.text}")
                raise HTTPException(400, "Failed to refresh access token")

            # Parse and validate response using Pydantic model
            response_data = response.json()
            return RefreshTokenResponse(**response_data)

    def _get_state_metadata(self, state: str) -> KeycloakStateMeta:
        """Return metadata stored for a given state."""
        state_meta = self._state_store.get(state)
        if not state_meta:
            raise HTTPException(400, "Invalid state parameter")
        return state_meta

    def cleanup_state(self, state: str) -> None:
        """Clean up state after successful authentication."""
        self._state_store.pop(state, None)

    async def on_callback(
        self, request: Request, provider: "GeneralOAuthAuthorizationServer"
    ) -> Response:
        """Handle the OAuth callback from Keycloak."""
        # Extract code and state from query parameters
        code = request.query_params.get("code")
        state = request.query_params.get("state")
        error = request.query_params.get("error")

        # Handle errors from Keycloak
        if error:
            error_description = request.query_params.get("error_description", "Unknown error")
            logger.error(f"Keycloak OAuth error: {error} - {error_description}")
            return HTMLResponse(
                content=f"<h1>Authentication Failed</h1><p>{error_description}</p>", status_code=400
            )

        if not code or not state:
            return HTMLResponse(
                content="<h1>Authentication Failed</h1><p>Missing code or state parameter</p>",
                status_code=400,
            )

        try:
            # Handle the callback and get the redirect URL
            redirect_url = await provider.handle_callback(code, state)
            return RedirectResponse(url=redirect_url)
        except HTTPException as e:
            logger.error(f"Callback handling failed: {e.detail}")
            return HTMLResponse(
                content=f"<h1>Authentication Failed</h1><p>{e.detail}</p>",
                status_code=e.status_code,
            )
        except Exception as e:
            logger.error(f"Unexpected error during callback: {e}")
            return HTMLResponse(
                content="<h1>Authentication Failed</h1><p>An unexpected error occurred</p>",
                status_code=500,
            )

    async def get_user_context(self, token: str) -> UserContext:
        """Get standardized user context from Keycloak.

        Args:
            token: OAuth access token for the user

        Returns:
            UserContext with standardized user information

        Raises:
            HTTPException: If token is invalid or user info cannot be retrieved
        """
        try:
            # Get user info from Keycloak
            user_profile = await self._get_user_info(token)

            # Map Keycloak claims to UserContext
            # Keycloak uses standard OIDC claims
            return UserContext(
                provider="keycloak",
                user_id=user_profile.get("sub", ""),
                username=user_profile.get("preferred_username", user_profile.get("email", "")),
                email=user_profile.get("email"),
                name=user_profile.get("name"),
                avatar_url=user_profile.get("picture"),
                raw_profile=user_profile,
                external_token=token,
            )
        except HTTPException:
            # Re-raise HTTP exceptions (e.g., 401 for token refresh) with original status code
            raise
        except Exception as e:
            logger.error(f"Failed to get user context: {e}")
            raise HTTPException(500, f"Failed to get user information: {e}") from e
