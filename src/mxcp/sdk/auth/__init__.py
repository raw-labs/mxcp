"""MXCP SDK Authentication - OAuth providers and user context management.

This package provides comprehensive authentication functionality including:
- OAuth 2.0 providers (GitHub, Atlassian, Salesforce, Keycloak)
- User context management with thread-local storage
- Authentication middleware for HTTP requests
- Token persistence and session management

## Key Components

### OAuth Providers
- `GeneralOAuthAuthorizationServer`: Core OAuth server implementation
- `ExternalOAuthHandler`: Protocol for OAuth provider integrations
- Provider-specific configs: `GitHubAuthConfig`, `AtlassianAuthConfig`, etc.

### User Context
- `UserContext`: Represents authenticated user with roles and permissions
- `get_user_context()`, `set_user_context()`: Thread-safe context management

### Middleware
- `AuthenticationMiddleware`: HTTP middleware for request authentication

## Quick Examples

### Basic User Context
```python
from mxcp.sdk.auth import UserContext, set_user_context, get_user_context

# Create and set user context
user = UserContext(
    username="alice",
    role="analyst",
    scopes=["read:data", "write:reports"]
)
set_user_context(user)

# Retrieve context in other parts of code
current_user = get_user_context()
print(f"Current user: {current_user.username}")
```

### OAuth Configuration
```python
from mxcp.sdk.auth import AuthConfig, GitHubAuthConfig

config = AuthConfig(
    provider="github",
    github=GitHubAuthConfig(
        client_id="your-client-id",
        client_secret="your-secret",
        scope="user:email",
        callback_path="/auth/callback",
        auth_url="https://github.com/login/oauth/authorize",
        token_url="https://github.com/login/oauth/access_token"
    )
)
```
"""

from ._types import (
    AtlassianAuthConfig,
    AuthConfig,
    AuthorizationConfig,
    AuthPersistenceConfig,
    ExternalUserInfo,
    GitHubAuthConfig,
    HttpTransportConfig,
    KeycloakAuthConfig,
    OAuthClientConfig,
    SalesforceAuthConfig,
    UserContext,
)
from .base import (
    ExternalOAuthHandler,
    GeneralOAuthAuthorizationServer,
)
from .context import get_user_context, reset_user_context, set_user_context
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
    # Context management
    "get_user_context",
    "set_user_context",
    "reset_user_context",
]
