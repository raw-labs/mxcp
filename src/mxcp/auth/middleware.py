# -*- coding: utf-8 -*-
"""Authentication middleware for MXCP endpoints."""
import logging
from typing import Any, Dict, Optional, Callable
from functools import wraps

from mcp.server.auth.middleware.auth_context import get_access_token
from mxcp.auth.providers import ExternalOAuthHandler, GeneralOAuthAuthorizationServer, UserContext

logger = logging.getLogger(__name__)


class AuthenticationMiddleware:
    """Middleware to handle authentication for MXCP endpoints."""
    
    def __init__(self, oauth_handler: Optional[ExternalOAuthHandler], oauth_server: Optional[GeneralOAuthAuthorizationServer]):
        """Initialize authentication middleware.
        
        Args:
            oauth_handler: OAuth handler instance (None if auth is disabled)
            oauth_server: OAuth authorization server instance (None if auth is disabled)
        """
        self.oauth_handler = oauth_handler
        self.oauth_server = oauth_server
        self.auth_enabled = oauth_handler is not None and oauth_server is not None

    async def check_authentication(self) -> Optional[UserContext]:
        """Check if the current request is authenticated.
        
        Returns:
            UserContext if authenticated, None if not authenticated or auth is disabled
        """
        if not self.auth_enabled:
            logger.debug("Authentication is disabled")
            return None
            
        try:
            # Get the access token from the current request context
            access_token = get_access_token()
            if not access_token:
                logger.warning("No access token found in request context")
                return None
                
            # Validate the token with the OAuth server
            token_info = await self.oauth_server.load_access_token(access_token.token)
            if not token_info:
                logger.warning("Invalid or expired access token")
                return None
                
            # Get the external token to fetch user context
            external_token = self.oauth_server._token_mapping.get(access_token.token)
            if not external_token:
                logger.warning("No external token mapping found")
                return None
                
            # Get standardized user context from the provider
            try:
                user_context = await self.oauth_handler.get_user_context(external_token)
                return user_context
            except Exception as e:
                logger.error(f"Failed to get user context: {e}")
                return None
                
        except Exception as e:
            logger.error(f"Authentication check failed: {e}")
            return None

    def require_auth(self, func: Callable) -> Callable:
        """Decorator to require authentication for a function.
        
        Args:
            func: Function to protect with authentication
            
        Returns:
            Wrapped function that checks authentication
        """
        @wraps(func)
        async def wrapper(*args, **kwargs):
            if self.auth_enabled:
                user_context = await self.check_authentication()
                if user_context:
                    # Log detailed user information when available
                    log_parts = [f"user: {user_context.username} (ID: {user_context.user_id}, provider: {user_context.provider})"]
                    if user_context.name:
                        log_parts.append(f"name: {user_context.name}")
                    if user_context.email:
                        log_parts.append(f"email: {user_context.email}")
                    
                    logger.info(f"Executing {func.__name__} for authenticated {', '.join(log_parts)}")
                else:
                    logger.warning(f"Unauthenticated access attempt to {func.__name__}")
                    # For now, we'll continue execution but log the warning
                    # In a production system, you might want to raise an exception here
            else:
                logger.debug(f"Executing {func.__name__} (authentication disabled)")
                
            return await func(*args, **kwargs)
        return wrapper 