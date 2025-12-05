"""Provider adapters for MXCP authentication.

This package contains thin IdP client implementations that conform to
the ProviderAdapter protocol. These adapters handle only the protocol-specific
communication with Identity Providers.

Each adapter is a pure IdP client that handles:
- Building authorization URLs
- Exchanging authorization codes for tokens
- Refreshing tokens (where supported)
- Fetching user information
- Revoking tokens (where supported)

Adapters do NOT handle:
- Callback routing (handled by AuthService)
- State management (handled by SessionManager)
- Token storage (handled by TokenStore)
"""

from .atlassian import AtlassianAdapter
from .github import GitHubAdapter
from .google import GoogleAdapter
from .keycloak import KeycloakAdapter
from .salesforce import SalesforceAdapter

__all__ = [
    "AtlassianAdapter",
    "GitHubAdapter",
    "GoogleAdapter",
    "KeycloakAdapter",
    "SalesforceAdapter",
]

