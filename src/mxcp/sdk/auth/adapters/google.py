"""Google OAuth adapter for MXCP authentication.

This module provides a thin Google OAuth client that conforms to the
ProviderAdapter protocol. It handles only Google-specific OAuth communication,
delegating state management and storage to other components.
"""

import logging
from typing import Any, cast
from urllib.parse import urlencode

from mcp.shared._httpx_utils import create_mcp_http_client

from ..adapter import GrantResult, ProviderError, UserInfo
from ..models import GoogleAuthConfigModel, HttpTransportConfigModel

logger = logging.getLogger(__name__)

# Google OAuth endpoints
GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"
GOOGLE_REVOKE_URL = "https://oauth2.googleapis.com/revoke"

# Default scopes for Google
DEFAULT_SCOPES = ["openid", "profile", "email"]


class GoogleAdapter:
    """Google OAuth provider adapter.

    A thin client for Google OAuth that implements the ProviderAdapter protocol.
    This adapter handles only the protocol communication with Google, without
    managing state or callback routing.

    Attributes:
        client_id: Google OAuth client ID.
        client_secret: Google OAuth client secret.
        scopes: Default scopes to request.
    """

    def __init__(
        self,
        config: GoogleAuthConfigModel,
        transport_config: HttpTransportConfigModel | None = None,
    ):
        """Initialize Google adapter.

        Args:
            config: Google-specific OAuth configuration.
            transport_config: HTTP transport configuration (unused, for interface consistency).
        """
        self.client_id = config.client_id
        self.client_secret = config.client_secret

        # Parse configured scopes
        scope_str = config.scope or " ".join(DEFAULT_SCOPES)
        self._default_scopes = scope_str.split()

        # Use configured URLs or defaults
        self._auth_url = config.auth_url or GOOGLE_AUTH_URL
        self._token_url = config.token_url or GOOGLE_TOKEN_URL

        logger.info("GoogleAdapter initialized")

    @property
    def provider_name(self) -> str:
        """Return the provider name."""
        return "google"

    async def build_authorize_url(
        self,
        redirect_uri: str,
        state: str,
        scopes: list[str] | None = None,
        code_challenge: str | None = None,
        code_challenge_method: str | None = None,
        extra_params: dict[str, str] | None = None,
    ) -> str:
        """Build the Google authorization URL.

        Args:
            redirect_uri: The callback URL.
            state: CSRF protection state value.
            scopes: Scopes to request (uses defaults if None).
            code_challenge: PKCE code challenge.
            code_challenge_method: PKCE method.
            extra_params: Additional parameters.

        Returns:
            Complete Google authorization URL.
        """
        effective_scopes = scopes if scopes is not None else self._default_scopes
        scope_str = " ".join(effective_scopes)

        params: dict[str, str] = {
            "client_id": self.client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": scope_str,
            "state": state,
            "access_type": "offline",  # Request refresh token
            "prompt": "consent",  # Force consent for refresh token
        }

        if code_challenge:
            params["code_challenge"] = code_challenge
            params["code_challenge_method"] = code_challenge_method or "S256"

        if extra_params:
            params.update(extra_params)

        url = f"{self._auth_url}?{urlencode(params)}"
        logger.debug(f"Built Google authorize URL: {url[:100]}...")
        return url

    async def exchange_code(
        self,
        code: str,
        redirect_uri: str,
        code_verifier: str | None = None,
    ) -> GrantResult:
        """Exchange authorization code for tokens.

        Args:
            code: The authorization code.
            redirect_uri: The redirect URI used in authorization.
            code_verifier: PKCE code verifier (if used).

        Returns:
            GrantResult with access token and optionally refresh token.

        Raises:
            ProviderError: If token exchange fails.
        """
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
            error_data: dict[str, Any] = {}
            try:
                error_data = resp.json()
            except Exception:
                pass  # JSON parsing failed, use empty dict
            
            raise ProviderError(
                error=error_data.get("error", "token_exchange_failed"),
                error_description=error_data.get("error_description") or resp.text,
                status_code=resp.status_code,
            )

        payload = resp.json()

        if "error" in payload:
            raise ProviderError(
                error=payload["error"],
                error_description=payload.get("error_description"),
            )

        # Extract user_id from ID token if present, or fetch it
        user_id = None
        if "id_token" in payload:
            # Could decode JWT here, but we'll fetch userinfo for simplicity
            pass

        logger.info("Google code exchange successful")

        return GrantResult(
            access_token=payload["access_token"],
            refresh_token=payload.get("refresh_token"),
            expires_in=payload.get("expires_in"),
            token_type=payload.get("token_type", "Bearer"),
            scope=payload.get("scope"),
            id_token=payload.get("id_token"),
            user_id=user_id,
            raw_response=payload,
        )

    async def refresh_token(
        self,
        refresh_token: str,
        scopes: list[str] | None = None,
    ) -> GrantResult:
        """Refresh an access token.

        Args:
            refresh_token: The refresh token.
            scopes: Scopes to request.

        Returns:
            GrantResult with new access token.

        Raises:
            ProviderError: If refresh fails.
        """
        data: dict[str, str] = {
            "grant_type": "refresh_token",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "refresh_token": refresh_token,
        }

        if scopes:
            data["scope"] = " ".join(scopes)

        async with create_mcp_http_client() as client:
            resp = await client.post(
                self._token_url,
                data=data,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )

        if resp.status_code != 200:
            error_data: dict[str, Any] = {}
            try:
                error_data = resp.json()
            except Exception:
                pass  # JSON parsing failed, use empty dict
            
            raise ProviderError(
                error=error_data.get("error", "refresh_failed"),
                error_description=error_data.get("error_description") or resp.text,
                status_code=resp.status_code,
            )

        payload = resp.json()

        if "error" in payload:
            raise ProviderError(
                error=payload["error"],
                error_description=payload.get("error_description"),
            )

        logger.info("Google token refresh successful")

        return GrantResult(
            access_token=payload["access_token"],
            refresh_token=payload.get("refresh_token", refresh_token),  # May not return new refresh token
            expires_in=payload.get("expires_in"),
            token_type=payload.get("token_type", "Bearer"),
            scope=payload.get("scope"),
            raw_response=payload,
        )

    async def fetch_user_info(self, access_token: str) -> UserInfo:
        """Fetch user information from Google.

        Args:
            access_token: A valid Google access token.

        Returns:
            UserInfo with Google user data.

        Raises:
            ProviderError: If user info cannot be retrieved.
        """
        async with create_mcp_http_client() as client:
            resp = await client.get(
                GOOGLE_USERINFO_URL,
                headers={"Authorization": f"Bearer {access_token}"},
            )

        if resp.status_code != 200:
            raise ProviderError(
                error="userinfo_failed",
                error_description=f"Failed to fetch user info: {resp.status_code}",
                status_code=resp.status_code,
            )

        profile = cast(dict[str, Any], resp.json())

        # Google returns 'sub' (OIDC) or 'id' (OAuth2) as user ID
        user_id = str(profile.get("sub") or profile.get("id", ""))
        if not user_id:
            raise ProviderError(
                error="invalid_profile",
                error_description="User profile missing ID",
            )

        # Use email prefix as username if available
        email = profile.get("email")
        username = email.split("@")[0] if email else None

        logger.debug(f"Fetched Google user info for user_id: {user_id}")

        return UserInfo(
            user_id=user_id,
            username=username,
            email=email,
            name=profile.get("name"),
            avatar_url=profile.get("picture"),
            raw_profile=profile,
        )

    async def revoke_token(self, token: str, token_type_hint: str | None = None) -> bool:
        """Revoke a token at Google.

        Args:
            token: The token to revoke.
            token_type_hint: Hint about token type (unused by Google).

        Returns:
            True if revocation succeeded.
        """
        async with create_mcp_http_client() as client:
            resp = await client.post(
                GOOGLE_REVOKE_URL,
                data={"token": token},
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )

        # Google returns 200 on success
        if resp.status_code == 200:
            logger.info("Google token revoked successfully")
            return True

        logger.warning(f"Google token revocation failed: {resp.status_code}")
        return False

