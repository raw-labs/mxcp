# -*- coding: utf-8 -*-
"""GitHub OAuth provider implementation for MXCP authentication."""
import logging
import secrets
from typing import Dict, Any

from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import RedirectResponse, HTMLResponse, Response

from mcp.server.auth.provider import AuthorizationParams
from mcp.shared._httpx_utils import create_mcp_http_client
from .providers import ExternalOAuthHandler, ExternalUserInfo, StateMeta, UserContext
from mxcp.config.types import UserAuthConfig
from mxcp.auth.url_utils import URLBuilder

logger = logging.getLogger(__name__)


class GitHubOAuthHandler(ExternalOAuthHandler):
    """GitHub OAuth provider implementation."""

    def __init__(self, auth_config: UserAuthConfig, host: str = "localhost", port: int = 8000):
        """Initialize GitHub OAuth handler.

        Args:
            auth_config: The auth configuration from user config
            host: The server host for callback URLs
            port: The server port for callback URLs
        """
        logger.info(f"GitHubOAuthHandler init: {auth_config}")

        github_config = auth_config.get("github", {})

        # Validate required GitHub configuration
        required_fields = ["client_id", "client_secret", "auth_url", "token_url"]
        missing_fields = [field for field in required_fields if not github_config.get(field)]
        if missing_fields:
            raise ValueError(
                "GitHub OAuth configuration is incomplete. Required: client_id, client_secret, auth_url, token_url"
            )

        self.client_id = github_config["client_id"]
        self.client_secret = github_config["client_secret"]
        self.scope = github_config.get("scope", "user:email")
        self._callback_path = github_config.get("callback_path", "/github/callback")
        self.auth_url = github_config["auth_url"]
        self.token_url = github_config["token_url"]
        self.host = host
        self.port = port

        # Initialize URL builder for proper scheme detection
        # Extract transport config from auth_config if available
        transport_config = None
        if "transport" in auth_config:
            transport_config = auth_config["transport"].get("http", {})
        self.url_builder = URLBuilder(transport_config)

        # State storage for OAuth flow
        self._state_store: Dict[str, StateMeta] = {}

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
        )
        # Store the callback URL separately for consistency
        self._state_store[state + "_callback"] = full_callback_url

        logger.info(
            f"GitHub OAuth authorize URL: client_id={self.client_id}, redirect_uri={full_callback_url}, scope={self.scope}"
        )

        return (
            f"{self.auth_url}?client_id={self.client_id}"
            f"&redirect_uri={full_callback_url}"
            f"&scope={self.scope}&state={state}"
        )

    # ----- state helpers -----
    def get_state_metadata(self, state: str) -> StateMeta:
        try:
            return self._state_store[state]
        except KeyError:
            raise HTTPException(400, "Invalid state parameter")

    def _pop_state(self, state: str):
        self._state_store.pop(state, None)

    def cleanup_state(self, state: str):
        """Clean up state and associated callback URL after OAuth flow completion."""
        self._pop_state(state)
        self._state_store.pop(state + "_callback", None)

    # ----- code exchange -----
    async def exchange_code(self, code: str, state: str) -> ExternalUserInfo:
        meta = self.get_state_metadata(state)

        # Use the stored callback URL for consistency
        full_callback_url = self._state_store.get(state + "_callback")
        if not full_callback_url:
            # Fallback to constructing it using URL builder
            full_callback_url = self.url_builder.build_callback_url(
                self._callback_path, host=self.host, port=self.port
            )

        logger.info(
            f"GitHub OAuth token exchange: code={code[:10]}..., redirect_uri={full_callback_url}"
        )

        async with create_mcp_http_client() as client:
            resp = await client.post(
                self.token_url,
                data={
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "code": code,
                    "redirect_uri": full_callback_url,
                },
                headers={"Accept": "application/json"},
            )
        if resp.status_code != 200:
            logger.error(f"GitHub token exchange failed: {resp.status_code} {resp.text}")
            raise HTTPException(400, "Failed to exchange code for token")
        payload = resp.json()
        if "error" in payload:
            logger.error(f"GitHub token exchange error: {payload}")
            raise HTTPException(400, payload.get("error_description", payload["error"]))

        # Don't clean up state here - let handle_callback do it after getting metadata
        logger.info(f"GitHub OAuth token exchange successful for client: {meta.client_id}")

        return ExternalUserInfo(
            id=meta.client_id,
            scopes=[],
            raw_token=payload["access_token"],
            provider="github",
        )

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
            logger.error("GitHub callback failed", exc_info=exc)
            return HTMLResponse(status_code=500, content="oauth_failure")

    # ----- user context -----
    async def get_user_context(self, token: str) -> UserContext:
        """Get standardized user context from GitHub.

        Args:
            token: GitHub OAuth access token

        Returns:
            UserContext with GitHub user information

        Raises:
            HTTPException: If token is invalid or user info cannot be retrieved
        """
        try:
            user_profile = await self._fetch_user_profile(token)

            # Extract GitHub-specific fields and map to standard UserContext
            return UserContext(
                provider="github",
                user_id=str(user_profile.get("id", "")),
                username=user_profile.get("login", f"user_{user_profile.get('id', 'unknown')}"),
                email=user_profile.get("email"),
                name=user_profile.get("name"),
                avatar_url=user_profile.get("avatar_url"),
                raw_profile=user_profile,
            )
        except Exception as e:
            logger.error(f"Failed to get GitHub user context: {e}")
            raise HTTPException(500, f"Failed to retrieve user information: {e}")

    # ----- private helper -----
    async def _fetch_user_profile(self, token: str) -> dict[str, Any]:
        """Fetch raw user profile from GitHub API (private implementation detail)."""
        async with create_mcp_http_client() as client:
            resp = await client.get(
                "https://api.github.com/user",
                headers={"Authorization": f"Bearer {token}"},
            )
        if resp.status_code != 200:
            raise ValueError(f"GitHub API error: {resp.status_code}")
        return resp.json()
