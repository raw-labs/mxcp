"""Atlassian OAuth adapter for MXCP authentication.

This module provides a thin Atlassian OAuth client that conforms to the
ProviderAdapter protocol. It handles only Atlassian-specific OAuth communication
for JIRA and Confluence Cloud.
"""

import logging
from typing import Any, cast
from urllib.parse import urlencode

from mcp.shared._httpx_utils import create_mcp_http_client

from ..adapter import GrantResult, ProviderError, UserInfo
from ..models import AtlassianAuthConfigModel, HttpTransportConfigModel

logger = logging.getLogger(__name__)

# Atlassian OAuth endpoints
ATLASSIAN_AUTH_URL = "https://auth.atlassian.com/authorize"
ATLASSIAN_TOKEN_URL = "https://auth.atlassian.com/oauth/token"
ATLASSIAN_API_URL = "https://api.atlassian.com"

# Default scopes for Atlassian
DEFAULT_SCOPES = ["read:me", "read:jira-work", "read:jira-user", "offline_access"]


class AtlassianAdapter:
    """Atlassian OAuth provider adapter.

    A thin client for Atlassian OAuth that implements the ProviderAdapter protocol.
    Supports JIRA and Confluence Cloud authentication.
    """

    def __init__(
        self,
        config: AtlassianAuthConfigModel,
        transport_config: HttpTransportConfigModel | None = None,
    ):
        """Initialize Atlassian adapter."""
        self.client_id = config.client_id
        self.client_secret = config.client_secret

        scope_str = config.scope or " ".join(DEFAULT_SCOPES)
        self._default_scopes = scope_str.split()

        self._auth_url = config.auth_url or ATLASSIAN_AUTH_URL
        self._token_url = config.token_url or ATLASSIAN_TOKEN_URL

        logger.info("AtlassianAdapter initialized")

    @property
    def provider_name(self) -> str:
        return "atlassian"

    async def build_authorize_url(
        self,
        redirect_uri: str,
        state: str,
        scopes: list[str] | None = None,
        code_challenge: str | None = None,
        code_challenge_method: str | None = None,
        extra_params: dict[str, str] | None = None,
    ) -> str:
        effective_scopes = scopes if scopes is not None else self._default_scopes
        scope_str = " ".join(effective_scopes)

        params: dict[str, str] = {
            "audience": "api.atlassian.com",
            "client_id": self.client_id,
            "scope": scope_str,
            "redirect_uri": redirect_uri,
            "state": state,
            "response_type": "code",
            "prompt": "consent",
        }

        if extra_params:
            params.update(extra_params)

        return f"{self._auth_url}?{urlencode(params)}"

    async def exchange_code(
        self,
        code: str,
        redirect_uri: str,
        code_verifier: str | None = None,
    ) -> GrantResult:
        data = {
            "grant_type": "authorization_code",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "code": code,
            "redirect_uri": redirect_uri,
        }

        async with create_mcp_http_client() as client:
            resp = await client.post(
                self._token_url,
                json=data,
                headers={"Content-Type": "application/json"},
            )

        if resp.status_code != 200:
            raise ProviderError("token_exchange_failed", resp.text, resp.status_code)

        payload = resp.json()
        if "error" in payload:
            raise ProviderError(payload["error"], payload.get("error_description"))

        return GrantResult(
            access_token=payload["access_token"],
            refresh_token=payload.get("refresh_token"),
            expires_in=payload.get("expires_in"),
            scope=payload.get("scope"),
            raw_response=payload,
        )

    async def refresh_token(
        self,
        refresh_token: str,
        scopes: list[str] | None = None,
    ) -> GrantResult:
        data = {
            "grant_type": "refresh_token",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "refresh_token": refresh_token,
        }

        async with create_mcp_http_client() as client:
            resp = await client.post(
                self._token_url,
                json=data,
                headers={"Content-Type": "application/json"},
            )

        if resp.status_code != 200:
            raise ProviderError("refresh_failed", resp.text, resp.status_code)

        payload = resp.json()
        return GrantResult(
            access_token=payload["access_token"],
            refresh_token=payload.get("refresh_token", refresh_token),
            expires_in=payload.get("expires_in"),
            raw_response=payload,
        )

    async def fetch_user_info(self, access_token: str) -> UserInfo:
        async with create_mcp_http_client() as client:
            resp = await client.get(
                f"{ATLASSIAN_API_URL}/me",
                headers={"Authorization": f"Bearer {access_token}"},
            )

        if resp.status_code != 200:
            raise ProviderError("userinfo_failed", f"Status: {resp.status_code}", resp.status_code)

        profile = cast(dict[str, Any], resp.json())
        user_id = profile.get("account_id", "")

        return UserInfo(
            user_id=user_id,
            username=profile.get("name"),
            email=profile.get("email"),
            name=profile.get("name"),
            avatar_url=profile.get("picture"),
            raw_profile=profile,
        )

    async def revoke_token(self, token: str, token_type_hint: str | None = None) -> bool:
        # Atlassian doesn't have a standard revocation endpoint
        return False


