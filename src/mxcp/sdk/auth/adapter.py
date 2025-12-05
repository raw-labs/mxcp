"""Provider adapter protocol for MXCP authentication.

This module defines the `ProviderAdapter` protocol - a thin interface for
Identity Provider (IdP) integrations. Provider adapters are pure IdP clients
that handle:
- Building authorization URLs
- Exchanging authorization codes for tokens
- Refreshing tokens
- Fetching user information

Provider adapters do NOT handle:
- Callback routing (handled by AuthService)
- State management (handled by SessionManager)
- Token storage (handled by TokenStore)

Example usage:
    from mxcp.sdk.auth.adapter import ProviderAdapter, GrantResult

    class MyProviderAdapter(ProviderAdapter):
        async def build_authorize_url(self, redirect_uri: str, state: str, scopes: list[str]) -> str:
            return f"https://provider.com/authorize?..."
        
        async def exchange_code(self, code: str, redirect_uri: str) -> GrantResult:
            # Exchange code for tokens
            return GrantResult(access_token="...", ...)
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

logger = logging.getLogger(__name__)


@dataclass
class GrantResult:
    """Result of a successful OAuth grant (code exchange or token refresh).

    This is the standardized result returned by provider adapters after
    exchanging an authorization code or refreshing a token.

    Attributes:
        access_token: The provider's access token.
        refresh_token: The provider's refresh token (if issued).
        expires_in: Token lifetime in seconds (if provided).
        token_type: Token type (usually "Bearer").
        scope: Space-separated scopes actually granted (may differ from requested).
        id_token: OpenID Connect ID token (if issued).
        user_id: User identifier extracted from the token response.
        raw_response: The complete token response from the provider.
    """

    access_token: str
    refresh_token: str | None = None
    expires_in: int | None = None
    token_type: str = "Bearer"
    scope: str | None = None
    id_token: str | None = None
    user_id: str | None = None
    raw_response: dict[str, Any] = field(default_factory=dict)


@dataclass
class UserInfo:
    """Standardized user information from a provider.

    Attributes:
        user_id: Unique identifier for the user at the provider.
        username: Username or login name.
        email: User's email address.
        name: User's display name.
        avatar_url: URL to user's profile picture.
        raw_profile: Complete profile data from the provider.
    """

    user_id: str
    username: str | None = None
    email: str | None = None
    name: str | None = None
    avatar_url: str | None = None
    raw_profile: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class ProviderAdapter(Protocol):
    """Protocol for OAuth/OIDC provider adapters.

    Provider adapters are thin clients that communicate with Identity Providers.
    They handle the protocol-specific details of OAuth/OIDC flows but delegate
    state management and storage to other components.

    All methods are async to support non-blocking I/O with the IdP.
    """

    @property
    def provider_name(self) -> str:
        """Return the provider name (e.g., 'google', 'keycloak')."""
        ...

    async def build_authorize_url(
        self,
        redirect_uri: str,
        state: str,
        scopes: list[str] | None = None,
        code_challenge: str | None = None,
        code_challenge_method: str | None = None,
        extra_params: dict[str, str] | None = None,
    ) -> str:
        """Build the authorization URL for the OAuth flow.

        Args:
            redirect_uri: The callback URL to redirect to after authorization.
            state: Opaque state value for CSRF protection.
            scopes: List of scopes to request (uses provider defaults if None).
            code_challenge: PKCE code challenge (for public clients).
            code_challenge_method: PKCE method (e.g., 'S256').
            extra_params: Additional provider-specific parameters.

        Returns:
            The complete authorization URL to redirect the user to.
        """
        ...

    async def exchange_code(
        self,
        code: str,
        redirect_uri: str,
        code_verifier: str | None = None,
    ) -> GrantResult:
        """Exchange an authorization code for tokens.

        Args:
            code: The authorization code from the callback.
            redirect_uri: The redirect URI used in the authorization request.
            code_verifier: PKCE code verifier (if PKCE was used).

        Returns:
            GrantResult containing access token and optionally refresh token.

        Raises:
            ProviderError: If the token exchange fails.
        """
        ...

    async def refresh_token(
        self,
        refresh_token: str,
        scopes: list[str] | None = None,
    ) -> GrantResult:
        """Refresh an access token using a refresh token.

        Args:
            refresh_token: The refresh token.
            scopes: Scopes to request (usually same as original).

        Returns:
            GrantResult containing the new access token.

        Raises:
            ProviderError: If the refresh fails.
        """
        ...

    async def fetch_user_info(self, access_token: str) -> UserInfo:
        """Fetch user information from the provider.

        Args:
            access_token: A valid access token for the user.

        Returns:
            UserInfo with standardized user data.

        Raises:
            ProviderError: If user info cannot be retrieved.
        """
        ...

    async def revoke_token(self, token: str, token_type_hint: str | None = None) -> bool:
        """Revoke a token at the provider (if supported).

        Args:
            token: The token to revoke.
            token_type_hint: Hint about token type ('access_token' or 'refresh_token').

        Returns:
            True if revocation succeeded or was accepted, False otherwise.
        """
        ...


class ProviderError(Exception):
    """Error from an OAuth provider.

    Attributes:
        error: OAuth error code (e.g., 'invalid_grant').
        error_description: Human-readable error description.
        status_code: HTTP status code from the provider.
    """

    def __init__(
        self,
        error: str,
        error_description: str | None = None,
        status_code: int | None = None,
    ):
        self.error = error
        self.error_description = error_description
        self.status_code = status_code
        message = f"{error}: {error_description}" if error_description else error
        super().__init__(message)


