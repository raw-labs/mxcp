"""Pydantic models for the auth module.

These types are used for server/user configuration and normalized auth data.

## Security-relevant configuration fields

- OAuth client **redirect URIs**: affect redirect binding and open-redirect risk.
- Provider **scope** strings: affect what permissions are requested from the upstream IdP.
- Provider **callback_path**: controls which HTTP route receives IdP callbacks.

Treat changes to these fields as security-sensitive and ensure they are covered by
tests and documented behavior.
"""

from typing import Any, Literal

from pydantic import ConfigDict

from mxcp.sdk.models import SdkBaseModel


class HttpTransportConfigModel(SdkBaseModel):
    """HTTP transport configuration for OAuth callbacks and URL building.

    Specialized for auth needs - handles scheme detection, base URLs, and proxy settings.
    """

    # Override frozen=True since this is a config object that may need updates
    model_config = ConfigDict(extra="forbid", frozen=False)

    port: int | None = None
    host: str | None = None
    scheme: Literal["http", "https"] | None = None
    base_url: str | None = None
    trust_proxy: bool | None = None
    stateless: bool | None = None


class OAuthClientConfigModel(SdkBaseModel):
    """OAuth client configuration.

    Represents a pre-configured OAuth client for the auth server.
    """

    client_id: str
    name: str
    client_secret: str | None = None  # None for public clients
    redirect_uris: list[str] | None = None
    grant_types: list[Literal["authorization_code", "refresh_token"]] | None = None
    scopes: list[str] | None = None


class GitHubAuthConfigModel(SdkBaseModel):
    """GitHub OAuth provider configuration.

    All fields required for GitHub authentication.
    """

    client_id: str
    client_secret: str
    scope: str | None = None
    callback_path: str
    auth_url: str
    token_url: str


class AtlassianAuthConfigModel(SdkBaseModel):
    """Atlassian OAuth provider configuration.

    For JIRA and Confluence Cloud authentication.
    """

    client_id: str
    client_secret: str
    # OAuth 2.0 scope string to request at the provider's /authorize endpoint.
    #
    # Intentionally required: the SDK provider adapter must not invent default
    # scopes (which could silently broaden permissions). Defaults, if any, belong
    # in higher-level configuration or templates.
    scope: str
    callback_path: str
    auth_url: str
    token_url: str


class SalesforceAuthConfigModel(SdkBaseModel):
    """Salesforce OAuth provider configuration.

    For Salesforce Cloud authentication.
    """

    client_id: str
    client_secret: str
    scope: str | None = None
    callback_path: str
    auth_url: str
    token_url: str


class KeycloakAuthConfigModel(SdkBaseModel):
    """Keycloak OAuth provider configuration.

    Includes Keycloak-specific fields like realm and server_url.
    """

    client_id: str
    client_secret: str
    realm: str
    server_url: str
    scope: str | None = None
    callback_path: str


class GoogleAuthConfigModel(SdkBaseModel):
    """Google OAuth provider configuration.

    For Google Workspace authentication including Calendar, Drive, etc.
    """

    client_id: str
    client_secret: str
    # OAuth 2.0 scope string to request at the provider's /authorize endpoint.
    #
    # Intentionally required: the SDK provider adapter must not invent default
    # scopes (which could silently broaden permissions). Defaults, if any, belong
    # in higher-level configuration or templates.
    scope: str
    callback_path: str
    auth_url: str
    token_url: str


class AuthPersistenceConfigModel(SdkBaseModel):
    """Authentication persistence backend configuration.

    Currently supports SQLite for storing tokens, auth codes, and clients.
    """

    # Override frozen=True since this is a config object
    model_config = ConfigDict(extra="forbid", frozen=False)

    type: Literal["sqlite"] | None = None
    path: str | None = None


class AuthorizationConfigModel(SdkBaseModel):
    """Authorization policy configuration.

    Defines access control requirements.
    """

    # Override frozen=True since this is a config object
    model_config = ConfigDict(extra="forbid", frozen=False)

    required_scopes: list[str] | None = None


class AuthConfigModel(SdkBaseModel):
    """Minimal authentication configuration for the OAuth server (issuer-mode)."""

    # Override frozen=True since this is a config object
    model_config = ConfigDict(extra="forbid", frozen=False)

    provider: Literal["none", "github", "atlassian", "salesforce", "keycloak", "google"] | None = (
        None
    )
    clients: list[OAuthClientConfigModel] | None = None  # Pre-configured OAuth clients
    authorization: AuthorizationConfigModel | None = None  # Authorization policies
    persistence: AuthPersistenceConfigModel | None = None  # Token/client persistence


class ExternalUserInfoModel(SdkBaseModel):
    """Result of exchanging an auth-code with an external IdP."""

    id: str
    scopes: list[str]
    raw_token: str  # original token from the IdP (JWT or opaque)
    provider: str


class UserContextModel(SdkBaseModel):
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


class StateMetaModel(SdkBaseModel):
    """OAuth state metadata for tracking authorization flows."""

    redirect_uri: str
    code_challenge: str | None = None
    redirect_uri_provided_explicitly: bool
    client_id: str
    callback_url: str | None = None  # Store callback URL for OAuth providers
