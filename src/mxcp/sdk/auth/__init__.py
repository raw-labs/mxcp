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
from mxcp.sdk.auth.models import UserContextModel
from mxcp.sdk.auth.context import set_user_context, get_user_context

# Create and set user context
user = UserContextModel(
    provider="internal",
    user_id="alice",
    username="alice",
)
set_user_context(user)

# Retrieve context in other parts of code
current_user = get_user_context()
print(f"Current user: {current_user.username}")
```

### OAuth Configuration
```python
from mxcp.sdk.auth import AuthConfigModel, GitHubAuthConfigModel

config = AuthConfigModel(
    provider="github",
)
github_config = GitHubAuthConfigModel(
    client_id="your-client-id",
    client_secret="your-secret",
    scope="user:email",
    callback_path="/auth/callback",
    auth_url="https://github.com/login/oauth/authorize",
    token_url="https://github.com/login/oauth/access_token"
)
```
"""

from .auth_service import AccessTokenResponse, AuthService
from .base import ExternalOAuthHandler, GeneralOAuthAuthorizationServer
from .context import get_user_context, reset_user_context, set_user_context
from .contracts import (
    GrantResult,
    ProviderAdapter,
    ProviderError,
    ScopeMapper,
    Session,
    UserInfo,
)
from .middleware import AuthenticationMiddleware
from .models import (
    AtlassianAuthConfigModel,
    AuthConfigModel,
    AuthorizationConfigModel,
    AuthPersistenceConfigModel,
    ExternalUserInfoModel,
    GitHubAuthConfigModel,
    GoogleAuthConfigModel,
    HttpTransportConfigModel,
    KeycloakAuthConfigModel,
    OAuthClientConfigModel,
    SalesforceAuthConfigModel,
    StateMetaModel,
    UserContextModel,
)
from .session_manager import SessionManager
from .storage import (
    AuthCodeRecord,
    SqliteTokenStore,
    StateRecord,
    StoredSession,
    TokenStore,
)

__all__ = [
    # Types
    "AuthConfigModel",
    "HttpTransportConfigModel",
    "OAuthClientConfigModel",
    "GitHubAuthConfigModel",
    "AtlassianAuthConfigModel",
    "SalesforceAuthConfigModel",
    "KeycloakAuthConfigModel",
    "GoogleAuthConfigModel",
    "AuthPersistenceConfigModel",
    "AuthorizationConfigModel",
    "StateMetaModel",
    # Core classes
    "ExternalOAuthHandler",
    "ExternalUserInfoModel",
    "UserContextModel",
    "AccessTokenResponse",
    "AuthService",
    "GeneralOAuthAuthorizationServer",
    "AuthenticationMiddleware",
    # Contracts
    "GrantResult",
    "ProviderAdapter",
    "ProviderError",
    "ScopeMapper",
    "Session",
    "UserInfo",
    "SessionManager",
    # Storage
    "AuthCodeRecord",
    "SqliteTokenStore",
    "StateRecord",
    "StoredSession",
    "TokenStore",
    # Context management
    "get_user_context",
    "set_user_context",
    "reset_user_context",
]
