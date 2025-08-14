"""OAuth provider implementations.

This module contains concrete implementations of OAuth providers.
"""

from .atlassian import AtlassianOAuthHandler
from .github import GitHubOAuthHandler
from .keycloak import KeycloakOAuthHandler
from .salesforce import SalesforceOAuthHandler

__all__ = [
    "AtlassianOAuthHandler",
    "GitHubOAuthHandler",
    "KeycloakOAuthHandler",
    "SalesforceOAuthHandler",
]
