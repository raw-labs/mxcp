"""Authentication helper functions for translating between MXCP config models and SDK auth types."""

from typing import Any, cast

from mxcp.sdk.auth.contracts import ProviderAdapter
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
from mxcp.sdk.auth.providers.atlassian import AtlassianProviderAdapter
from mxcp.sdk.auth.providers.github import GitHubProviderAdapter
from mxcp.sdk.auth.providers.google import GoogleProviderAdapter
from mxcp.sdk.auth.providers.keycloak import KeycloakProviderAdapter
from mxcp.sdk.auth.providers.salesforce import SalesforceProviderAdapter
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


def _model_dump_with_scope(config: Any) -> dict[str, Any]:
    data = cast(dict[str, Any], config.model_dump(exclude_none=True))
    data.setdefault("scope", "")
    return data


def create_url_builder(user_config: UserConfigModel) -> URLBuilder:
    """Create a URL builder from user configuration.

    Args:
        user_config: User configuration dictionary

    Returns:
        Configured URLBuilder instance
    """
    transport_config = translate_transport_config(user_config.transport.http)
    return URLBuilder(transport_config)


def create_provider_adapter(
    user_auth_config: UserAuthConfigModel,
    host: str = "localhost",
    port: int = 8000,
    user_config: UserConfigModel | None = None,
) -> ProviderAdapter | None:
    """Create a ProviderAdapter for issuer-mode OAuth."""
    provider = user_auth_config.provider
    if provider == "none":
        return None

    if provider == "atlassian":
        atlassian_config = user_auth_config.atlassian
        if not atlassian_config:
            raise ValueError("Atlassian provider selected but no Atlassian configuration found")
        atlassian_model = AtlassianAuthConfigModel.model_validate(
            _model_dump_with_scope(atlassian_config)
        )
        return AtlassianProviderAdapter(atlassian_model)

    if provider == "google":
        google_config = user_auth_config.google
        if not google_config:
            raise ValueError("Google provider selected but no Google configuration found")
        google_model = GoogleAuthConfigModel.model_validate(_model_dump_with_scope(google_config))
        return GoogleProviderAdapter(google_model)

    if provider == "github":
        github_config = user_auth_config.github
        if not github_config:
            raise ValueError("GitHub provider selected but no GitHub configuration found")
        github_model = GitHubAuthConfigModel.model_validate(_model_dump_with_scope(github_config))
        return GitHubProviderAdapter(github_model)

    if provider == "keycloak":
        keycloak_config = user_auth_config.keycloak
        if not keycloak_config:
            raise ValueError("Keycloak provider selected but no Keycloak configuration found")
        keycloak_model = KeycloakAuthConfigModel.model_validate(
            _model_dump_with_scope(keycloak_config)
        )
        return KeycloakProviderAdapter(keycloak_model)

    if provider == "salesforce":
        salesforce_config = user_auth_config.salesforce
        if not salesforce_config:
            raise ValueError("Salesforce provider selected but no Salesforce configuration found")
        salesforce_model = SalesforceAuthConfigModel.model_validate(
            _model_dump_with_scope(salesforce_config)
        )
        return SalesforceProviderAdapter(salesforce_model)

    raise ValueError(f"Unsupported provider for adapter: {provider}")
