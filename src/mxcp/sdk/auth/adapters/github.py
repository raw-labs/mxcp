"""GitHub OAuth adapter for MXCP authentication.

This module provides a thin GitHub OAuth client that conforms to the
ProviderAdapter protocol. It handles only GitHub-specific OAuth communication,
delegating state management and storage to other components.
"""

import logging
from typing import Any, cast
from urllib.parse import urlencode

from mcp.shared._httpx_utils import create_mcp_http_client

from ..adapter import GrantResult, ProviderError, UserInfo
from ..models import GitHubAuthConfigModel, HttpTransportConfigModel

logger = logging.getLogger(__name__)

# GitHub OAuth endpoints
GITHUB_AUTH_URL = "https://github.com/login/oauth/authorize"
GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
GITHUB_API_URL = "https://api.github.com"

# Default scopes for GitHub
DEFAULT_SCOPES = ["user:email"]


class GitHubAdapter:
    """GitHub OAuth provider adapter.

    A thin client for GitHub OAuth that implements the ProviderAdapter protocol.
    This adapter handles only the protocol communication with GitHub, without
    managing state or callback routing.

    Note: GitHub does not support refresh tokens in the standard OAuth flow.

    Attributes:
        client_id: GitHub OAuth client ID.
        client_secret: GitHub OAuth client secret.
        scopes: Default scopes to request.
    """

    def __init__(
        self,
        config: GitHubAuthConfigModel,
        transport_config: HttpTransportConfigModel | None = None,
    ):
        """Initialize GitHub adapter.

        Args:
            config: GitHub-specific OAuth configuration.
            transport_config: HTTP transport configuration (unused, for interface consistency).
        """
        self.client_id = config.client_id
        self.client_secret = config.client_secret

        # Parse configured scopes
        scope_str = config.scope or " ".join(DEFAULT_SCOPES)
        self._default_scopes = scope_str.split()

        # Use configured URLs or defaults
        self._auth_url = config.auth_url or GITHUB_AUTH_URL
        self._token_url = config.token_url or GITHUB_TOKEN_URL

        logger.info("GitHubAdapter initialized")

    @property
    def provider_name(self) -> str:
        """Return the provider name."""
        return "github"

    async def build_authorize_url(
        self,
        redirect_uri: str,
        state: str,
        scopes: list[str] | None = None,
        code_challenge: str | None = None,
        code_challenge_method: str | None = None,
        extra_params: dict[str, str] | None = None,
    ) -> str:
        """Build the GitHub authorization URL.

        Note: GitHub does not support PKCE in its standard OAuth flow.

        Args:
            redirect_uri: The callback URL.
            state: CSRF protection state value.
            scopes: Scopes to request (uses defaults if None).
            code_challenge: Unused (GitHub doesn't support PKCE).
            code_challenge_method: Unused.
            extra_params: Additional parameters.

        Returns:
            Complete GitHub authorization URL.
        """
        effective_scopes = scopes if scopes is not None else self._default_scopes
        scope_str = " ".join(effective_scopes)

        params: dict[str, str] = {
            "client_id": self.client_id,
            "redirect_uri": redirect_uri,
            "scope": scope_str,
            "state": state,
        }

        if extra_params:
            params.update(extra_params)

        url = f"{self._auth_url}?{urlencode(params)}"
        logger.debug(f"Built GitHub authorize URL: {url[:100]}...")
        return url

    async def exchange_code(
        self,
        code: str,
        redirect_uri: str,
        code_verifier: str | None = None,
    ) -> GrantResult:
        """Exchange authorization code for tokens.

        Note: GitHub does not return refresh tokens.

        Args:
            code: The authorization code.
            redirect_uri: The redirect URI used in authorization.
            code_verifier: Unused (GitHub doesn't support PKCE).

        Returns:
            GrantResult with access token (no refresh token).

        Raises:
            ProviderError: If token exchange fails.
        """
        data: dict[str, str] = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "code": code,
            "redirect_uri": redirect_uri,
        }

        async with create_mcp_http_client() as client:
            resp = await client.post(
                self._token_url,
                data=data,
                headers={"Accept": "application/json"},
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

        logger.info("GitHub code exchange successful")

        return GrantResult(
            access_token=payload["access_token"],
            refresh_token=None,  # GitHub doesn't provide refresh tokens
            expires_in=None,  # GitHub tokens don't expire by default
            token_type=payload.get("token_type", "Bearer"),
            scope=payload.get("scope"),
            raw_response=payload,
        )

    async def refresh_token(
        self,
        refresh_token: str,
        scopes: list[str] | None = None,
    ) -> GrantResult:
        """Refresh an access token.

        Note: GitHub does not support refresh tokens in the standard OAuth flow.
        This method will always raise a ProviderError.

        Args:
            refresh_token: The refresh token (not supported).
            scopes: Scopes to request (not supported).

        Raises:
            ProviderError: Always, as GitHub doesn't support refresh.
        """
        raise ProviderError(
            error="refresh_not_supported",
            error_description="GitHub OAuth does not support refresh tokens",
        )

    async def fetch_user_info(self, access_token: str) -> UserInfo:
        """Fetch user information from GitHub.

        Args:
            access_token: A valid GitHub access token.

        Returns:
            UserInfo with GitHub user data.

        Raises:
            ProviderError: If user info cannot be retrieved.
        """
        async with create_mcp_http_client() as client:
            resp = await client.get(
                f"{GITHUB_API_URL}/user",
                headers={"Authorization": f"Bearer {access_token}"},
            )

        if resp.status_code != 200:
            raise ProviderError(
                error="userinfo_failed",
                error_description=f"Failed to fetch user info: {resp.status_code}",
                status_code=resp.status_code,
            )

        profile = cast(dict[str, Any], resp.json())

        # GitHub uses 'id' as the unique identifier
        user_id = str(profile.get("id", ""))
        if not user_id:
            raise ProviderError(
                error="invalid_profile",
                error_description="User profile missing ID",
            )

        logger.debug(f"Fetched GitHub user info for user_id: {user_id}")

        return UserInfo(
            user_id=user_id,
            username=profile.get("login"),
            email=profile.get("email"),
            name=profile.get("name"),
            avatar_url=profile.get("avatar_url"),
            raw_profile=profile,
        )

    async def revoke_token(self, token: str, token_type_hint: str | None = None) -> bool:
        """Revoke a token at GitHub.

        Note: GitHub requires a different endpoint for token revocation.
        This implementation uses the OAuth app authorization deletion endpoint.

        Args:
            token: The token to revoke.
            token_type_hint: Unused.

        Returns:
            True if revocation succeeded (or token was already invalid).
        """
        # GitHub revocation requires Basic auth with client_id:client_secret
        import base64
        auth_string = f"{self.client_id}:{self.client_secret}"
        auth_bytes = base64.b64encode(auth_string.encode()).decode()

        async with create_mcp_http_client() as client:
            resp = await client.delete(
                f"{GITHUB_API_URL}/applications/{self.client_id}/token",
                json={"access_token": token},
                headers={
                    "Authorization": f"Basic {auth_bytes}",
                    "Accept": "application/vnd.github+json",
                },
            )

        # GitHub returns 204 on success, 404 if token not found
        if resp.status_code in (204, 404):
            logger.info("GitHub token revoked successfully")
            return True

        logger.warning(f"GitHub token revocation failed: {resp.status_code}")
        return False


