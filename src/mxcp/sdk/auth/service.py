"""AuthService - Single entry point for MXCP authentication.

This module provides the `AuthService` class which encapsulates all authentication
functionality including OAuth provider handling, session management, and middleware.

The service supports two deployment modes:
- **Issuer mode** (default): MXCP issues opaque tokens via internal session management.
- **Verifier mode**: External IdP issues tokens; MXCP validates and processes them.

Example usage:
    from mxcp.sdk.auth.service import AuthService
    from mxcp.sdk.auth.models import AuthConfigModel, GoogleAuthConfigModel

    # Create service from provider config
    auth_config = AuthConfigModel(provider="google", ...)
    provider_config = GoogleAuthConfigModel(client_id="...", ...)
    
    auth_service = AuthService.from_provider_config(
        auth_config=auth_config,
        provider_config=provider_config,
        host="localhost",
        port=8000,
    )
    
    # Register routes with FastMCP
    auth_service.register_routes(fastmcp_instance)
    
    # Get middleware for endpoint protection
    middleware = auth_service.build_middleware()
"""

import logging
import secrets
from typing import TYPE_CHECKING, Literal
from urllib.parse import urlencode

from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse, Response

from .adapter import ProviderAdapter
from .adapters.atlassian import AtlassianAdapter
from .adapters.github import GitHubAdapter
from .adapters.google import GoogleAdapter
from .adapters.keycloak import KeycloakAdapter
from .adapters.salesforce import SalesforceAdapter
from .fastmcp_provider import FastMCPAuthProvider
from .middleware import AuthenticationMiddleware
from .models import (
    AtlassianAuthConfigModel,
    AuthConfigModel,
    GitHubAuthConfigModel,
    GoogleAuthConfigModel,
    HttpTransportConfigModel,
    KeycloakAuthConfigModel,
    SalesforceAuthConfigModel,
)
from .sessions import SessionManager
from .storage import create_token_store
from .url_utils import URLBuilder

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

logger = logging.getLogger(__name__)

# Default callback path for unified callback handling
DEFAULT_CALLBACK_PATH = "/auth/callback"

# Type alias for provider configs
ProviderConfigType = (
    GoogleAuthConfigModel
    | KeycloakAuthConfigModel
    | GitHubAuthConfigModel
    | AtlassianAuthConfigModel
    | SalesforceAuthConfigModel
)


class AuthService:
    """Single entry point for MXCP authentication.

    AuthService encapsulates OAuth provider handling, token management, and
    middleware creation. It supports both issuer mode (MXCP issues tokens)
    and verifier mode (external IdP issues tokens).

    Attributes:
        auth_config: The authentication configuration.
        transport_config: HTTP transport configuration for URL building.
        provider_adapter: The provider adapter for IdP communication.
        session_manager: Session and token management.
        auth_enabled: Whether authentication is enabled.
        mode: The authentication mode ('issuer', 'verifier', or 'disabled').
    """

    def __init__(
        self,
        auth_config: AuthConfigModel,
        transport_config: HttpTransportConfigModel | None = None,
        provider_adapter: ProviderAdapter | None = None,
        session_manager: SessionManager | None = None,
        mode: Literal["issuer", "verifier", "disabled"] = "disabled",
        callback_path: str = DEFAULT_CALLBACK_PATH,
        host: str = "localhost",
        port: int = 8000,
    ):
        """Initialize AuthService.

        Use `from_provider_config()` factory method instead of calling this directly.

        Args:
            auth_config: Authentication configuration.
            transport_config: HTTP transport configuration.
            provider_adapter: Provider adapter for IdP communication.
            session_manager: SessionManager for session handling.
            mode: Authentication mode.
            callback_path: OAuth callback path.
            host: Server host for callback URLs.
            port: Server port for callback URLs.
        """
        self.auth_config = auth_config
        self.transport_config = transport_config
        self.provider_adapter = provider_adapter
        self.session_manager = session_manager
        self.mode = mode
        self.auth_enabled = mode != "disabled"
        self._callback_path = callback_path
        self._host = host
        self._port = port

        # URL builder for callback URLs
        self._url_builder = URLBuilder(transport_config)

        # FastMCP auth server provider (lazy initialized)
        self._fastmcp_provider: FastMCPAuthProvider | None = None

        # Track initialization state
        self._initialized = False

    @classmethod
    def from_config(
        cls,
        auth_config: AuthConfigModel,
        transport_config: HttpTransportConfigModel | None = None,
        host: str = "localhost",
        port: int = 8000,
    ) -> "AuthService":
        """Create AuthService from config (disabled mode only).

        This factory method creates a disabled AuthService when no provider
        configuration is provided. For enabled auth, use from_provider_config().

        Args:
            auth_config: SDK authentication configuration.
            transport_config: SDK HTTP transport configuration.
            host: Server host for callback URLs.
            port: Server port for callback URLs.

        Returns:
            Configured AuthService instance (disabled).
        """
        return cls(
            auth_config=auth_config,
            transport_config=transport_config,
            mode="disabled",
            host=host,
            port=port,
        )

    @classmethod
    def from_provider_config(
        cls,
        auth_config: AuthConfigModel,
        provider_config: ProviderConfigType,
        transport_config: HttpTransportConfigModel | None = None,
        host: str = "localhost",
        port: int = 8000,
        mode: Literal["issuer", "verifier"] | None = None,
        callback_path: str = DEFAULT_CALLBACK_PATH,
    ) -> "AuthService":
        """Create AuthService with provider configuration.

        This is the primary factory method for creating an AuthService instance.
        It creates the appropriate provider adapter and session manager.

        Args:
            auth_config: SDK authentication configuration.
            provider_config: Provider-specific configuration (Google, Keycloak, etc.).
            transport_config: SDK HTTP transport configuration.
            host: Server host for callback URLs.
            port: Server port for callback URLs.
            mode: Override authentication mode.
            callback_path: OAuth callback path.

        Returns:
            Configured AuthService instance.

        Raises:
            ValueError: If provider configuration is invalid.
        """
        provider = auth_config.provider

        if provider == "none" or provider is None:
            return cls(
                auth_config=auth_config,
                transport_config=transport_config,
                mode="disabled",
            )

        # Create provider adapter
        adapter = cls._create_adapter(provider_config, transport_config)

        # Determine effective mode
        effective_mode: Literal["issuer", "verifier", "disabled"] = mode or "issuer"

        # Create session manager with token store
        token_store = create_token_store(auth_config.persistence)
        session_manager = SessionManager(token_store=token_store)

        logger.info(
            f"Created AuthService with provider={provider}, mode={effective_mode}"
        )

        return cls(
            auth_config=auth_config,
            transport_config=transport_config,
            provider_adapter=adapter,
            session_manager=session_manager,
            mode=effective_mode,
            callback_path=callback_path,
            host=host,
            port=port,
        )

    @staticmethod
    def _create_adapter(
        provider_config: ProviderConfigType,
        transport_config: HttpTransportConfigModel | None,
    ) -> ProviderAdapter:
        """Create a provider adapter from configuration.

        Args:
            provider_config: Provider-specific configuration.
            transport_config: HTTP transport configuration.

        Returns:
            Configured provider adapter.

        Raises:
            ValueError: If provider config type is unsupported.
        """
        if isinstance(provider_config, GoogleAuthConfigModel):
            return GoogleAdapter(provider_config, transport_config)
        elif isinstance(provider_config, KeycloakAuthConfigModel):
            return KeycloakAdapter(provider_config, transport_config)
        elif isinstance(provider_config, GitHubAuthConfigModel):
            return GitHubAdapter(provider_config, transport_config)
        elif isinstance(provider_config, AtlassianAuthConfigModel):
            return AtlassianAdapter(provider_config, transport_config)
        elif isinstance(provider_config, SalesforceAuthConfigModel):
            return SalesforceAdapter(provider_config, transport_config)
        else:
            raise ValueError(f"Unsupported provider config type: {type(provider_config)}")

    async def initialize(self) -> None:
        """Initialize the auth service.

        This must be called before using the service. It initializes
        persistence backends and loads pre-configured clients.
        """
        if self._initialized:
            return

        if self.session_manager:
            await self.session_manager.initialize()
            logger.info(f"AuthService initialized (mode={self.mode})")
        else:
            logger.info("AuthService initialized (disabled)")

        self._initialized = True

    async def close(self) -> None:
        """Close the auth service and release resources."""
        if self.session_manager:
            await self.session_manager.close()

        logger.info("AuthService closed")

    def register_routes(self, mcp: "FastMCP") -> None:
        """Register OAuth routes with FastMCP.

        This registers the OAuth callback route and any well-known endpoints
        required for OAuth flows.

        Args:
            mcp: FastMCP instance to register routes with.
        """
        if not self.auth_enabled:
            logger.info("Authentication disabled, skipping route registration")
            return

        if not self.provider_adapter or not self.session_manager:
            logger.warning("No provider adapter or session manager configured")
            return

        callback_path = self._callback_path
        logger.info(f"Registering OAuth callback route: {callback_path}")

        @mcp.custom_route(callback_path, methods=["GET"])  # type: ignore[misc]
        async def oauth_callback(request: Request) -> Response:
            return await self._handle_callback(request)

        logger.info(f"Registered OAuth callback route: {callback_path}")

    async def _handle_callback(self, request: Request) -> Response:
        """Handle OAuth callback.

        This method:
        1. Parses the callback request
        2. Retrieves and validates OAuth state
        3. Exchanges the authorization code for tokens
        4. Creates a session with the tokens
        5. Issues an MXCP authorization code
        6. Redirects back to the client

        Args:
            request: The callback request from the IdP.

        Returns:
            Redirect response to the client's redirect_uri.
        """
        if not self.provider_adapter or not self.session_manager:
            return HTMLResponse(
                content="<h1>Error</h1><p>OAuth not properly configured</p>",
                status_code=500,
            )

        # Extract query parameters
        code = request.query_params.get("code")
        state = request.query_params.get("state")
        error = request.query_params.get("error")
        error_description = request.query_params.get("error_description")

        # Handle IdP errors
        if error:
            logger.error(f"OAuth error from IdP: {error} - {error_description}")
            return HTMLResponse(
                content=f"<h1>Authentication Failed</h1><p>{error_description or error}</p>",
                status_code=400,
            )

        if not code or not state:
            logger.error("Missing code or state in callback")
            return HTMLResponse(
                content="<h1>Authentication Failed</h1><p>Missing code or state parameter</p>",
                status_code=400,
            )

        # Retrieve and consume OAuth state (one-time use)
        oauth_state = self.session_manager.consume_oauth_state(state)
        if not oauth_state:
            logger.error(f"Invalid or expired state: {state[:8]}...")
            return HTMLResponse(
                content="<h1>Authentication Failed</h1><p>Invalid or expired state</p>",
                status_code=400,
            )

        try:
            # Exchange code for tokens using the adapter
            grant_result = await self.provider_adapter.exchange_code(
                code=code,
                redirect_uri=oauth_state.callback_url,
                code_verifier=oauth_state.code_verifier,
            )

            logger.info(f"Token exchange successful for client: {oauth_state.client_id}")

            # Create a session with the provider tokens
            session = await self.session_manager.create_session(
                client_id=oauth_state.client_id,
                provider_token=grant_result.access_token,
                provider_refresh_token=grant_result.refresh_token,
                scopes=grant_result.scope.split() if grant_result.scope else [],
                expires_in=grant_result.expires_in or self.session_manager.default_token_lifetime,
            )

            # Generate MXCP authorization code for the client
            mxcp_code = f"mcp_{secrets.token_hex(16)}"

            # Store auth code -> session mapping for token exchange
            self.session_manager.store_auth_code(mxcp_code, session.session_id)

            # Build redirect URL back to client
            redirect_params = {"code": mxcp_code, "state": state}
            redirect_url = f"{oauth_state.redirect_uri}?{urlencode(redirect_params)}"

            logger.info("OAuth callback complete, redirecting to client")
            return RedirectResponse(url=redirect_url)

        except Exception as e:
            logger.error(f"OAuth callback failed: {e}", exc_info=True)
            return HTMLResponse(
                content="<h1>Authentication Failed</h1><p>An error occurred during authentication</p>",
                status_code=500,
            )

    def get_callback_url(self, request: Request | None = None) -> str:
        """Get the full callback URL for OAuth flows.

        Args:
            request: Optional request for scheme detection.

        Returns:
            The full callback URL.
        """
        if request:
            return self._url_builder.build_callback_url(
                self._callback_path, request=request
            )
        return self._url_builder.build_callback_url(
            self._callback_path, host=self._host, port=self._port
        )

    async def build_authorize_url(
        self,
        client_id: str,
        redirect_uri: str,
        scopes: list[str] | None = None,
        code_challenge: str | None = None,
        code_challenge_method: str | None = None,
    ) -> str:
        """Build the authorization URL for starting an OAuth flow.

        This creates the OAuth state and returns the URL to redirect the user to.

        Args:
            client_id: The MCP client ID.
            redirect_uri: Where to redirect the user after auth completes.
            scopes: Scopes to request from the provider.
            code_challenge: PKCE code challenge (for public clients).
            code_challenge_method: PKCE method (e.g., 'S256').

        Returns:
            The authorization URL to redirect the user to.

        Raises:
            RuntimeError: If auth is not properly configured.
        """
        if not self.provider_adapter or not self.session_manager:
            raise RuntimeError("OAuth not properly configured")

        # Get our callback URL
        callback_url = self.get_callback_url()

        # Create OAuth state
        oauth_state = self.session_manager.create_oauth_state(
            client_id=client_id,
            redirect_uri=redirect_uri,
            callback_url=callback_url,
            code_challenge=code_challenge,
            provider=self.provider_adapter.provider_name,
            scopes=scopes,
        )

        # Build the authorization URL
        return await self.provider_adapter.build_authorize_url(
            redirect_uri=callback_url,
            state=oauth_state.state,
            scopes=scopes,
            code_challenge=code_challenge,
            code_challenge_method=code_challenge_method,
        )

    def build_middleware(self) -> AuthenticationMiddleware:
        """Build authentication middleware for endpoint protection.

        Returns:
            Configured AuthenticationMiddleware instance.
        """
        return AuthenticationMiddleware(
            session_manager=self.session_manager,
            provider_adapter=self.provider_adapter,
        )

    @property
    def callback_path(self) -> str | None:
        """Get the OAuth callback path.

        Returns:
            Callback path string, or None if auth is disabled.
        """
        if not self.auth_enabled:
            return None
        return self._callback_path

    @property
    def fastmcp_provider(self) -> FastMCPAuthProvider | None:
        """Get the FastMCP auth server provider.

        This provides the OAuthAuthorizationServerProvider interface
        required by FastMCP for OAuth endpoints.

        Returns:
            FastMCPAuthProvider instance, or None if auth is disabled.
        """
        if not self.auth_enabled:
            return None

        if self._fastmcp_provider is None and self.session_manager:
            self._fastmcp_provider = FastMCPAuthProvider(
                session_manager=self.session_manager,
                provider_adapter=self.provider_adapter,
            )

        return self._fastmcp_provider
