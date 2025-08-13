"""Keycloak OAuth provider implementation for MXCP authentication."""

import logging
import secrets
from typing import Any, cast
from urllib.parse import urlencode

from mcp.server.auth.provider import AuthorizationParams
from mcp.shared._httpx_utils import create_mcp_http_client
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse, Response

from ._types import (
    ExternalUserInfo,
    HttpTransportConfig,
    KeycloakAuthConfig,
    StateMeta,
    UserContext,
)
from .providers import ExternalOAuthHandler, GeneralOAuthAuthorizationServer
from .url_utils import URLBuilder

logger = logging.getLogger(__name__)


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
        self.scope = keycloak_config.get("scope", "openid profile email")
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
        self._state_store: dict[str, StateMeta] = {}

    @property
    def callback_path(self) -> str:
        """Return the callback path for OAuth flow."""
        return self._callback_path

    def get_authorize_url(self, client_id: str, params: AuthorizationParams) -> str:
        """Generate the authorization URL for Keycloak."""
        state = secrets.token_urlsafe(32)

        # Store state metadata
        self._state_store[state] = StateMeta(
            redirect_uri=str(params.redirect_uri),
            code_challenge=params.code_challenge,
            redirect_uri_provided_explicitly=params.redirect_uri_provided_explicitly,
            client_id=client_id,
        )

        # Prepare authorization parameters
        auth_params = {
            "client_id": self.client_id,
            "response_type": "code",
            "redirect_uri": (
                str(params.redirect_uri)
                if params.redirect_uri
                else self.url_builder.build_callback_url(self._callback_path)
            ),
            "scope": self.scope,
            "state": state,
        }

        # Add optional parameters
        if params.code_challenge:
            auth_params["code_challenge"] = params.code_challenge
            auth_params["code_challenge_method"] = "S256"  # Always use S256 for PKCE

        # Note: prompt and login_hint are not standard AuthorizationParams attributes
        # They would need to be passed through a different mechanism if needed

        # Construct the full authorization URL
        auth_url = f"{self.auth_url}?{urlencode(auth_params)}"
        logger.debug(f"Generated authorization URL: {auth_url}")

        return auth_url

    async def exchange_code(self, code: str, state: str) -> ExternalUserInfo:
        """Exchange authorization code for tokens."""
        # Retrieve state metadata
        state_meta = self._state_store.get(state)
        if not state_meta:
            raise HTTPException(400, "Invalid state parameter")

        # Prepare token exchange request
        token_data = {
            "grant_type": "authorization_code",
            "code": code,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "redirect_uri": state_meta.redirect_uri,
        }

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

        # Extract the access token
        access_token = token_response.get("access_token")
        if not access_token:
            raise HTTPException(400, "No access token received")

        # Get user info using the access token
        user_info = await self._get_user_info(access_token)

        # Map Keycloak claims to ExternalUserInfo
        # Keycloak typically uses 'sub' as the unique user identifier
        user_id = user_info.get("sub", "")

        # Extract scopes from the token response or use default
        scopes = token_response.get("scope", self.scope).split()

        return ExternalUserInfo(
            id=user_id, scopes=scopes, raw_token=access_token, provider="keycloak"
        )

    async def _get_user_info(self, access_token: str) -> dict[str, Any]:
        """Get user information from Keycloak userinfo endpoint."""
        async with create_mcp_http_client() as client:
            response = await client.get(
                self.userinfo_url, headers={"Authorization": f"Bearer {access_token}"}
            )

            if response.status_code != 200:
                logger.error(f"Failed to get user info: {response.status_code}")
                raise HTTPException(400, "Failed to get user information")

            return cast(dict[str, Any], response.json())

    def get_state_metadata(self, state: str) -> StateMeta:
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
            user_info = await self._get_user_info(token)

            # Map Keycloak claims to UserContext
            # Keycloak uses standard OIDC claims
            return UserContext(
                provider="keycloak",
                user_id=user_info.get("sub", ""),
                username=user_info.get("preferred_username", user_info.get("email", "")),
                email=user_info.get("email"),
                name=user_info.get("name"),
                avatar_url=user_info.get("picture"),
                raw_profile=user_info,
                external_token=token,
            )
        except Exception as e:
            logger.error(f"Failed to get user context: {e}")
            raise HTTPException(401, "Failed to get user information") from e
