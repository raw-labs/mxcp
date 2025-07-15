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
from .context import get_user_context, set_user_context, reset_user_context
from .middleware import AuthenticationMiddleware

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
    # Functions
    "get_user_context",
    "set_user_context",
    "reset_user_context",
] 