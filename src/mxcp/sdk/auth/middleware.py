"""Authentication middleware for MXCP endpoints."""

import logging
from collections.abc import Callable
from functools import wraps
from typing import TYPE_CHECKING, Any

from mcp.server.auth.middleware.auth_context import get_access_token

from mxcp.sdk.telemetry import record_counter, traced_operation

from .context import reset_user_context, set_user_context
from .models import UserContextModel

if TYPE_CHECKING:
    from .adapter import ProviderAdapter
    from .sessions import SessionManager

logger = logging.getLogger(__name__)


class AuthenticationMiddleware:
    """Middleware to handle authentication for MXCP endpoints."""

    def __init__(
        self,
        session_manager: "SessionManager | None" = None,
        provider_adapter: "ProviderAdapter | None" = None,
    ):
        """Initialize authentication middleware.

        Args:
            session_manager: SessionManager for token validation and session lookup.
            provider_adapter: Provider adapter for fetching user info.
        """
        self.session_manager = session_manager
        self.provider_adapter = provider_adapter
        self.auth_enabled = session_manager is not None and provider_adapter is not None

    async def check_authentication(self) -> UserContextModel | None:
        """Check if the current request is authenticated.

        Returns:
            UserContextModel if authenticated, None if not authenticated or auth is disabled
        """
        provider = "unknown"

        with traced_operation(
            "mxcp.auth.check_authentication",
            attributes={
                "mxcp.auth.enabled": self.auth_enabled,
            },
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
                    # Record failed auth attempt
                    record_counter(
                        "mxcp.auth.attempts_total",
                        attributes={"provider": provider, "status": "no_token"},
                        description="Total authentication attempts",
                    )
                    return None

                logger.info("Access token found in request context")
                if span:
                    span.set_attribute("mxcp.auth.has_token", True)

                # Validate the token and get the session
                if not self.session_manager:
                    logger.warning("Session manager not configured")
                    return None

                with traced_operation("mxcp.auth.validate_token") as token_span:
                    session = await self.session_manager.get_session(access_token.token)
                    if not session:
                        logger.warning("Invalid or expired access token")
                        if token_span:
                            token_span.set_attribute("mxcp.auth.token_valid", False)
                        record_counter(
                            "mxcp.auth.attempts_total",
                            attributes={"provider": provider, "status": "invalid_token"},
                            description="Total authentication attempts",
                        )
                        return None
                    if token_span:
                        token_span.set_attribute("mxcp.auth.token_valid", True)
                        token_span.set_attribute("mxcp.auth.client_id", session.client_id)

                logger.info(f"Token validated successfully for client: {session.client_id}")

                # Get the provider token from the session
                provider_token = session.provider_token
                if not provider_token:
                    logger.warning("No provider token in session")
                    return None

                logger.debug("Provider token found in session")

                # Get user context from the provider
                try:
                    with traced_operation("mxcp.auth.get_user_context") as user_span:
                        if not self.provider_adapter:
                            logger.warning("Provider adapter not configured")
                            return None

                        user_info = await self.provider_adapter.fetch_user_info(provider_token)
                        provider = self.provider_adapter.provider_name

                        # Convert UserInfo to UserContextModel
                        user_context = UserContextModel(
                            provider=provider,
                            user_id=user_info.user_id,
                            username=user_info.username,
                            email=user_info.email,
                            name=user_info.name,
                            external_token=provider_token,
                        )

                        logger.info(
                            f"Successfully retrieved user context for {user_context.username} "
                            f"(provider: {user_context.provider})"
                        )

                        if user_span:
                            user_span.set_attribute("mxcp.auth.provider", user_context.provider)
                            user_span.set_attribute("mxcp.auth.user_id", user_context.user_id)
                            # Don't log sensitive username for privacy
                            user_span.set_attribute(
                                "mxcp.auth.has_username", bool(user_context.username)
                            )
                            user_span.set_attribute("mxcp.auth.success", True)

                        if span:
                            span.set_attribute("mxcp.auth.authenticated", True)
                            span.set_attribute("mxcp.auth.provider", user_context.provider)

                        # Record auth attempt metrics before returning
                        record_counter(
                            "mxcp.auth.attempts_total",
                            attributes={"provider": provider, "status": "success"},
                            description="Total authentication attempts",
                        )

                        return user_context

                except Exception as e:
                    logger.error(f"Failed to get user context: {e}")
                    if span:
                        span.set_attribute("mxcp.auth.authenticated", False)
                        span.set_attribute("mxcp.auth.error", str(e))
                    # Record failed auth attempt
                    record_counter(
                        "mxcp.auth.attempts_total",
                        attributes={"provider": provider, "status": "error"},
                        description="Total authentication attempts",
                    )
                    return None

            except Exception as e:
                logger.error(f"Authentication check failed: {e}")
                if span:
                    span.set_attribute("mxcp.auth.error", str(e))
                # Record failed auth attempt
                record_counter(
                    "mxcp.auth.attempts_total",
                    attributes={"provider": provider, "status": "error"},
                    description="Total authentication attempts",
                )
                return None

    def require_auth(self, func: Callable[..., Any]) -> Callable[..., Any]:
        """Decorator to require authentication for a function.

        Args:
            func: Function to protect with authentication

        Returns:
            Wrapped function that checks authentication and sets UserContextModel in context
        """

        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            user_context = None
            context_token = None

            if self.auth_enabled:
                user_context = await self.check_authentication()
                if user_context:
                    # Log authentication status without PII
                    logger.info(
                        f"Executing {func.__name__} for authenticated user "
                        f"(provider: {user_context.provider})"
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
