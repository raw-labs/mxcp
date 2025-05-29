# -*- coding: utf-8 -*-
"""Authentication middleware for MXCP endpoints."""
import logging
from typing import Any, Dict, Optional, Callable
from functools import wraps

from mcp.server.auth.middleware.auth_context import get_access_token
from mxcp.auth.providers import ExternalOAuthHandler, GeneralOAuthAuthorizationServer, UserContext
from mxcp.auth.context import set_user_context, reset_user_context

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
                
            logger.info(f"Found access token: {access_token.token[:10]}...")
                
            # Validate the token with the OAuth server
            token_info = await self.oauth_server.load_access_token(access_token.token)
            if not token_info:
                logger.warning("Invalid or expired access token")
                return None
                
            logger.info(f"Token validated successfully for client: {token_info.client_id}")
                
            # Get the external token to fetch user context
            external_token = self.oauth_server._token_mapping.get(access_token.token)
            if not external_token:
                logger.warning("No external token mapping found")
                return None
                
            logger.info(f"Found external token mapping: {external_token[:10]}...")
                
            # Get standardized user context from the provider
            try:
                user_context = await self.oauth_handler.get_user_context(external_token)
                logger.info(f"Successfully retrieved user context for {user_context.username} (provider: {user_context.provider})")
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
            Wrapped function that checks authentication and sets UserContext in context
        """
        @wraps(func)
        async def wrapper(*args, **kwargs):
            user_context = None
            context_token = None
            
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
            
            # Set the user context in the context variable
            context_token = set_user_context(user_context)
            
            try:
                return await func(*args, **kwargs)
            finally:
                # Always reset the context when done
                if context_token is not None:
                    reset_user_context(context_token)
                    
        return wrapper 