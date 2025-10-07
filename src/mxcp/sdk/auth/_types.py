"""Standalone authentication types for MXCP SDK.

These types are specialized for the auth package and don't depend on other MXCP packages.
Callers need to translate their config types to these auth-specific types.
"""

from dataclasses import dataclass
from typing import Any, Literal, TypedDict


class HttpTransportConfig(TypedDict, total=False):
    """HTTP transport configuration for OAuth callbacks and URL building.

    Specialized for auth needs - handles scheme detection, base URLs, and proxy settings.
    """

    port: int | None
    host: str | None
    scheme: Literal["http", "https"] | None
    base_url: str | None
    trust_proxy: bool | None
    stateless: bool | None


class OAuthClientConfig(TypedDict):
    """OAuth client configuration.

    Represents a pre-configured OAuth client for the auth server.
    """

    client_id: str
    name: str
    client_secret: str | None  # None for public clients
    redirect_uris: list[str] | None
    grant_types: list[Literal["authorization_code", "refresh_token"]] | None
    scopes: list[str] | None


class GitHubAuthConfig(TypedDict):
    """GitHub OAuth provider configuration.

    All fields required for GitHub authentication.
    """

    client_id: str
    client_secret: str
    scope: str | None
    callback_path: str
    auth_url: str
    token_url: str


class AtlassianAuthConfig(TypedDict):
    """Atlassian OAuth provider configuration.

    For JIRA and Confluence Cloud authentication.
    """

    client_id: str
    client_secret: str
    scope: str | None
    callback_path: str
    auth_url: str
    token_url: str


class SalesforceAuthConfig(TypedDict):
    """Salesforce OAuth provider configuration.

    For Salesforce Cloud authentication.
    """

    client_id: str
    client_secret: str
    scope: str | None
    callback_path: str
    auth_url: str
    token_url: str


class KeycloakAuthConfig(TypedDict):
    """Keycloak OAuth provider configuration.

    Includes Keycloak-specific fields like realm and server_url.
    """

    client_id: str
    client_secret: str
    realm: str
    server_url: str
    scope: str | None
    callback_path: str


class GoogleAuthConfig(TypedDict):
    """Google OAuth provider configuration.

    For Google Workspace authentication including Calendar, Drive, etc.
    """

    client_id: str
    client_secret: str
    scope: str | None
    callback_path: str
    auth_url: str
    token_url: str


class AuthPersistenceConfig(TypedDict, total=False):
    """Authentication persistence backend configuration.

    Currently supports SQLite for storing tokens, auth codes, and clients.
    """

    type: Literal["sqlite"] | None
    path: str | None


class AuthorizationConfig(TypedDict, total=False):
    """Authorization policy configuration.

    Defines access control requirements.
    """

    required_scopes: list[str] | None


class AuthConfig(TypedDict, total=False):
    """Minimal authentication configuration for the OAuth server.

    This type only contains fields needed by GeneralOAuthAuthorizationServer.
    Provider-specific configs are passed directly to their respective handlers.
    """

    provider: Literal["none", "github", "atlassian", "salesforce", "keycloak", "google"] | None
    cache_ttl: int | None  # Cache TTL in seconds for user context caching
    cleanup_interval: int | None  # Cleanup interval in seconds for OAuth mappings (default: 300)
    clients: list[OAuthClientConfig] | None  # Pre-configured OAuth clients
    authorization: AuthorizationConfig | None  # Authorization policies
    persistence: AuthPersistenceConfig | None  # Token/client persistence


@dataclass
class ExternalUserInfo:
    """Result of exchanging an auth-code with an external IdP."""

    id: str
    scopes: list[str]
    raw_token: str  # original access token from the IdP (JWT or opaque)
    provider: str
    refresh_token: str | None = None  # refresh token for renewing access tokens


@dataclass
class UserContext:
    """Standardized user context that all OAuth providers must return.

    This represents the common denominator of user information across all providers.
    Some fields may be None if the provider doesn't support them.
    """

    provider: str  # Provider name (e.g., 'github', 'google', 'microsoft')
    user_id: str  # Unique user identifier from the provider
    username: str  # Display username/handle
    email: str | None = None  # User's email address
    name: str | None = None  # User's display name
    avatar_url: str | None = None  # User's profile picture URL
    raw_profile: dict[str, Any] | None = None  # Raw profile data for debugging
    external_token: str | None = None  # Original OAuth provider token


@dataclass
class StateMeta:
    """OAuth state metadata for tracking authorization flows."""

    redirect_uri: str
    code_challenge: str | None
    redirect_uri_provided_explicitly: bool
    client_id: str
    callback_url: str | None = None  # Store callback URL for OAuth providers
