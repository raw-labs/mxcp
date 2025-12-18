"""Authentication helper functions for translating between MXCP config models and SDK auth types."""

from mxcp.sdk.auth.contracts import ProviderAdapter
from mxcp.sdk.auth.models import (
    AuthConfigModel,
    AuthorizationConfigModel,
    AuthPersistenceConfigModel,
    GoogleAuthConfigModel,
    HttpTransportConfigModel,
    OAuthClientConfigModel,
)
from mxcp.sdk.auth.providers.google import GoogleProviderAdapter
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

    if provider == "google":
        google_config = user_auth_config.google
        if not google_config:
            raise ValueError("Google provider selected but no Google configuration found")
        google_model = GoogleAuthConfigModel.model_validate(
            google_config.model_dump(exclude_none=True)
        )
        return GoogleProviderAdapter(google_model)

    raise ValueError(f"Unsupported provider for adapter: {provider}")
