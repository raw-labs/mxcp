"""OAuth provider implementations.

This module contains concrete implementations of OAuth providers.
"""

from .atlassian import AtlassianProviderAdapter
from .dummy import DummyProviderAdapter
from .github import GitHubOAuthHandler
from .google import GoogleProviderAdapter
from .keycloak import KeycloakOAuthHandler
from .salesforce import SalesforceOAuthHandler

__all__ = [
    "AtlassianProviderAdapter",
    "DummyProviderAdapter",
    "GitHubOAuthHandler",
    "GoogleProviderAdapter",
    "KeycloakOAuthHandler",
    "SalesforceOAuthHandler",
]
