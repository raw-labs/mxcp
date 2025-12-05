"""Keycloak OAuth adapter for MXCP authentication.

This module provides a thin Keycloak OAuth client that conforms to the
ProviderAdapter protocol. It handles only Keycloak-specific OAuth communication,
delegating state management and storage to other components.
"""

import base64
import hashlib
import logging
import secrets
from typing import Any, cast
from urllib.parse import urlencode

from mcp.shared._httpx_utils import create_mcp_http_client

from ..adapter import GrantResult, ProviderError, UserInfo
from ..models import HttpTransportConfigModel, KeycloakAuthConfigModel

logger = logging.getLogger(__name__)

# Default scopes for Keycloak
DEFAULT_SCOPES = ["openid", "profile", "email"]


def generate_pkce_pair() -> tuple[str, str]:
    """Generate PKCE code verifier and challenge pair.

    Returns:
        Tuple of (code_verifier, code_challenge).
    """
    # Generate a cryptographically random code_verifier (43-128 chars)
    code_verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode("utf-8").rstrip("=")

    # Generate code_challenge using S256 method
    challenge_bytes = hashlib.sha256(code_verifier.encode("utf-8")).digest()
    code_challenge = base64.urlsafe_b64encode(challenge_bytes).decode("utf-8").rstrip("=")

    return code_verifier, code_challenge


class KeycloakAdapter:
    """Keycloak OAuth provider adapter.

    A thin client for Keycloak OAuth that implements the ProviderAdapter protocol.
    This adapter handles only the protocol communication with Keycloak, without
    managing state or callback routing.

    Keycloak uses PKCE by default for added security.

    Attributes:
        client_id: Keycloak OAuth client ID.
        client_secret: Keycloak OAuth client secret (may be None for public clients).
        realm: Keycloak realm name.
        server_url: Base URL of the Keycloak server.
    """

    def __init__(
        self,
        config: KeycloakAuthConfigModel,
        transport_config: HttpTransportConfigModel | None = None,
    ):
        """Initialize Keycloak adapter.

        Args:
            config: Keycloak-specific OAuth configuration.
            transport_config: HTTP transport configuration (unused, for interface consistency).
        """
        self.client_id = config.client_id
        self.client_secret = config.client_secret
        self.realm = config.realm
        self.server_url = config.server_url.rstrip("/")

        # Parse configured scopes
        scope_str = config.scope or " ".join(DEFAULT_SCOPES)
        self._default_scopes = scope_str.split()

        # Construct Keycloak OAuth endpoints
        realm_base = f"{self.server_url}/realms/{self.realm}/protocol/openid-connect"
        self._auth_url = f"{realm_base}/auth"
        self._token_url = f"{realm_base}/token"
        self._userinfo_url = f"{realm_base}/userinfo"
        self._revoke_url = f"{realm_base}/revoke"

        logger.info(f"KeycloakAdapter initialized for realm: {self.realm}")

    @property
    def provider_name(self) -> str:
        """Return the provider name."""
        return "keycloak"

    async def build_authorize_url(
        self,
        redirect_uri: str,
        state: str,
        scopes: list[str] | None = None,
        code_challenge: str | None = None,
        code_challenge_method: str | None = None,
        extra_params: dict[str, str] | None = None,
    ) -> str:
        """Build the Keycloak authorization URL.

        Note: Keycloak requires PKCE. If code_challenge is not provided,
        the caller should generate one using generate_pkce_pair().

        Args:
            redirect_uri: The callback URL.
            state: CSRF protection state value.
            scopes: Scopes to request (uses defaults if None).
            code_challenge: PKCE code challenge (required for Keycloak).
            code_challenge_method: PKCE method (default: S256).
            extra_params: Additional parameters.

        Returns:
            Complete Keycloak authorization URL.
        """
        effective_scopes = scopes if scopes is not None else self._default_scopes
        scope_str = " ".join(effective_scopes)

        params: dict[str, str] = {
            "client_id": self.client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": scope_str,
            "state": state,
        }

        # PKCE is required for Keycloak
        if code_challenge:
            params["code_challenge"] = code_challenge
            params["code_challenge_method"] = code_challenge_method or "S256"

        if extra_params:
            params.update(extra_params)

        url = f"{self._auth_url}?{urlencode(params)}"
        logger.debug(f"Built Keycloak authorize URL for realm {self.realm}")
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
            code_verifier: PKCE code verifier (required if PKCE was used).

        Returns:
            GrantResult with access token and optionally refresh token.

        Raises:
            ProviderError: If token exchange fails.
        """
        data: dict[str, str] = {
            "grant_type": "authorization_code",
            "client_id": self.client_id,
            "code": code,
            "redirect_uri": redirect_uri,
        }

        if self.client_secret:
            data["client_secret"] = self.client_secret

        if code_verifier:
            data["code_verifier"] = code_verifier

        async with create_mcp_http_client() as client:
            resp = await client.post(
                self._token_url,
                data=data,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )

        if resp.status_code != 200:
            try:
                error_data = resp.json()
                raise ProviderError(
                    error=error_data.get("error", "token_exchange_failed"),
                    error_description=error_data.get("error_description"),
                    status_code=resp.status_code,
                )
            except Exception:
                raise ProviderError(
                    error="token_exchange_failed",
                    error_description=resp.text,
                    status_code=resp.status_code,
                )

        payload = resp.json()

        if "error" in payload:
            raise ProviderError(
                error=payload["error"],
                error_description=payload.get("error_description"),
            )

        logger.info("Keycloak code exchange successful")

        return GrantResult(
            access_token=payload["access_token"],
            refresh_token=payload.get("refresh_token"),
            expires_in=payload.get("expires_in"),
            token_type=payload.get("token_type", "Bearer"),
            scope=payload.get("scope"),
            id_token=payload.get("id_token"),
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
            "refresh_token": refresh_token,
        }

        if self.client_secret:
            data["client_secret"] = self.client_secret

        if scopes:
            data["scope"] = " ".join(scopes)

        async with create_mcp_http_client() as client:
            resp = await client.post(
                self._token_url,
                data=data,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )

        if resp.status_code != 200:
            try:
                error_data = resp.json()
                raise ProviderError(
                    error=error_data.get("error", "refresh_failed"),
                    error_description=error_data.get("error_description"),
                    status_code=resp.status_code,
                )
            except Exception:
                raise ProviderError(
                    error="refresh_failed",
                    error_description=resp.text,
                    status_code=resp.status_code,
                )

        payload = resp.json()

        if "error" in payload:
            raise ProviderError(
                error=payload["error"],
                error_description=payload.get("error_description"),
            )

        logger.info("Keycloak token refresh successful")

        return GrantResult(
            access_token=payload["access_token"],
            refresh_token=payload.get("refresh_token", refresh_token),
            expires_in=payload.get("expires_in"),
            token_type=payload.get("token_type", "Bearer"),
            scope=payload.get("scope"),
            id_token=payload.get("id_token"),
            raw_response=payload,
        )

    async def fetch_user_info(self, access_token: str) -> UserInfo:
        """Fetch user information from Keycloak.

        Args:
            access_token: A valid Keycloak access token.

        Returns:
            UserInfo with Keycloak user data.

        Raises:
            ProviderError: If user info cannot be retrieved.
        """
        async with create_mcp_http_client() as client:
            resp = await client.get(
                self._userinfo_url,
                headers={"Authorization": f"Bearer {access_token}"},
            )

        if resp.status_code != 200:
            raise ProviderError(
                error="userinfo_failed",
                error_description=f"Failed to fetch user info: {resp.status_code}",
                status_code=resp.status_code,
            )

        profile = cast(dict[str, Any], resp.json())

        # Keycloak uses standard OIDC claims
        user_id = str(profile.get("sub", ""))
        if not user_id:
            raise ProviderError(
                error="invalid_profile",
                error_description="User profile missing sub claim",
            )

        logger.debug(f"Fetched Keycloak user info for user_id: {user_id}")

        return UserInfo(
            user_id=user_id,
            username=profile.get("preferred_username", profile.get("email")),
            email=profile.get("email"),
            name=profile.get("name"),
            avatar_url=profile.get("picture"),
            raw_profile=profile,
        )

    async def revoke_token(self, token: str, token_type_hint: str | None = None) -> bool:
        """Revoke a token at Keycloak.

        Args:
            token: The token to revoke.
            token_type_hint: Hint about token type ('access_token' or 'refresh_token').

        Returns:
            True if revocation succeeded.
        """
        data: dict[str, str] = {
            "client_id": self.client_id,
            "token": token,
        }

        if self.client_secret:
            data["client_secret"] = self.client_secret

        if token_type_hint:
            data["token_type_hint"] = token_type_hint

        async with create_mcp_http_client() as client:
            resp = await client.post(
                self._revoke_url,
                data=data,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )

        # Keycloak returns 200 on success
        if resp.status_code == 200:
            logger.info("Keycloak token revoked successfully")
            return True

        logger.warning(f"Keycloak token revocation failed: {resp.status_code}")
        return False


