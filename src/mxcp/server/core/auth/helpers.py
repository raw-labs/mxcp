"""Authentication helper functions for translating between MXCP config models and SDK auth types."""

from mxcp.sdk.auth import AuthService
from mxcp.sdk.auth.models import (
    AtlassianAuthConfigModel,
    AuthConfigModel,
    AuthorizationConfigModel,
    AuthPersistenceConfigModel,
    GitHubAuthConfigModel,
    GoogleAuthConfigModel,
    HttpTransportConfigModel,
    KeycloakAuthConfigModel,
    OAuthClientConfigModel,
    SalesforceAuthConfigModel,
)
from mxcp.sdk.auth.url_utils import URLBuilder
from mxcp.server.core.config.models import (
    UserAuthConfigModel,
    UserConfigModel,
    UserHttpTransportConfigModel,
)


def translate_auth_config(user_auth_config: UserAuthConfigModel) -> AuthConfigModel:
    """Translate user auth config to minimal SDK auth config."""
    clients: list[OAuthClientConfigModel] | None = None
    if user_auth_config.clients:
        clients = [
            OAuthClientConfigModel.model_validate(client.model_dump(exclude_none=True))
            for client in user_auth_config.clients
        ]

    authorization: AuthorizationConfigModel | None = None
    if user_auth_config.authorization:
        authorization = AuthorizationConfigModel.model_validate(
            user_auth_config.authorization.model_dump(exclude_none=True)
        )

    persistence: AuthPersistenceConfigModel | None = None
    if user_auth_config.persistence:
        persistence = AuthPersistenceConfigModel.model_validate(
            user_auth_config.persistence.model_dump(exclude_none=True)
        )

    return AuthConfigModel(
        provider=user_auth_config.provider,
        clients=clients,
        authorization=authorization,
        persistence=persistence,
    )


def translate_transport_config(
    user_transport_config: UserHttpTransportConfigModel | None,
) -> HttpTransportConfigModel | None:
    """Translate user HTTP transport config to SDK transport config.

    Args:
        user_transport_config: User configuration transport section

    Returns:
        SDK-compatible HTTP transport configuration
    """
    if not user_transport_config:
        return None

    return HttpTransportConfigModel.model_validate(
        user_transport_config.model_dump(exclude_none=True)
    )


def _get_provider_config(
    user_auth_config: UserAuthConfigModel,
) -> (
    GoogleAuthConfigModel
    | KeycloakAuthConfigModel
    | GitHubAuthConfigModel
    | AtlassianAuthConfigModel
    | SalesforceAuthConfigModel
    | None
):
    """Extract and validate provider-specific config from user config.

    Args:
        user_auth_config: User authentication configuration

    Returns:
        Provider-specific config model or None if provider is 'none'

    Raises:
        ValueError: If provider config is missing or invalid
    """
    provider = user_auth_config.provider

    if provider == "none":
        return None

    if provider == "google":
        google_config = user_auth_config.google
        if not google_config:
            raise ValueError("Google provider selected but no Google configuration found")
        return GoogleAuthConfigModel.model_validate(
            google_config.model_dump(exclude_none=True)
        )

    if provider == "keycloak":
        keycloak_config = user_auth_config.keycloak
        if not keycloak_config:
            raise ValueError("Keycloak provider selected but no Keycloak configuration found")
        return KeycloakAuthConfigModel.model_validate(
            keycloak_config.model_dump(exclude_none=True)
        )

    if provider == "github":
        github_config = user_auth_config.github
        if not github_config:
            raise ValueError("GitHub provider selected but no GitHub configuration found")
        return GitHubAuthConfigModel.model_validate(
            github_config.model_dump(exclude_none=True)
        )

    if provider == "atlassian":
        atlassian_config = user_auth_config.atlassian
        if not atlassian_config:
            raise ValueError("Atlassian provider selected but no Atlassian configuration found")
        return AtlassianAuthConfigModel.model_validate(
            atlassian_config.model_dump(exclude_none=True)
        )

    if provider == "salesforce":
        salesforce_config = user_auth_config.salesforce
        if not salesforce_config:
            raise ValueError("Salesforce provider selected but no Salesforce configuration found")
        return SalesforceAuthConfigModel.model_validate(
            salesforce_config.model_dump(exclude_none=True)
        )

    raise ValueError(f"Unsupported auth provider: {provider}")


def create_url_builder(user_config: UserConfigModel) -> URLBuilder:
    """Create a URL builder from user configuration.

    Args:
        user_config: User configuration dictionary

    Returns:
        Configured URLBuilder instance
    """
    transport_config = translate_transport_config(user_config.transport.http)
    return URLBuilder(transport_config)


def create_auth_service(
    user_auth_config: UserAuthConfigModel,
    host: str = "localhost",
    port: int = 8000,
    user_config: UserConfigModel | None = None,
) -> AuthService:
    """Create an AuthService from user configuration.

    This helper translates user config to SDK types and creates the AuthService.

    Args:
        user_auth_config: User authentication configuration
        host: The server host to use for callback URLs
        port: The server port to use for callback URLs
        user_config: Full user configuration for transport settings (optional)

    Returns:
        Configured AuthService instance
    """
    provider = user_auth_config.provider

    # Translate to SDK config
    auth_config = translate_auth_config(user_auth_config)
    transport_config = None
    if user_config:
        transport_config = translate_transport_config(
            user_config.transport.http if user_config.transport else None
        )

    if provider == "none":
        return AuthService(
            auth_config=auth_config,
            transport_config=transport_config,
            mode="disabled",
        )

    # Get provider-specific config
    provider_config = _get_provider_config(user_auth_config)
    if provider_config is None:
        return AuthService(
            auth_config=auth_config,
            transport_config=transport_config,
            mode="disabled",
        )

    # Create AuthService with the provider config
    return AuthService.from_provider_config(
        auth_config=auth_config,
        provider_config=provider_config,
        transport_config=transport_config,
        host=host,
        port=port,
    )
