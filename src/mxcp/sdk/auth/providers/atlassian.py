"""Atlassian OAuth provider implementation for MXCP authentication."""

import logging
import secrets
from typing import Any, cast

from mcp.server.auth.provider import AuthorizationParams
from mcp.shared._httpx_utils import create_mcp_http_client
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse, Response

from .._types import (
    AtlassianAuthConfig,
    ExternalUserInfo,
    HttpTransportConfig,
    StateMeta,
    UserContext,
)
from ..base import ExternalOAuthHandler, GeneralOAuthAuthorizationServer
from ..url_utils import URLBuilder

logger = logging.getLogger(__name__)


class AtlassianOAuthHandler(ExternalOAuthHandler):
    """Atlassian OAuth provider implementation for JIRA and Confluence Cloud."""

    def __init__(
        self,
        atlassian_config: AtlassianAuthConfig,
        transport_config: HttpTransportConfig | None = None,
        host: str = "localhost",
        port: int = 8000,
    ):
        """Initialize Atlassian OAuth handler.

        Args:
            atlassian_config: Atlassian-specific OAuth configuration
            transport_config: HTTP transport configuration for URL building
            host: The server host for callback URLs
            port: The server port for callback URLs
        """
        logger.info(f"AtlassianOAuthHandler init: {atlassian_config}")

        # Required fields are enforced by TypedDict structure
        self.client_id = atlassian_config["client_id"]
        self.client_secret = atlassian_config["client_secret"]

        # Atlassian OAuth endpoints are standardized
        self.auth_url = atlassian_config["auth_url"]
        self.token_url = atlassian_config["token_url"]

        # Use configured scope or default
        self.scope = atlassian_config.get(
            "scope",
            "read:me read:jira-work read:jira-user read:confluence-content.all read:confluence-user offline_access",
        )

        self._callback_path = atlassian_config["callback_path"]
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
            f"Atlassian OAuth authorize URL: client_id={self.client_id}, redirect_uri={full_callback_url}, scope={self.scope}"
        )

        # Atlassian requires specific parameters
        return (
            f"{self.auth_url}?"
            f"audience=api.atlassian.com&"
            f"client_id={self.client_id}&"
            f"scope={self.scope}&"
            f"redirect_uri={full_callback_url}&"
            f"state={state}&"
            f"response_type=code&"
            f"prompt=consent"
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
            f"Atlassian OAuth token exchange: code={code[:10]}..., redirect_uri={full_callback_url}"
        )

        async with create_mcp_http_client() as client:
            resp = await client.post(
                self.token_url,
                json={
                    "grant_type": "authorization_code",
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "code": code,
                    "redirect_uri": full_callback_url,
                },
                headers={"Content-Type": "application/json"},
            )
        if resp.status_code != 200:
            logger.error(f"Atlassian token exchange failed: {resp.status_code} {resp.text}")
            raise HTTPException(400, "Failed to exchange code for token")
        payload = resp.json()
        if "error" in payload:
            logger.error(f"Atlassian token exchange error: {payload}")
            raise HTTPException(400, payload.get("error_description", payload["error"]))

        # Get user info to extract the actual user ID
        access_token = payload["access_token"]
        refresh_token = payload.get("refresh_token")  # May be None if not requested
        user_profile = await self._fetch_user_profile(access_token)

        # Use Atlassian's 'account_id' field as the unique identifier
        user_id = user_profile.get("account_id", "")
        if not user_id:
            logger.error("Atlassian user profile missing 'account_id' field")
            raise HTTPException(400, "Invalid user profile: missing user ID")

        # Don't clean up state here - let handle_callback do it after getting metadata
        logger.info(f"Atlassian OAuth token exchange successful for user: {user_id}")

        user_info = ExternalUserInfo(
            id=user_id,
            scopes=[],
            raw_token=access_token,
            provider="atlassian",
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
        if not code or not state:
            raise HTTPException(400, "Missing code or state")
        try:
            redirect_uri = await provider.handle_callback(code, state)
            return RedirectResponse(redirect_uri)
        except HTTPException:
            raise
        except Exception as exc:
            logger.error("Atlassian callback failed", exc_info=exc)
            return HTMLResponse(status_code=500, content="oauth_failure")

    # ----- user context -----
    async def get_user_context(self, token: str) -> UserContext:
        """Get standardized user context from Atlassian.

        Args:
            token: Atlassian OAuth access token

        Returns:
            UserContext with Atlassian user information

        Raises:
            HTTPException: If token is invalid or user info cannot be retrieved
        """
        try:
            user_profile = await self._fetch_user_profile(token)

            # Extract Atlassian-specific fields and map to standard UserContext
            return UserContext(
                provider="atlassian",
                user_id=str(user_profile.get("account_id", "")),
                username=user_profile.get(
                    "nickname", f"user_{user_profile.get('account_id', 'unknown')}"
                ),
                email=user_profile.get("email"),
                name=user_profile.get("name"),
                avatar_url=user_profile.get("picture"),
                raw_profile=user_profile,
                external_token=token,
            )
        except Exception as e:
            logger.error(f"Failed to get Atlassian user context: {e}")
            raise HTTPException(500, f"Failed to retrieve user information: {e}") from e

    # ----- private helper -----
    async def _fetch_user_profile(self, token: str) -> dict[str, Any]:
        """Fetch raw user profile from Atlassian User Identity API (private implementation detail)."""
        logger.info(f"Fetching Atlassian user profile with token: {token[:10]}...")

        async with create_mcp_http_client() as client:
            resp = await client.get(
                "https://api.atlassian.com/me",
                headers={"Authorization": f"Bearer {token}"},
            )

        logger.info(f"Atlassian User Identity API response: {resp.status_code}")

        if resp.status_code != 200:
            error_body = ""
            try:
                error_body = resp.text
                logger.error(f"Atlassian User Identity API error {resp.status_code}: {error_body}")
            except Exception:
                logger.error(
                    f"Atlassian User Identity API error {resp.status_code}: Unable to read response body"
                )
            raise ValueError(f"Atlassian API error: {resp.status_code} - {error_body}")

        user_data = cast(dict[str, Any], resp.json())
        logger.info(
            f"Successfully fetched Atlassian user profile for account_id: {user_data.get('account_id', 'unknown')}"
        )
        return user_data

    async def refresh_access_token(self, refresh_token: str) -> dict[str, Any]:
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
                json=refresh_data,
                headers={"Content-Type": "application/json"},
            )

            if response.status_code != 200:
                logger.error(
                    f"Atlassian token refresh failed: {response.status_code} - {response.text}"
                )
                raise HTTPException(400, "Failed to refresh access token")

            return cast(dict[str, Any], response.json())
