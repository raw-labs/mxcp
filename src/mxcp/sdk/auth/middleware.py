"""Authentication middleware for MXCP endpoints."""

import logging
from collections.abc import Callable
from functools import wraps
from typing import Any

from mcp.server.auth.middleware.auth_context import get_access_token

from mxcp.sdk.telemetry import traced_operation

from ._types import UserContext
from .base import ExternalOAuthHandler, GeneralOAuthAuthorizationServer
from .context import reset_user_context, set_user_context

logger = logging.getLogger(__name__)


class AuthenticationMiddleware:
    """Middleware to handle authentication for MXCP endpoints."""

    def __init__(
        self,
        oauth_handler: ExternalOAuthHandler | None,
        oauth_server: GeneralOAuthAuthorizationServer | None,
    ):
        """Initialize authentication middleware.

        Args:
            oauth_handler: OAuth handler instance (None if auth is disabled)
            oauth_server: OAuth authorization server instance (None if auth is disabled)
        """
        self.oauth_handler = oauth_handler
        self.oauth_server = oauth_server
        self.auth_enabled = oauth_handler is not None and oauth_server is not None

    async def check_authentication(self) -> UserContext | None:
        """Check if the current request is authenticated.

        Returns:
            UserContext if authenticated, None if not authenticated or auth is disabled
        """
        with traced_operation(
            "mxcp.auth.check_authentication",
            attributes={
                "mxcp.auth.enabled": self.auth_enabled,
            }
        ) as span:
            if not self.auth_enabled:
                logger.debug("Authentication is disabled")
                return None

            try:
                # Get the access token from the current request context
                access_token = get_access_token()
                if not access_token:
                    logger.warning("No access token found in request context")
                    if span:
                        span.set_attribute("mxcp.auth.has_token", False)
                    return None

                logger.info(f"Found access token: {access_token.token[:10]}...")
                if span:
                    span.set_attribute("mxcp.auth.has_token", True)

                # Validate the token with the OAuth server
                if not self.oauth_server:
                    logger.warning("OAuth server not configured")
                    return None

                with traced_operation("mxcp.auth.validate_token") as token_span:
                    token_info = await self.oauth_server.load_access_token(access_token.token)
                    if not token_info:
                        logger.warning("Invalid or expired access token")
                        if token_span:
                            token_span.set_attribute("mxcp.auth.token_valid", False)
                        return None
                    if token_span:
                        token_span.set_attribute("mxcp.auth.token_valid", True)
                        token_span.set_attribute("mxcp.auth.client_id", token_info.client_id)

                logger.info(f"Token validated successfully for client: {token_info.client_id}")

                # Get the external token to fetch user context
                if not self.oauth_server:
                    logger.warning("OAuth server not configured")
                    return None

                external_token = self.oauth_server._token_mapping.get(access_token.token)
                if not external_token:
                    logger.warning("No external token mapping found")
                    return None

                logger.info(f"Found external token mapping: {external_token[:10]}...")

                # Get standardized user context from the provider
                try:
                    with traced_operation("mxcp.auth.get_user_context") as user_span:
                        if not self.oauth_handler:
                            logger.warning("OAuth handler not configured")
                            return None

                        user_context = await self.oauth_handler.get_user_context(external_token)
                        # Add external token to the user context for use in DuckDB functions
                        user_context.external_token = external_token
                        logger.info(
                            f"Successfully retrieved user context for {user_context.username} (provider: {user_context.provider})"
                        )

                        if user_span:
                            user_span.set_attribute("mxcp.auth.provider", user_context.provider)
                            user_span.set_attribute("mxcp.auth.user_id", user_context.user_id)
                            # Don't log sensitive username for privacy
                            user_span.set_attribute("mxcp.auth.has_username", bool(user_context.username))
                            user_span.set_attribute("mxcp.auth.success", True)

                        if span:
                            span.set_attribute("mxcp.auth.authenticated", True)
                            span.set_attribute("mxcp.auth.provider", user_context.provider)

                        return user_context
                except Exception as e:
                    logger.error(f"Failed to get user context: {e}")
                    if span:
                        span.set_attribute("mxcp.auth.authenticated", False)
                        span.set_attribute("mxcp.auth.error", str(e))
                    return None

            except Exception as e:
                logger.error(f"Authentication check failed: {e}")
                if span:
                    span.set_attribute("mxcp.auth.error", str(e))
                return None

    def require_auth(self, func: Callable[..., Any]) -> Callable[..., Any]:
        """Decorator to require authentication for a function.

        Args:
            func: Function to protect with authentication

        Returns:
            Wrapped function that checks authentication and sets UserContext in context
        """

        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            user_context = None
            context_token = None

            if self.auth_enabled:
                user_context = await self.check_authentication()
                if user_context:
                    # Log detailed user information when available
                    log_parts = [
                        f"user: {user_context.username} (ID: {user_context.user_id}, provider: {user_context.provider})"
                    ]
                    if user_context.name:
                        log_parts.append(f"name: {user_context.name}")
                    if user_context.email:
                        log_parts.append(f"email: {user_context.email}")

                    logger.info(
                        f"Executing {func.__name__} for authenticated {', '.join(log_parts)}"
                    )
                else:
                    logger.error(f"Authentication required but failed for {func.__name__}")
                    from starlette.exceptions import HTTPException

                    raise HTTPException(401, "Authentication required")
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
