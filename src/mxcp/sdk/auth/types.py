# -*- coding: utf-8 -*-
"""Standalone authentication types for MXCP SDK.

These types are specialized for the auth package and don't depend on other MXCP packages.
Callers need to translate their config types to these auth-specific types.
"""
from typing import TypedDict, List, Dict, Optional, Literal, Any


class HttpTransportConfig(TypedDict, total=False):
    """HTTP transport configuration for OAuth callbacks and URL building.
    
    Specialized for auth needs - handles scheme detection, base URLs, and proxy settings.
    """
    port: Optional[int]
    host: Optional[str]
    scheme: Optional[Literal["http", "https"]]
    base_url: Optional[str]
    trust_proxy: Optional[bool]
    stateless: Optional[bool]


class OAuthClientConfig(TypedDict):
    """OAuth client configuration.
    
    Represents a pre-configured OAuth client for the auth server.
    """
    client_id: str
    name: str
    client_secret: Optional[str]  # None for public clients
    redirect_uris: Optional[List[str]]
    grant_types: Optional[List[Literal["authorization_code", "refresh_token"]]]
    scopes: Optional[List[str]]


class GitHubAuthConfig(TypedDict):
    """GitHub OAuth provider configuration.
    
    All fields required for GitHub authentication.
    """
    client_id: str
    client_secret: str
    scope: Optional[str]
    callback_path: str
    auth_url: str
    token_url: str


class AtlassianAuthConfig(TypedDict):
    """Atlassian OAuth provider configuration.
    
    For JIRA and Confluence Cloud authentication.
    """
    client_id: str
    client_secret: str
    scope: Optional[str]
    callback_path: str
    auth_url: str
    token_url: str


class SalesforceAuthConfig(TypedDict):
    """Salesforce OAuth provider configuration.
    
    For Salesforce Cloud authentication.
    """
    client_id: str
    client_secret: str
    scope: Optional[str]
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
    scope: Optional[str]
    callback_path: str


class AuthPersistenceConfig(TypedDict, total=False):
    """Authentication persistence backend configuration.
    
    Currently supports SQLite for storing tokens, auth codes, and clients.
    """
    type: Optional[Literal["sqlite"]]
    path: Optional[str]


class AuthorizationConfig(TypedDict, total=False):
    """Authorization policy configuration.
    
    Defines access control requirements.
    """
    required_scopes: Optional[List[str]]


class AuthConfig(TypedDict, total=False):
    """Minimal authentication configuration for the OAuth server.
    
    This type only contains fields needed by GeneralOAuthAuthorizationServer.
    Provider-specific configs are passed directly to their respective handlers.
    """
    provider: Optional[Literal["none", "github", "atlassian", "salesforce", "keycloak"]]
    clients: Optional[List[OAuthClientConfig]]  # Pre-configured OAuth clients
    authorization: Optional[AuthorizationConfig]  # Authorization policies
    persistence: Optional[AuthPersistenceConfig]  # Token/client persistence


from dataclasses import dataclass


@dataclass
class ExternalUserInfo:
    """Result of exchanging an auth-code with an external IdP."""
    id: str
    scopes: list[str]
    raw_token: str  # original token from the IdP (JWT or opaque)
    provider: str


@dataclass
class UserContext:
    """Standardized user context that all OAuth providers must return.
    
    This represents the common denominator of user information across all providers.
    Some fields may be None if the provider doesn't support them.
    """
    provider: str  # Provider name (e.g., 'github', 'google', 'microsoft')
    user_id: str   # Unique user identifier from the provider
    username: str  # Display username/handle
    email: Optional[str] = None      # User's email address
    name: Optional[str] = None       # User's display name
    avatar_url: Optional[str] = None # User's profile picture URL
    raw_profile: Optional[Dict[str, Any]] = None  # Raw profile data for debugging
    external_token: Optional[str] = None  # Original OAuth provider token


@dataclass
class StateMeta:
    """OAuth state metadata for tracking authorization flows."""
    redirect_uri: str
    code_challenge: Optional[str]
    redirect_uri_provided_explicitly: bool
    client_id: str
    callback_url: Optional[str] = None  # Store callback URL for OAuth providers


# Type aliases for backward compatibility during migration
UserAuthConfig = AuthConfig  # Alias for transition period
UserHttpTransportConfig = HttpTransportConfig  # Alias for transition period 