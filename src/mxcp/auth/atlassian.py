# -*- coding: utf-8 -*-
"""Atlassian OAuth provider implementation for MXCP authentication."""
import logging
import secrets
from typing import Dict, Any

from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import RedirectResponse, HTMLResponse, Response

from mcp.server.auth.provider import AuthorizationParams
from mcp.shared._httpx_utils import create_mcp_http_client
from .providers import ExternalOAuthHandler, ExternalUserInfo, StateMeta, UserContext, MCP_SCOPE
from mxcp.config.types import UserAuthConfig
from mxcp.auth.url_utils import URLBuilder

logger = logging.getLogger(__name__)


class AtlassianOAuthHandler(ExternalOAuthHandler):
    """Atlassian OAuth provider implementation for JIRA and Confluence Cloud."""

    def __init__(self, auth_config: UserAuthConfig, host: str = "localhost", port: int = 8000):
        """Initialize Atlassian OAuth handler.
        
        Args:
            auth_config: The auth configuration from user config
            host: The server host for callback URLs
            port: The server port for callback URLs
        """
        logger.info(f"AtlassianOAuthHandler init: {auth_config}")
        
        atlassian_config = auth_config.get("atlassian", {})
        
        # Validate required Atlassian configuration
        required_fields = ["client_id", "client_secret"]
        missing_fields = [field for field in required_fields if not atlassian_config.get(field)]
        if missing_fields:
            raise ValueError(f"Atlassian OAuth configuration is incomplete. Missing: {', '.join(missing_fields)}")
        
        self.client_id = atlassian_config["client_id"]
        self.client_secret = atlassian_config["client_secret"]
        
        # Atlassian OAuth endpoints are standardized
        self.auth_url = atlassian_config.get("auth_url", "https://auth.atlassian.com/authorize")
        self.token_url = atlassian_config.get("token_url", "https://auth.atlassian.com/oauth/token")
        
        # Default scopes for JIRA and Confluence access
        default_scopes = [
            "read:jira-work",
            "read:jira-user", 
            "read:confluence-content.all",
            "read:confluence-user",
            "offline_access"  # For refresh tokens
        ]
        self.scope = atlassian_config.get("scope", " ".join(default_scopes))
        
        self._callback_path = atlassian_config.get("callback_path", "/atlassian/callback")
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
            self._callback_path, 
            host=self.host, 
            port=self.port
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
        
        logger.info(f"Atlassian OAuth authorize URL: client_id={self.client_id}, redirect_uri={full_callback_url}, scope={self.scope}")
        
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
                self._callback_path,
                host=self.host,
                port=self.port
            )
        
        logger.info(f"Atlassian OAuth token exchange: code={code[:10]}..., redirect_uri={full_callback_url}")
        
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
        
        # Don't clean up state here - let handle_callback do it after getting metadata
        logger.info(f"Atlassian OAuth token exchange successful for client: {meta.client_id}")
        
        return ExternalUserInfo(
            id=meta.client_id,
            scopes=[MCP_SCOPE],
            raw_token=payload["access_token"],
            provider="atlassian",
        )

    # ----- callback -----
    @property
    def callback_path(self) -> str:  # noqa: D401
        return self._callback_path

    async def on_callback(self, request: Request, provider: "GeneralOAuthAuthorizationServer") -> Response:  # noqa: E501
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
                username=user_profile.get("nickname", f"user_{user_profile.get('account_id', 'unknown')}"),
                email=user_profile.get("email"),
                name=user_profile.get("name"),
                avatar_url=user_profile.get("picture"),
                raw_profile=user_profile
            )
        except Exception as e:
            logger.error(f"Failed to get Atlassian user context: {e}")
            raise HTTPException(500, f"Failed to retrieve user information: {e}")

    # ----- private helper -----
    async def _fetch_user_profile(self, token: str) -> dict[str, Any]:
        """Fetch raw user profile from Atlassian User Identity API (private implementation detail)."""
        async with create_mcp_http_client() as client:
            resp = await client.get(
                "https://api.atlassian.com/me",
                headers={"Authorization": f"Bearer {token}"},
            )
        if resp.status_code != 200:
            raise ValueError(f"Atlassian API error: {resp.status_code}")
        return resp.json() 