"""OAuth provider implementations.

This module contains concrete implementations of OAuth providers.
"""

from .atlassian import AtlassianProviderAdapter
from .dummy import DummyProviderAdapter
from .github import GitHubProviderAdapter
from .google import GoogleProviderAdapter
from .keycloak import KeycloakProviderAdapter
from .oidc import OIDCProviderAdapter
from .salesforce import SalesforceProviderAdapter

__all__ = [
    "AtlassianProviderAdapter",
    "DummyProviderAdapter",
    "GitHubProviderAdapter",
    "GoogleProviderAdapter",
    "KeycloakProviderAdapter",
    "OIDCProviderAdapter",
    "SalesforceProviderAdapter",
]
