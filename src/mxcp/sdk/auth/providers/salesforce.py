"""Salesforce OAuth provider implementation for MXCP authentication."""

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
    HttpTransportConfig,
    SalesforceAuthConfig,
    StateMeta,
    UserContext,
)
from ..base import ExternalOAuthHandler, GeneralOAuthAuthorizationServer
from ..url_utils import URLBuilder

logger = logging.getLogger(__name__)


class SalesforceOAuthHandler(ExternalOAuthHandler):
    """Salesforce OAuth provider implementation for Salesforce Cloud."""

    def __init__(
        self,
        salesforce_config: SalesforceAuthConfig,
        transport_config: HttpTransportConfig | None = None,
        host: str = "localhost",
        port: int = 8000,
    ):
        """Initialize Salesforce OAuth handler.

        Args:
            salesforce_config: Salesforce-specific OAuth configuration
            transport_config: HTTP transport configuration for URL building
            host: The server host for callback URLs
            port: The server port for callback URLs
        """
        logger.info(f"SalesforceOAuthHandler init: {salesforce_config}")

        # Required fields are enforced by TypedDict structure
        self.client_id = salesforce_config["client_id"]
        self.client_secret = salesforce_config["client_secret"]

        # Salesforce OAuth endpoints
        self.auth_url = salesforce_config["auth_url"]
        self.token_url = salesforce_config["token_url"]

        # Use configured scope or default
        self.scope = salesforce_config.get("scope", "api refresh_token openid profile email")

        self._callback_path = salesforce_config["callback_path"]
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
            f"Salesforce OAuth authorize URL: client_id={self.client_id}, redirect_uri={full_callback_url}, scope={self.scope}"
        )

        # Salesforce OAuth parameters
        return (
            f"{self.auth_url}?"
            f"client_id={self.client_id}&"
            f"redirect_uri={full_callback_url}&"
            f"scope={self.scope}&"
            f"response_type=code&"
            f"state={state}"
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
        """Clean up state after OAuth flow completion."""
        self._pop_state(state)

    # ----- code exchange -----
    async def exchange_code(self, code: str, state: str) -> tuple[ExternalUserInfo, StateMeta]:
        meta = self._get_state_metadata(state)

        # Use the stored callback URL for consistency
        full_callback_url = meta.callback_url
        if not full_callback_url:
            # Fallback to constructing it using URL builder
            full_callback_url = self.url_builder.build_callback_url(
                self._callback_path, host=self.host, port=self.port
            )

        logger.info(
            f"Salesforce OAuth token exchange: code={code[:10]}..., redirect_uri={full_callback_url}"
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
            logger.error(f"Salesforce token exchange failed: {resp.status_code} {resp.text}")
            raise HTTPException(400, "Failed to exchange code for token")
        payload = resp.json()
        if "error" in payload:
            logger.error(f"Salesforce token exchange error: {payload}")
            raise HTTPException(400, payload.get("error_description", payload["error"]))

        # Get user info to extract the actual user ID
        access_token = payload["access_token"]
        user_profile = await self._fetch_user_profile(access_token)

        # Use Salesforce's 'user_id' field as the unique identifier
        user_id = user_profile.get("user_id", "")
        if not user_id:
            logger.error("Salesforce user profile missing 'user_id' field")
            raise HTTPException(400, "Invalid user profile: missing user ID")

        # Don't clean up state here - let handle_callback do it after getting metadata
        logger.info(f"Salesforce OAuth token exchange successful for user: {user_id}")

        user_info = ExternalUserInfo(
            id=user_id,
            scopes=[],
            raw_token=access_token,
            provider="salesforce",
        )

        return user_info, meta

    # ----- callback -----
    @property
    def callback_path(self) -> str:  # noqa: D401
        return self._callback_path

    async def on_callback(
        self, request: Request, provider: GeneralOAuthAuthorizationServer
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
            logger.error("Salesforce callback failed", exc_info=exc)
            return HTMLResponse(status_code=500, content="oauth_failure")

    # ----- user context -----
    async def get_user_context(self, token: str) -> UserContext:
        """Get standardized user context from Salesforce.

        Args:
            token: Salesforce OAuth access token

        Returns:
            UserContext with Salesforce user information

        Raises:
            HTTPException: If token is invalid or user info cannot be retrieved
        """
        try:
            user_profile = await self._fetch_user_profile(token)

            # Extract Salesforce-specific fields and map to standard UserContext
            return UserContext(
                provider="salesforce",
                user_id=str(user_profile.get("user_id", "")),
                username=user_profile.get(
                    "username", f"user_{user_profile.get('user_id', 'unknown')}"
                ),
                email=user_profile.get("email"),
                name=user_profile.get("display_name") or user_profile.get("name"),
                avatar_url=user_profile.get("photos", {}).get("picture"),
                raw_profile=user_profile,
                external_token=token,
            )
        except Exception as e:
            logger.error(f"Failed to get Salesforce user context: {e}")
            raise HTTPException(500, f"Failed to retrieve user information: {e}") from e

    # ----- private helper -----
    async def _fetch_user_profile(self, token: str) -> dict[str, Any]:
        """Fetch raw user profile from Salesforce UserInfo endpoint (private implementation detail)."""
        logger.info(f"Fetching Salesforce user profile with token: {token[:10]}...")

        # First get the identity URL from the token response
        async with create_mcp_http_client() as client:
            # Get token info to find the identity URL
            await client.get(
                "https://login.salesforce.com/services/oauth2/token",
                headers={"Authorization": f"Bearer {token}"},
            )

            # If token info doesn't work, try the standard userinfo endpoint
            resp = await client.get(
                "https://login.salesforce.com/services/oauth2/userinfo",
                headers={"Authorization": f"Bearer {token}"},
            )

        logger.info(f"Salesforce UserInfo API response: {resp.status_code}")

        if resp.status_code != 200:
            error_body = ""
            try:
                error_body = resp.text
                logger.error(f"Salesforce UserInfo API error {resp.status_code}: {error_body}")
            except Exception:
                logger.error(
                    f"Salesforce UserInfo API error {resp.status_code}: Unable to read response body"
                )
            raise ValueError(f"Salesforce API error: {resp.status_code} - {error_body}")

        user_data = cast(dict[str, Any], resp.json())
        logger.info(
            f"Successfully fetched Salesforce user profile for user_id: {user_data.get('user_id', 'unknown')}"
        )
        return user_data
