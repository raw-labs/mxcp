"""Authentication helper functions for translating between user config and SDK auth types.

These functions help bridge the gap between MXCP's configuration format and the
standalone SDK auth types. They don't belong in the SDK itself since they're
specific to MXCP's config structure.
"""

from mxcp.core.config._types import UserAuthConfig, UserConfig, UserHttpTransportConfig
from mxcp.sdk.auth._types import AuthConfig, HttpTransportConfig
from mxcp.sdk.auth.providers.atlassian import AtlassianOAuthHandler
from mxcp.sdk.auth.providers.github import GitHubOAuthHandler
from mxcp.sdk.auth.providers.keycloak import KeycloakOAuthHandler
from mxcp.sdk.auth import ExternalOAuthHandler
from mxcp.sdk.auth.providers.salesforce import SalesforceOAuthHandler
from mxcp.sdk.auth.url_utils import URLBuilder


def translate_auth_config(user_auth_config: UserAuthConfig) -> AuthConfig:
    """Translate user auth config to minimal SDK auth config.

    Only extracts fields needed by GeneralOAuthAuthorizationServer.
    Provider-specific configs are handled separately.

    Args:
        user_auth_config: User configuration auth section

    Returns:
        Minimal SDK-compatible auth configuration
    """
    return {
        "provider": user_auth_config.get("provider"),
        "clients": user_auth_config.get("clients"),
        "authorization": user_auth_config.get("authorization"),
        "persistence": user_auth_config.get("persistence"),
    }


def translate_transport_config(
    user_transport_config: UserHttpTransportConfig | None,
) -> HttpTransportConfig | None:
    """Translate user HTTP transport config to SDK transport config.

    Args:
        user_transport_config: User configuration transport section

    Returns:
        SDK-compatible HTTP transport configuration
    """
    if not user_transport_config:
        return None

    return {
        "port": user_transport_config.get("port"),
        "host": user_transport_config.get("host"),
        "scheme": user_transport_config.get("scheme"),
        "base_url": user_transport_config.get("base_url"),
        "trust_proxy": user_transport_config.get("trust_proxy"),
        "stateless": user_transport_config.get("stateless"),
    }


def create_oauth_handler(
    user_auth_config: UserAuthConfig,
    host: str = "localhost",
    port: int = 8000,
    user_config: UserConfig | None = None,
) -> ExternalOAuthHandler | None:
    """Create an OAuth handler from user configuration.

    This helper translates user config to SDK types and instantiates the appropriate handler.

    Args:
        user_auth_config: User authentication configuration
        host: The server host to use for callback URLs
        port: The server port to use for callback URLs
        user_config: Full user configuration for transport settings (optional)

    Returns:
        OAuth handler instance or None if provider is 'none'
    """
    provider = user_auth_config.get("provider", "none")

    if provider == "none":
        return None

    # Extract transport config if available
    transport_config = None
    if user_config and "transport" in user_config:
        transport = user_config["transport"]
        user_transport = transport.get("http") if transport else None
        transport_config = translate_transport_config(user_transport)

    if provider == "github":

        github_config = user_auth_config.get("github")
        if not github_config:
            raise ValueError("GitHub provider selected but no GitHub configuration found")
        return GitHubOAuthHandler(github_config, transport_config, host=host, port=port)

    elif provider == "atlassian":

        atlassian_config = user_auth_config.get("atlassian")
        if not atlassian_config:
            raise ValueError("Atlassian provider selected but no Atlassian configuration found")
        return AtlassianOAuthHandler(atlassian_config, transport_config, host=host, port=port)

    elif provider == "salesforce":

        salesforce_config = user_auth_config.get("salesforce")
        if not salesforce_config:
            raise ValueError("Salesforce provider selected but no Salesforce configuration found")
        return SalesforceOAuthHandler(salesforce_config, transport_config, host=host, port=port)

    elif provider == "keycloak":

        keycloak_config = user_auth_config.get("keycloak")
        if not keycloak_config:
            raise ValueError("Keycloak provider selected but no Keycloak configuration found")
        return KeycloakOAuthHandler(keycloak_config, transport_config, host=host, port=port)

    else:
        raise ValueError(f"Unsupported auth provider: {provider}")


def create_url_builder(user_config: UserConfig) -> URLBuilder:
    """Create a URL builder from user configuration.

    Args:
        user_config: User configuration dictionary

    Returns:
        Configured URLBuilder instance
    """
    transport = user_config.get("transport", {})
    user_transport_config = transport.get("http", {}) if transport else {}
    transport_config = translate_transport_config(user_transport_config)
    return URLBuilder(transport_config)
