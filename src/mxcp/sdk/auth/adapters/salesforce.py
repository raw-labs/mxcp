"""Salesforce OAuth adapter for MXCP authentication.

This module provides a thin Salesforce OAuth client that conforms to the
ProviderAdapter protocol. It handles only Salesforce-specific OAuth communication.
"""

import logging
from typing import Any, cast
from urllib.parse import urlencode

from mcp.shared._httpx_utils import create_mcp_http_client

from ..adapter import GrantResult, ProviderError, UserInfo
from ..models import HttpTransportConfigModel, SalesforceAuthConfigModel

logger = logging.getLogger(__name__)

# Salesforce OAuth endpoints (can be overridden for sandbox)
SALESFORCE_AUTH_URL = "https://login.salesforce.com/services/oauth2/authorize"
SALESFORCE_TOKEN_URL = "https://login.salesforce.com/services/oauth2/token"
SALESFORCE_REVOKE_URL = "https://login.salesforce.com/services/oauth2/revoke"

# Default scopes for Salesforce
DEFAULT_SCOPES = ["api", "refresh_token", "openid", "profile", "email"]


class SalesforceAdapter:
    """Salesforce OAuth provider adapter.

    A thin client for Salesforce OAuth that implements the ProviderAdapter protocol.
    Supports both production and sandbox environments.
    """

    def __init__(
        self,
        config: SalesforceAuthConfigModel,
        transport_config: HttpTransportConfigModel | None = None,
    ):
        """Initialize Salesforce adapter."""
        self.client_id = config.client_id
        self.client_secret = config.client_secret

        scope_str = config.scope or " ".join(DEFAULT_SCOPES)
        self._default_scopes = scope_str.split()

        self._auth_url = config.auth_url or SALESFORCE_AUTH_URL
        self._token_url = config.token_url or SALESFORCE_TOKEN_URL

        # Salesforce returns instance_url in token response, store for API calls
        self._instance_url: str | None = None

        logger.info("SalesforceAdapter initialized")

    @property
    def provider_name(self) -> str:
        return "salesforce"

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
            "client_id": self.client_id,
            "redirect_uri": redirect_uri,
            "scope": scope_str,
            "response_type": "code",
            "state": state,
        }

        if code_challenge:
            params["code_challenge"] = code_challenge
            params["code_challenge_method"] = code_challenge_method or "S256"

        if extra_params:
            params.update(extra_params)

        return f"{self._auth_url}?{urlencode(params)}"

    async def exchange_code(
        self,
        code: str,
        redirect_uri: str,
        code_verifier: str | None = None,
    ) -> GrantResult:
        data: dict[str, str] = {
            "grant_type": "authorization_code",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "code": code,
            "redirect_uri": redirect_uri,
        }

        if code_verifier:
            data["code_verifier"] = code_verifier

        async with create_mcp_http_client() as client:
            resp = await client.post(
                self._token_url,
                data=data,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )

        if resp.status_code != 200:
            raise ProviderError("token_exchange_failed", resp.text, resp.status_code)

        payload = resp.json()
        if "error" in payload:
            raise ProviderError(payload["error"], payload.get("error_description"))

        # Store instance URL for API calls
        self._instance_url = payload.get("instance_url")

        return GrantResult(
            access_token=payload["access_token"],
            refresh_token=payload.get("refresh_token"),
            expires_in=None,  # Salesforce doesn't return expires_in in standard flow
            id_token=payload.get("id_token"),
            raw_response=payload,
        )

    async def refresh_token(
        self,
        refresh_token: str,
        scopes: list[str] | None = None,
    ) -> GrantResult:
        data: dict[str, str] = {
            "grant_type": "refresh_token",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "refresh_token": refresh_token,
        }

        async with create_mcp_http_client() as client:
            resp = await client.post(
                self._token_url,
                data=data,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )

        if resp.status_code != 200:
            raise ProviderError("refresh_failed", resp.text, resp.status_code)

        payload = resp.json()

        # Update instance URL
        self._instance_url = payload.get("instance_url")

        return GrantResult(
            access_token=payload["access_token"],
            refresh_token=refresh_token,  # Salesforce doesn't return new refresh token
            raw_response=payload,
        )

    async def fetch_user_info(self, access_token: str) -> UserInfo:
        # Use the stored instance URL or fall back to standard endpoint
        base_url = self._instance_url or "https://login.salesforce.com"
        userinfo_url = f"{base_url}/services/oauth2/userinfo"

        async with create_mcp_http_client() as client:
            resp = await client.get(
                userinfo_url,
                headers={"Authorization": f"Bearer {access_token}"},
            )

        if resp.status_code != 200:
            raise ProviderError("userinfo_failed", f"Status: {resp.status_code}", resp.status_code)

        profile = cast(dict[str, Any], resp.json())

        # Salesforce uses 'user_id' or 'sub' depending on endpoint
        user_id = profile.get("user_id") or profile.get("sub", "")

        return UserInfo(
            user_id=user_id,
            username=profile.get("preferred_username"),
            email=profile.get("email"),
            name=profile.get("name"),
            avatar_url=profile.get("picture"),
            raw_profile=profile,
        )

    async def revoke_token(self, token: str, token_type_hint: str | None = None) -> bool:
        revoke_url = SALESFORCE_REVOKE_URL
        if self._instance_url:
            revoke_url = f"{self._instance_url}/services/oauth2/revoke"

        async with create_mcp_http_client() as client:
            resp = await client.post(
                revoke_url,
                data={"token": token},
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )

        return resp.status_code == 200


