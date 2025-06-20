# -*- coding: utf-8 -*-
"""OAuth provider implementations for MXCP authentication."""
import asyncio
import logging
import secrets
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Optional, Dict
from pathlib import Path

from pydantic import AnyHttpUrl
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import Response

from mcp.server.auth.provider import (
    AccessToken,
    AuthorizationCode,
    AuthorizationParams,
    OAuthAuthorizationServerProvider,
    OAuthToken,
    construct_redirect_uri,
)
from mcp.shared.auth import OAuthClientInformationFull, OAuthClientMetadata
from mxcp.config.types import UserAuthConfig
from mxcp.auth.persistence import (
    AuthPersistenceBackend,
    create_persistence_backend,
    PersistedAccessToken,
    PersistedAuthCode,
    PersistedClient,
)

logger = logging.getLogger(__name__)

# ────────────────────────────────────────────────────────────────────────────
# OAuth Client implementation
# ────────────────────────────────────────────────────────────────────────────

# We'll use the standard MCP OAuthClientInformationFull instead of a custom class


# ────────────────────────────────────────────────────────────────────────────
# Generic data containers
# ────────────────────────────────────────────────────────────────────────────

@dataclass
class ExternalUserInfo:
    """Result of exchanging an auth‑code with an external IdP."""

    id: str
    scopes: list[str]
    raw_token: str  # original token from the IdP (JWT or opaque)
    provider: str


@dataclass
class UserContext:
    """Standardized user context that all OAuth providers must return.
    
    This represents the common denominator of user information across all providers.
    Some fields may be None if the provider doesn't support them.
    """
    
    provider: str  # Provider name (e.g., 'github', 'google', 'microsoft')
    user_id: str   # Unique user identifier from the provider
    username: str  # Display username/handle
    email: Optional[str] = None      # User's email address
    name: Optional[str] = None       # User's display name
    avatar_url: Optional[str] = None # User's profile picture URL
    raw_profile: Optional[Dict[str, Any]] = None  # Raw profile data for debugging
    external_token: Optional[str] = None  # Original OAuth provider token


@dataclass
class StateMeta:
    redirect_uri: str
    code_challenge: Optional[str]
    redirect_uri_provided_explicitly: bool
    client_id: str


# ────────────────────────────────────────────────────────────────────────────
# Provider interface
# ────────────────────────────────────────────────────────────────────────────

class ExternalOAuthHandler(ABC):
    """Implement one concrete subclass per OAuth / OpenID provider."""

    # ----- authorization step -----
    @abstractmethod
    def get_authorize_url(self, client_id: str, params: AuthorizationParams) -> str:
        """Return the complete authorize URL with a freshly‑minted *state*."""

    # ----- code exchange step -----
    @abstractmethod
    async def exchange_code(self, code: str, state: str) -> ExternalUserInfo:
        """Turn `code` + `state` into `ExternalUserInfo` or raise `HTTPException`."""

    # ----- state retrieval -----
    @abstractmethod
    def get_state_metadata(self, state: str) -> StateMeta:
        """Return metadata stored during `get_authorize_url`."""

    # ----- callback wiring -----
    @property
    @abstractmethod
    def callback_path(self) -> str:
        """HTTP path that FastMCP must register (e.g. "/github/callback")."""

    @abstractmethod
    async def on_callback(self, request: Request, provider: "GeneralOAuthAuthorizationServer") -> Response:  # noqa: E501
        """ASGI handler body for the callback route."""

    # ----- user context -----
    @abstractmethod
    async def get_user_context(self, token: str) -> UserContext:
        """Get standardized user context from the OAuth provider.
        
        Args:
            token: OAuth access token for the user
            
        Returns:
            UserContext with standardized user information
            
        Raises:
            HTTPException: If token is invalid or user info cannot be retrieved
        """


# ────────────────────────────────────────────────────────────────────────────
# Provider‑agnostic authorization server (opaque token flavour)
# ────────────────────────────────────────────────────────────────────────────

class GeneralOAuthAuthorizationServer(OAuthAuthorizationServerProvider):
    """OAuth authorization server that bridges external OAuth providers with MCP."""

    def __init__(self, handler: ExternalOAuthHandler, auth_config: Optional[UserAuthConfig] = None, user_config: Optional[Dict[str, Any]] = None):
        self.handler = handler
        self.auth_config = auth_config
        self.user_config = user_config
        
        # Initialize persistence backend
        persistence_config = auth_config.get("persistence") if auth_config else None
        self.persistence = create_persistence_backend(persistence_config)
        
        # In-memory caches for performance (fallback when persistence is disabled)
        self._clients: dict[str, OAuthClientInformationFull] = {}
        self._tokens: dict[str, AccessToken] = {}
        self._auth_codes: dict[str, AuthorizationCode] = {}
        self._token_mapping: dict[str, str] = {}  # MCP token -> external token
        self._lock = asyncio.Lock()
        
        # Flag to track if persistence is initialized
        self._persistence_initialized = False

    async def initialize(self):
        """Initialize the OAuth server and persistence backend."""
        if self._persistence_initialized:
            return
            
        if self.persistence:
            await self.persistence.initialize()
            logger.info("OAuth persistence backend initialized")
            
            # Load existing clients from persistence
            await self._load_clients_from_persistence()
        else:
            logger.info("OAuth persistence disabled, using in-memory storage only")
        
        # Register pre-configured clients from user config
        if self.auth_config:
            await self._register_configured_clients(self.auth_config)
            
        self._persistence_initialized = True

    async def close(self):
        """Close the OAuth server and persistence backend."""
        if self.persistence:
            await self.persistence.close()
            logger.info("OAuth persistence backend closed")

    async def _load_clients_from_persistence(self):
        """Load existing clients from persistence into memory cache."""
        if not self.persistence:
            return
            
        try:
            persisted_clients = await self.persistence.list_clients()
            for client_data in persisted_clients:
                try:
                    # Convert string URLs back to AnyHttpUrl objects for OAuthClientInformationFull
                    from pydantic import AnyHttpUrl, ValidationError
                    redirect_uris_pydantic = []
                    
                    # Validate each redirect URI individually
                    for uri in client_data.redirect_uris:
                        try:
                            redirect_uris_pydantic.append(AnyHttpUrl(uri))
                        except ValidationError as ve:
                            logger.warning(f"Skipping malformed redirect URI for client {client_data.client_id}: {uri} - {ve}")
                            # Skip malformed URIs but continue loading the client
                    
                    # Skip client if no valid redirect URIs remain
                    if not redirect_uris_pydantic and client_data.redirect_uris:
                        logger.error(f"Skipping client {client_data.client_id}: no valid redirect URIs")
                        continue
                    
                    client = OAuthClientInformationFull(
                        client_id=client_data.client_id,
                        client_secret=client_data.client_secret,
                        redirect_uris=redirect_uris_pydantic,  # Use validated URIs
                        grant_types=client_data.grant_types,
                        response_types=client_data.response_types,
                        scope=client_data.scope,
                        client_name=client_data.client_name
                    )
                    self._clients[client_data.client_id] = client
                    logger.info(f"Loaded persisted OAuth client: {client_data.client_id} ({client_data.client_name})")
                except Exception as e:
                    logger.error(f"Failed to load client {client_data.client_id}: {e}")
                    # Continue with next client instead of failing entirely
        except Exception as e:
            logger.error(f"Failed to load clients from persistence: {e}")

    async def _register_configured_clients(self, auth_config: UserAuthConfig):
        """Register pre-configured OAuth clients from user config."""
        clients = auth_config.get("clients", [])
        
        for client_config in clients:
            client_id = client_config["client_id"]
            client = OAuthClientInformationFull(
                client_id=client_id,
                client_secret=client_config.get("client_secret"),  # None for public clients
                redirect_uris=client_config.get("redirect_uris", []),
                grant_types=client_config.get("grant_types", ["authorization_code"]),
                response_types=client_config.get("response_types", ["code"]),
                scope=" ".join(client_config.get("scopes", [])),  # No default scopes
                client_name=client_config["name"]
            )
            
            # Store in memory cache
            self._clients[client_id] = client
            logger.info(f"Pre-registered OAuth client: {client_id} ({client_config['name']})")
            
            # Store in persistence if available (these are not persisted as they come from config)
            # Pre-configured clients should be loaded from config each time, not persisted

    # ----- client registry -----
    async def get_client(self, client_id: str) -> Optional[OAuthClientInformationFull]:
        async with self._lock:
            # First check memory cache
            client = self._clients.get(client_id)
            if client:
                logger.info(f"Looking up client_id: {client_id}, found in memory cache")
                return client
            
            # If not in cache and persistence is available, check persistence
            if self.persistence:
                try:
                    persisted_client = await self.persistence.load_client(client_id)
                    if persisted_client:
                        # Load into memory cache
                        # Convert string URLs back to AnyHttpUrl objects for OAuthClientInformationFull
                        from pydantic import AnyHttpUrl, ValidationError
                        redirect_uris_pydantic = []
                        
                        # Validate each redirect URI individually
                        for uri in persisted_client.redirect_uris:
                            try:
                                redirect_uris_pydantic.append(AnyHttpUrl(uri))
                            except ValidationError as ve:
                                logger.warning(f"Skipping malformed redirect URI for client {client_id}: {uri} - {ve}")
                                # Skip malformed URIs but continue loading the client
                        
                        # Return None if no valid redirect URIs remain
                        if not redirect_uris_pydantic and persisted_client.redirect_uris:
                            logger.error(f"Cannot load client {client_id}: no valid redirect URIs")
                            return None
                        
                        client = OAuthClientInformationFull(
                            client_id=persisted_client.client_id,
                            client_secret=persisted_client.client_secret,
                            redirect_uris=redirect_uris_pydantic,  # Use validated URIs
                            grant_types=persisted_client.grant_types,
                            response_types=persisted_client.response_types,
                            scope=persisted_client.scope,
                            client_name=persisted_client.client_name
                        )
                        self._clients[client_id] = client
                        logger.info(f"Looking up client_id: {client_id}, found in persistence")
                        return client
                except Exception as e:
                    logger.error(f"Error loading client from persistence: {e}")
            
            logger.warning(f"OAuth client not found: {client_id}")
            return None

    async def register_client(self, client_info: OAuthClientInformationFull):
        async with self._lock:
            logger.info(f"Registering client: {client_info.client_id}")
            
            # Store in memory cache
            self._clients[client_info.client_id] = client_info
            
            # Store in persistence if available
            if self.persistence:
                try:
                    # Convert Pydantic AnyHttpUrl objects to strings for JSON serialization
                    redirect_uris_str = [str(uri) for uri in client_info.redirect_uris]
                    
                    persisted_client = PersistedClient(
                        client_id=client_info.client_id,
                        client_secret=client_info.client_secret,
                        redirect_uris=redirect_uris_str,  # Convert AnyHttpUrl to strings
                        grant_types=client_info.grant_types,
                        response_types=client_info.response_types,
                        scope=client_info.scope,
                        client_name=client_info.client_name,
                        created_at=time.time()
                    )
                    await self.persistence.store_client(persisted_client)
                    logger.info(f"Persisted client: {client_info.client_id}")
                except Exception as e:
                    logger.error(f"Error persisting client: {e}")

    async def register_client_dynamically(self, client_metadata: Dict[str, Any]) -> Dict[str, Any]:
        """Handle Dynamic Client Registration requests.
        
        This implements RFC 7591 - OAuth 2.0 Dynamic Client Registration Protocol
        """
        import secrets
        import time
        
        try:
            # Generate client credentials
            client_id = secrets.token_urlsafe(32)
            client_secret = secrets.token_urlsafe(64)
            
            # Extract and validate metadata
            redirect_uris = client_metadata.get('redirect_uris', [])
            grant_types = client_metadata.get('grant_types', ['authorization_code'])
            response_types = client_metadata.get('response_types', ['code'])
            scope = client_metadata.get('scope', 'mxcp:access')
            client_name = client_metadata.get('client_name', 'MCP Client')
            
            # Create client object
            client_info = OAuthClientInformationFull(
                client_id=client_id,
                client_secret=client_secret,
                redirect_uris=redirect_uris,
                grant_types=grant_types,
                response_types=response_types,
                scope=scope,
                client_name=client_name
            )
            
            # Register the client
            await self.register_client(client_info)
            logger.info(f"Dynamically registered OAuth client: {client_id} ({client_name})")
            
            # Return registration response
            response = {
                'client_id': client_id,
                'client_secret': client_secret,
                'client_id_issued_at': int(time.time()),
                'client_secret_expires_at': 0,  # Never expires
                'redirect_uris': client_info.redirect_uris,
                'grant_types': client_info.grant_types,
                'response_types': client_info.response_types,
                'scope': client_info.scope,
                'client_name': client_info.client_name
            }
            return response
            
        except Exception as e:
            logger.error(f"Dynamic client registration failed: {e}")
            raise

    # ----- authorize URL -----
    async def authorize(self, client: OAuthClientInformationFull, params: AuthorizationParams) -> str:
        logger.info(f"OAuth authorize request - client_id: {client.client_id if client else 'None'}, params: {params}")
        if not client:
            logger.error("No client provided to authorize method")
            raise HTTPException(400, "Client not found")
        return self.handler.get_authorize_url(client.client_id, params)

    # ----- helper: store token -----
    async def _store_token(self, token: str, client_id: str, scopes: list[str], expires_in: Optional[int], external_token: Optional[str] = None):
        expires_at = (time.time() + expires_in) if expires_in else None
        access_token = AccessToken(
            token=token,
            client_id=client_id,
            scopes=scopes,
            expires_at=int(expires_at) if expires_at else None,
        )
        
        # Store in memory cache
        self._tokens[token] = access_token
        
        # Store external token mapping if provided
        if external_token:
            self._token_mapping[token] = external_token
        
        # Store in persistence if available
        if self.persistence:
            try:
                persisted_token = PersistedAccessToken(
                    token=token,
                    client_id=client_id,
                    external_token=external_token,
                    scopes=scopes,
                    expires_at=expires_at,
                    created_at=time.time()
                )
                await self.persistence.store_token(persisted_token)
                logger.debug(f"Persisted access token: {token[:10]}...")
            except Exception as e:
                logger.error(f"Error persisting access token: {e}")

    # ----- IdP callback → auth code -----
    async def handle_callback(self, code: str, state: str) -> str:
        user_info = await self.handler.exchange_code(code, state)
        meta = self.handler.get_state_metadata(state)
        
        # Clean up the handler's state now that we have the metadata
        if hasattr(self.handler, 'cleanup_state'):
            self.handler.cleanup_state(state)
        
        mcp_code = f"mcp_{secrets.token_hex(16)}"
        
        logger.info(f"Creating authorization code for client: {meta.client_id}")
        
        # Validate redirect URI
        try:
            from pydantic import ValidationError
            redirect_uri = AnyHttpUrl(meta.redirect_uri)
        except ValidationError as ve:
            logger.error(f"Invalid redirect URI in callback: {meta.redirect_uri} - {ve}")
            raise HTTPException(400, f"Invalid redirect URI: {meta.redirect_uri}")
        
        auth_code = AuthorizationCode(
            code=mcp_code,
            client_id=meta.client_id,  # Use the original MCP client ID, not user_info.id
            redirect_uri=redirect_uri,
            redirect_uri_provided_explicitly=meta.redirect_uri_provided_explicitly,
            expires_at=time.time() + 300,
            scopes=user_info.scopes,
            code_challenge=meta.code_challenge,
        )
        async with self._lock:
            # Store authorization code in memory cache
            self._auth_codes[mcp_code] = auth_code
            
            # Store authorization code in persistence if available
            if self.persistence:
                try:
                    persisted_auth_code = PersistedAuthCode(
                        code=mcp_code,
                        client_id=auth_code.client_id,
                        redirect_uri=str(auth_code.redirect_uri),
                        redirect_uri_provided_explicitly=auth_code.redirect_uri_provided_explicitly,
                        expires_at=auth_code.expires_at,
                        scopes=auth_code.scopes,
                        code_challenge=auth_code.code_challenge,
                        created_at=time.time()
                    )
                    await self.persistence.store_auth_code(persisted_auth_code)
                    logger.debug(f"Persisted auth code: {mcp_code}")
                except Exception as e:
                    logger.error(f"Error persisting auth code: {e}")
            
            # Store external token (temporary until exchanged for MCP token)
            await self._store_token(user_info.raw_token, user_info.id, user_info.scopes, None, user_info.raw_token)
            self._token_mapping[mcp_code] = user_info.raw_token
        
        logger.info(f"Created auth code: {mcp_code} for client: {meta.client_id}")
        return construct_redirect_uri(meta.redirect_uri, code=mcp_code, state=state)

    # ----- auth code → MCP token -----
    async def load_authorization_code(self, client: OAuthClientInformationFull, code: str) -> Optional[AuthorizationCode]:
        async with self._lock:
            # First check memory cache
            auth_code = self._auth_codes.get(code)
            
            # If not in cache and persistence is available, check persistence
            if not auth_code and self.persistence:
                try:
                    persisted_code = await self.persistence.load_auth_code(code)
                    if persisted_code:
                        # Check if code is expired
                        if persisted_code.expires_at < time.time():
                            # Clean up expired code
                            await self.persistence.delete_auth_code(code)
                            logger.warning(f"Auth code {code} has expired (from persistence)")
                            return None
                        
                        # Load into memory cache
                        try:
                            from pydantic import ValidationError
                            redirect_uri = AnyHttpUrl(persisted_code.redirect_uri)
                        except ValidationError as ve:
                            logger.error(f"Malformed redirect URI in auth code {code}: {persisted_code.redirect_uri} - {ve}")
                            # Delete the malformed auth code
                            await self.persistence.delete_auth_code(code)
                            return None
                        
                        auth_code = AuthorizationCode(
                            code=persisted_code.code,
                            client_id=persisted_code.client_id,
                            redirect_uri=redirect_uri,
                            redirect_uri_provided_explicitly=persisted_code.redirect_uri_provided_explicitly,
                            expires_at=persisted_code.expires_at,
                            scopes=persisted_code.scopes,
                            code_challenge=persisted_code.code_challenge,
                        )
                        self._auth_codes[code] = auth_code
                        logger.info(f"Loaded auth code from persistence: {code}")
                except Exception as e:
                    logger.error(f"Error loading auth code from persistence: {e}")
            
            if auth_code:
                # Check expiration
                if auth_code.expires_at < time.time():
                    logger.warning(f"Authorization code expired: {code}")
                    # Clean up expired code
                    self._auth_codes.pop(code, None)
                    if self.persistence:
                        try:
                            await self.persistence.delete_auth_code(code)
                        except Exception as e:
                            logger.error(f"Error deleting expired auth code from persistence: {e}")
                    return None
            else:
                logger.warning(f"Authorization code not found: {code}")
                
            return auth_code

    async def exchange_authorization_code(self, client: OAuthClientInformationFull, code_obj: AuthorizationCode) -> OAuthToken:
        try:
            logger.info(f"Token exchange - client_id: {client.client_id if client else 'None'}, code_obj.client_id: {code_obj.client_id}, code: {code_obj.code}")
            
            # Validate client and code match
            if not client:
                logger.error("No client provided to exchange_authorization_code")
                raise HTTPException(400, "Invalid client")
                
            if client.client_id != code_obj.client_id:
                logger.error(f"Client ID mismatch - client: {client.client_id}, code: {code_obj.client_id}")
                raise HTTPException(400, "Client ID mismatch")
            
            mcp_token = f"mcp_{secrets.token_hex(32)}"
            async with self._lock:
                # Get external token from mapping
                external = self._token_mapping.pop(code_obj.code, None)
                
                # Store MCP token with external token mapping
                await self._store_token(mcp_token, client.client_id, code_obj.scopes, 3600, external)
                
                if not external:
                    logger.warning(f"No external token found for authorization code: {code_obj.code}")
                
                # Clean up authorization code
                self._auth_codes.pop(code_obj.code, None)
                if self.persistence:
                    try:
                        await self.persistence.delete_auth_code(code_obj.code)
                        logger.debug(f"Deleted auth code from persistence: {code_obj.code}")
                    except Exception as e:
                        logger.error(f"Error deleting auth code from persistence: {e}")
            
            logger.info(f"Token exchange successful for client: {client.client_id}")
            
            # Return a proper OAuthToken object
            return OAuthToken(
                access_token=mcp_token,
                token_type="bearer",
                expires_in=3600,
                scope=" ".join(code_obj.scopes),
            )
        except Exception as e:
            logger.error(f"Error in exchange_authorization_code: {e}", exc_info=True)
            raise

    # ----- token validation / revocation -----
    async def load_access_token(self, token: str) -> Optional[AccessToken]:
        async with self._lock:
            # First check memory cache
            tkn = self._tokens.get(token)
            
            # If not in cache and persistence is available, check persistence
            if not tkn and self.persistence:
                try:
                    persisted_token = await self.persistence.load_token(token)
                    if persisted_token:
                        # Check if token is expired
                        if persisted_token.expires_at and persisted_token.expires_at < time.time():
                            # Clean up expired token
                            await self.persistence.delete_token(token)
                            return None
                        
                        # Load into memory cache
                        tkn = AccessToken(
                            token=persisted_token.token,
                            client_id=persisted_token.client_id,
                            scopes=persisted_token.scopes,
                            expires_at=int(persisted_token.expires_at) if persisted_token.expires_at else None,
                        )
                        self._tokens[token] = tkn
                        
                        # Load external token mapping if available
                        if persisted_token.external_token:
                            self._token_mapping[token] = persisted_token.external_token
                        
                        logger.debug(f"Loaded token from persistence: {token[:10]}...")
                except Exception as e:
                    logger.error(f"Error loading token from persistence: {e}")
            
            # Check expiration
            if tkn and tkn.expires_at and tkn.expires_at < time.time():
                # Clean up expired token
                self._tokens.pop(token, None)
                self._token_mapping.pop(token, None)
                if self.persistence:
                    try:
                        await self.persistence.delete_token(token)
                    except Exception as e:
                        logger.error(f"Error deleting expired token from persistence: {e}")
                return None
                
            return tkn

    async def load_refresh_token(self, client, refresh_token):
        return None

    async def exchange_refresh_token(self, client, refresh_token, scopes):
        raise NotImplementedError

    async def revoke_token(self, token: str, token_type_hint: str | None = None):
        async with self._lock:
            # Remove from memory cache
            self._tokens.pop(token, None)
            self._token_mapping.pop(token, None)
            
            # Remove from persistence if available
            if self.persistence:
                try:
                    await self.persistence.delete_token(token)
                    logger.debug(f"Revoked token from persistence: {token[:10]}...")
                except Exception as e:
                    logger.error(f"Error revoking token from persistence: {e}")


def create_oauth_handler(auth_config: UserAuthConfig, host: str = "localhost", port: int = 8000, user_config: Optional[Dict[str, Any]] = None) -> Optional[ExternalOAuthHandler]:
    """Create an OAuth handler based on the auth configuration.
    
    Args:
        auth_config: The auth configuration from user config
        host: The server host to use for callback URLs
        port: The server port to use for callback URLs
        user_config: Full user configuration for transport settings
        
    Returns:
        OAuth handler instance or None if provider is 'none'
    """
    provider = auth_config.get("provider", "none")
    
    if provider == "none":
        return None
    elif provider == "github":
        from .github import GitHubOAuthHandler
        # Pass transport config to GitHub handler
        enhanced_auth_config = dict(auth_config)
        if user_config and "transport" in user_config:
            enhanced_auth_config["transport"] = user_config["transport"]
        return GitHubOAuthHandler(enhanced_auth_config, host=host, port=port)
    elif provider == "atlassian":
        from .atlassian import AtlassianOAuthHandler
        # Pass transport config to Atlassian handler
        enhanced_auth_config = dict(auth_config)
        if user_config and "transport" in user_config:
            enhanced_auth_config["transport"] = user_config["transport"]
        return AtlassianOAuthHandler(enhanced_auth_config, host=host, port=port)
    elif provider == "salesforce":
        from .salesforce import SalesforceOAuthHandler
        # Pass transport config to Salesforce handler
        enhanced_auth_config = dict(auth_config)
        if user_config and "transport" in user_config:
            enhanced_auth_config["transport"] = user_config["transport"]
        return SalesforceOAuthHandler(enhanced_auth_config, host=host, port=port)
    else:
        raise ValueError(f"Unsupported auth provider: {provider}") 