# -*- coding: utf-8 -*-
"""MXCP SDK authentication package."""

from .types import (
    AuthConfig,
    HttpTransportConfig,
    OAuthClientConfig,
    GitHubAuthConfig,
    AtlassianAuthConfig,
    SalesforceAuthConfig,
    KeycloakAuthConfig,
    AuthPersistenceConfig,
    AuthorizationConfig,
    ExternalUserInfo,
    UserContext,
    StateMeta,
)
from .providers import (
    ExternalOAuthHandler,
    GeneralOAuthAuthorizationServer,
)
from .middleware import AuthenticationMiddleware
from .context import get_user_context, set_user_context, reset_user_context

__all__ = [
    # Types
    "AuthConfig",
    "HttpTransportConfig", 
    "OAuthClientConfig",
    "GitHubAuthConfig",
    "AtlassianAuthConfig",
    "SalesforceAuthConfig",
    "KeycloakAuthConfig",
    "AuthPersistenceConfig",
    "AuthorizationConfig",
    # Core classes
    "ExternalOAuthHandler",
    "ExternalUserInfo",
    "UserContext",
    "GeneralOAuthAuthorizationServer",
    "AuthenticationMiddleware",
    # Context management
    "get_user_context",
    "set_user_context",
    "reset_user_context"
] 