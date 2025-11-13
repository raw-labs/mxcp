"""Google OAuth provider implementation for MXCP authentication."""

import logging
import secrets
from typing import Any, cast

from mcp.server.auth.provider import AuthorizationParams
from mcp.shared._httpx_utils import create_mcp_http_client
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse, Response

from .._types import (
    ExternalUserInfo,
    GoogleAuthConfig,
    HttpTransportConfig,
    RefreshTokenResponse,
    StateMeta,
    UserContext,
)
from ..base import ExternalOAuthHandler, GeneralOAuthAuthorizationServer
from ..url_utils import URLBuilder

logger = logging.getLogger(__name__)


class GoogleOAuthHandler(ExternalOAuthHandler):
    """Google OAuth provider implementation for Google Workspace APIs."""

    def __init__(
        self,
        google_config: GoogleAuthConfig,
        transport_config: HttpTransportConfig | None = None,
        host: str = "localhost",
        port: int = 8000,
    ):
        """Initialize Google OAuth handler.

        Args:
            google_config: Google-specific OAuth configuration
            transport_config: HTTP transport configuration for URL building
            host: The server host for callback URLs
            port: The server port for callback URLs
        """
        logger.info("GoogleOAuthHandler initialized for Google Workspace authentication")

        # Required fields are enforced by TypedDict structure
        self.client_id = google_config["client_id"]
        self.client_secret = google_config["client_secret"]

        # Google OAuth endpoints
        self.auth_url = google_config["auth_url"]
        self.token_url = google_config["token_url"]

        # Use configured scope or default to calendar read-only
        self.scope = google_config.get(
            "scope",
            "https://www.googleapis.com/auth/calendar.readonly openid profile email",
        )

        self._callback_path = google_config["callback_path"]
        self.host = host
        self.port = port

        # Initialize URL builder for proper scheme detection
        self.url_builder = URLBuilder(transport_config)

        # State storage for OAuth flow
        self._state_store: dict[str, StateMeta] = {}

    # ----- authorize -----
    def get_authorize_url(self, client_id: str, params: AuthorizationParams) -> str:
        state = params.state or secrets.token_hex(16)

        # Use URL builder to construct callback URL with proper scheme detection
        full_callback_url = self.url_builder.build_callback_url(
            self._callback_path, host=self.host, port=self.port
        )

        # Store the original redirect URI and callback URL in state for later use
        self._state_store[state] = StateMeta(
            redirect_uri=str(params.redirect_uri),
            code_challenge=params.code_challenge,
            redirect_uri_provided_explicitly=params.redirect_uri_provided_explicitly,
            client_id=client_id,
            callback_url=full_callback_url,
        )

        logger.info(
            f"Google OAuth authorize URL: client_id={self.client_id}, redirect_uri={full_callback_url}, scope={self.scope}"
        )

        # Google requires specific parameters including access_type for refresh tokens
        return (
            f"{self.auth_url}?"
            f"client_id={self.client_id}&"
            f"redirect_uri={full_callback_url}&"
            f"response_type=code&"
            f"scope={self.scope}&"
            f"state={state}&"
            f"access_type=offline&"  # Request refresh token
            f"prompt=consent"  # Force consent to ensure refresh token is returned
        )

    # ----- state helpers -----
    def _get_state_metadata(self, state: str) -> StateMeta:
        try:
            return self._state_store[state]
        except KeyError:
            raise HTTPException(400, "Invalid state parameter") from None

    def _pop_state(self, state: str) -> None:
        self._state_store.pop(state, None)

    def cleanup_state(self, state: str) -> None:
        """Clean up state and associated callback URL after OAuth flow completion."""
        self._pop_state(state)

    # ----- code exchange -----
    async def exchange_code(self, code: str, state: str) -> tuple[ExternalUserInfo, StateMeta]:
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
            f"Google OAuth token exchange: code={code[:10]}..., redirect_uri={full_callback_url}"
        )

        async with create_mcp_http_client() as client:
            resp = await client.post(
                self.token_url,
                data={
                    "grant_type": "authorization_code",
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "code": code,
                    "redirect_uri": full_callback_url,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
        if resp.status_code != 200:
            logger.error(f"Google token exchange failed: {resp.status_code} {resp.text}")
            raise HTTPException(400, "Failed to exchange code for token")
        payload = resp.json()
        if "error" in payload:
            logger.error(f"Google token exchange error: {payload}")
            raise HTTPException(400, payload.get("error_description", payload["error"]))

        # Get user info to extract the actual user ID
        access_token = payload["access_token"]
        refresh_token = payload.get("refresh_token")  # May be None if not requested
        user_profile = await self._fetch_user_profile(access_token)

        # Use either 'sub' (OpenID Connect) or 'id' (OAuth2) as the unique identifier
        user_id = user_profile.get("sub") or user_profile.get("id", "")
        if not user_id:
            logger.error("Google user profile missing both 'sub' and 'id' fields")
            raise HTTPException(400, "Invalid user profile: missing user ID")

        # Don't clean up state here - let handle_callback do it after getting metadata
        logger.info(f"Google OAuth token exchange successful for user: {user_id}")

        user_info = ExternalUserInfo(
            id=user_id,
            scopes=[],
            raw_token=access_token,
            provider="google",
            refresh_token=refresh_token,
        )

        return user_info, state_meta

    # ----- callback -----
    @property
    def callback_path(self) -> str:  # noqa: D401
        return self._callback_path

    async def on_callback(
        self, request: Request, provider: "GeneralOAuthAuthorizationServer"
    ) -> Response:  # noqa: E501
        code = request.query_params.get("code")
        state = request.query_params.get("state")
        error = request.query_params.get("error")

        if error:
            logger.error(f"Google OAuth error: {error}")
            error_desc = request.query_params.get("error_description", error)
            return HTMLResponse(status_code=400, content=f"OAuth error: {error_desc}")

        if not code or not state:
            raise HTTPException(400, "Missing code or state")
        try:
            redirect_uri = await provider.handle_callback(code, state)
            return RedirectResponse(redirect_uri)
        except HTTPException:
            raise
        except Exception as exc:
            logger.error("Google callback failed", exc_info=exc)
            return HTMLResponse(status_code=500, content="oauth_failure")

    # ----- user context -----
    async def get_user_context(self, token: str) -> UserContext:
        """Get standardized user context from Google.

        Args:
            token: Google OAuth access token

        Returns:
            UserContext with Google user information

        Raises:
            HTTPException: If token is invalid or user info cannot be retrieved
        """
        try:
            user_profile = await self._fetch_user_profile(token)

            # Extract Google-specific fields and map to standard UserContext
            # Use either 'sub' (OpenID Connect) or 'id' (OAuth2) as the unique identifier
            user_id = str(user_profile.get("sub") or user_profile.get("id", ""))
            return UserContext(
                provider="google",
                user_id=user_id,  # Use whichever ID field is available
                username=user_profile.get("email", f"user_{user_id}").split("@")[
                    0
                ],  # Use email prefix as username
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
            logger.error(f"Failed to get Google user context: {e}")
            raise HTTPException(500, f"Failed to retrieve user information: {e}") from e

    # ----- private helper -----
    async def _fetch_user_profile(self, token: str) -> dict[str, Any]:
        """Fetch raw user profile from Google UserInfo API (private implementation detail)."""
        logger.info(f"Fetching Google user profile with token: {token[:10]}...")

        async with create_mcp_http_client() as client:
            resp = await client.get(
                "https://www.googleapis.com/oauth2/v2/userinfo",
                headers={"Authorization": f"Bearer {token}"},
            )

        logger.info(f"Google UserInfo API response: {resp.status_code}")

        if resp.status_code != 200:
            error_body = ""
            try:
                error_body = resp.text
                logger.error(f"Google UserInfo API error {resp.status_code}: {error_body}")
            except Exception:
                logger.error(
                    f"Google UserInfo API error {resp.status_code}: Unable to read response body"
                )
            # Preserve the original status code (e.g., 401 for expired tokens)
            raise HTTPException(resp.status_code, f"Google API error: {error_body}")

        user_data = cast(dict[str, Any], resp.json())
        logger.info(
            f"Successfully fetched Google user profile for sub: {user_data.get('sub', 'unknown')}"
        )
        return user_data

    async def refresh_access_token(self, refresh_token: str) -> RefreshTokenResponse:
        """Refresh an expired access token using the refresh token."""
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
                logger.error(
                    f"Google token refresh failed: {response.status_code} - {response.text}"
                )
                raise HTTPException(400, "Failed to refresh access token")

            # Parse and validate response using Pydantic model
            response_data = response.json()
            return RefreshTokenResponse(**response_data)
