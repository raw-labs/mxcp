# -*- coding: utf-8 -*-
"""OAuth provider implementations for MXCP authentication."""
import asyncio
import logging
import secrets
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Optional, Dict

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

    def __init__(self, handler: ExternalOAuthHandler, auth_config: Optional[UserAuthConfig] = None):
        self.handler = handler
        self._clients: dict[str, OAuthClientInformationFull] = {}
        self._tokens: dict[str, AccessToken] = {}
        self._auth_codes: dict[str, AuthorizationCode] = {}
        self._token_mapping: dict[str, str] = {}  # MCP token -> external token
        self._lock = asyncio.Lock()

        # Register pre-configured clients from user config
        if auth_config:
            self._register_configured_clients(auth_config)

    def _register_configured_clients(self, auth_config: UserAuthConfig):
        """Register pre-configured OAuth clients from user config."""
        clients = auth_config.get("clients", [])
        
        for client_config in clients:
            client_id = client_config["client_id"]
            client = OAuthClientInformationFull(
                client_id=client_id,
                client_secret=client_config.get("client_secret"),  # None for public clients
                redirect_uris=client_config.get("redirect_uris", [
                    "http://127.0.0.1:49153/oauth/callback",
                    "https://127.0.0.1:49153/oauth/callback",
                    "http://localhost:49153/oauth/callback", 
                    "https://localhost:49153/oauth/callback"
                ]),
                grant_types=client_config.get("grant_types", ["authorization_code"]),
                response_types=client_config.get("response_types", ["code"]),
                scope=" ".join(client_config.get("scopes", [])),  # No default scopes
                client_name=client_config["name"]
            )
            
            self._clients[client_id] = client
            logger.info(f"Pre-registered OAuth client: {client_id} ({client_config['name']})")

    # ----- client registry -----
    async def get_client(self, client_id: str) -> Optional[OAuthClientInformationFull]:
        async with self._lock:
            client = self._clients.get(client_id)
            logger.info(f"Looking up client_id: {client_id}, found: {client is not None}")
            if not client:
                logger.info(f"Available clients: {list(self._clients.keys())}")
            return client

    async def register_client(self, client_info: OAuthClientInformationFull):
        async with self._lock:
            logger.info(f"Registering client: {client_info.client_id}")
            self._clients[client_info.client_id] = client_info

    async def register_client_dynamically(self, client_metadata: Dict[str, Any]) -> Dict[str, Any]:
        """Handle Dynamic Client Registration requests.
        
        This implements RFC 7591 - OAuth 2.0 Dynamic Client Registration Protocol
        """
        import secrets
        import time
        
        logger.info(f"=== register_client_dynamically called ===")
        logger.info(f"Input client_metadata: {client_metadata}")
        logger.info(f"Input type: {type(client_metadata)}")
        
        try:
            # Generate client credentials
            client_id = secrets.token_urlsafe(32)
            client_secret = secrets.token_urlsafe(64)
            logger.info(f"Generated client_id: {client_id}")
            
            # Extract and validate metadata
            redirect_uris = client_metadata.get('redirect_uris', [])
            grant_types = client_metadata.get('grant_types', ['authorization_code'])
            response_types = client_metadata.get('response_types', ['code'])
            scope = client_metadata.get('scope', 'mxcp:access')
            client_name = client_metadata.get('client_name', 'MCP Client')
            
            logger.info(f"Extracted values:")
            logger.info(f"  redirect_uris: {redirect_uris} (type: {type(redirect_uris)})")
            logger.info(f"  grant_types: {grant_types} (type: {type(grant_types)})")
            logger.info(f"  response_types: {response_types} (type: {type(response_types)})")
            logger.info(f"  scope: {scope} (type: {type(scope)})")
            logger.info(f"  client_name: {client_name} (type: {type(client_name)})")
            
            # Create a proper client object
            logger.info("Creating OAuthClientInformationFull object...")
            client_info = OAuthClientInformationFull(
                client_id=client_id,
                client_secret=client_secret,
                redirect_uris=redirect_uris,
                grant_types=grant_types,
                response_types=response_types,
                scope=scope,
                client_name=client_name
            )
            logger.info(f"Created client_info: {client_info}")
            
            # Register the client
            logger.info("Registering client...")
            await self.register_client(client_info)
            
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
            logger.info(f"Returning response: {response}")
            return response
            
        except Exception as e:
            logger.error(f"Exception in register_client_dynamically: {e}")
            logger.error(f"Exception type: {type(e)}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            raise

    # ----- authorize URL -----
    async def authorize(self, client: OAuthClientInformationFull, params: AuthorizationParams) -> str:
        logger.info(f"OAuth authorize request - client_id: {client.client_id if client else 'None'}, params: {params}")
        if not client:
            logger.error("No client provided to authorize method")
            raise HTTPException(400, "Client not found")
        return self.handler.get_authorize_url(client.client_id, params)

    # ----- helper: store token -----
    async def _store_token(self, token: str, client_id: str, scopes: list[str], expires_in: Optional[int]):
        self._tokens[token] = AccessToken(
            token=token,
            client_id=client_id,
            scopes=scopes,
            expires_at=(int(time.time()) + expires_in) if expires_in else None,
        )

    # ----- IdP callback → auth code -----
    async def handle_callback(self, code: str, state: str) -> str:
        user_info = await self.handler.exchange_code(code, state)
        meta = self.handler.get_state_metadata(state)
        
        # Clean up the handler's state now that we have the metadata
        if hasattr(self.handler, 'cleanup_state'):
            self.handler.cleanup_state(state)
        
        mcp_code = f"mcp_{secrets.token_hex(16)}"
        
        # Debug logging for PKCE
        logger.info(f"Creating auth code with PKCE - code_challenge: {meta.code_challenge}")
        logger.info(f"External token from provider: {user_info.raw_token[:10]}... for user: {user_info.id}")
        
        auth_code = AuthorizationCode(
            code=mcp_code,
            client_id=meta.client_id,  # Use the original MCP client ID, not user_info.id
            redirect_uri=AnyHttpUrl(meta.redirect_uri),
            redirect_uri_provided_explicitly=meta.redirect_uri_provided_explicitly,
            expires_at=time.time() + 300,
            scopes=user_info.scopes,
            code_challenge=meta.code_challenge,
        )
        async with self._lock:
            self._auth_codes[mcp_code] = auth_code
            await self._store_token(user_info.raw_token, user_info.id, user_info.scopes, None)
            self._token_mapping[mcp_code] = user_info.raw_token
            logger.info(f"Stored external token mapping: {mcp_code} -> {user_info.raw_token[:10]}...")
        
        logger.info(f"Created auth code: {mcp_code} for client: {meta.client_id}")
        return construct_redirect_uri(meta.redirect_uri, code=mcp_code, state=state)

    # ----- auth code → MCP token -----
    async def load_authorization_code(self, client: OAuthClientInformationFull, code: str) -> Optional[AuthorizationCode]:
        async with self._lock:
            auth_code = self._auth_codes.get(code)
            logger.info(f"Loading auth code: {code}, found: {auth_code is not None}")
            if auth_code:
                logger.info(f"Auth code details - client_id: {auth_code.client_id}, expires_at: {auth_code.expires_at}, current_time: {time.time()}")
                logger.info(f"Auth code PKCE details - code_challenge: {auth_code.code_challenge}")
                if auth_code.expires_at < time.time():
                    logger.warning(f"Auth code {code} has expired")
                    self._auth_codes.pop(code, None)
                    return None
            else:
                logger.warning(f"Available auth codes: {list(self._auth_codes.keys())}")
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
                await self._store_token(mcp_token, client.client_id, code_obj.scopes, 3600)
                external = self._token_mapping.pop(code_obj.code, None)
                logger.info(f"External token mapping lookup - code: {code_obj.code}, found: {external[:10] if external else 'None'}...")
                if external:
                    self._token_mapping[mcp_token] = external
                    logger.info(f"Mapped MCP token {mcp_token[:10]}... to external token {external[:10]}...")
                else:
                    logger.warning(f"No external token found for auth code {code_obj.code}")
                    logger.warning(f"Available token mappings: {list(self._token_mapping.keys())}")
                self._auth_codes.pop(code_obj.code, None)
            
            logger.info(f"Token exchange successful - mcp_token: {mcp_token[:10]}..., scopes: {code_obj.scopes}")
            
            # Return a proper OAuthToken object
            result = OAuthToken(
                access_token=mcp_token,
                token_type="bearer",
                expires_in=3600,
                scope=" ".join(code_obj.scopes),
            )
            logger.info(f"Returning token response: {result}")
            return result
        except Exception as e:
            logger.error(f"Error in exchange_authorization_code: {e}", exc_info=True)
            raise

    # ----- token validation / revocation -----
    async def load_access_token(self, token: str) -> Optional[AccessToken]:
        async with self._lock:
            tkn = self._tokens.get(token)
            if not tkn:
                return None
            if tkn.expires_at and tkn.expires_at < time.time():
                self._tokens.pop(token, None)
                self._token_mapping.pop(token, None)
                return None
            return tkn

    async def load_refresh_token(self, client, refresh_token):
        return None

    async def exchange_refresh_token(self, client, refresh_token, scopes):
        raise NotImplementedError

    async def revoke_token(self, token: str, token_type_hint: str | None = None):
        async with self._lock:
            self._tokens.pop(token, None)
            self._token_mapping.pop(token, None)


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
    else:
        raise ValueError(f"Unsupported auth provider: {provider}") 