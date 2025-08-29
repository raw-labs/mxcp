"""OAuth provider implementations.

This module contains concrete implementations of OAuth providers.
"""

from .atlassian import AtlassianOAuthHandler
from .github import GitHubOAuthHandler
from .google import GoogleOAuthHandler
from .keycloak import KeycloakOAuthHandler
from .salesforce import SalesforceOAuthHandler

__all__ = [
    "AtlassianOAuthHandler",
    "GitHubOAuthHandler",
    "GoogleOAuthHandler",
    "KeycloakOAuthHandler",
    "SalesforceOAuthHandler",
]
