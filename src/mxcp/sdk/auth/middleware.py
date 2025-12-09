"""Authentication middleware for MXCP endpoints."""

import logging
from collections.abc import Callable
from functools import wraps
from typing import Any

from mcp.server.auth.middleware.auth_context import get_access_token

from mxcp.sdk.auth.contracts import ProviderAdapter, ProviderError
from mxcp.sdk.auth.session_manager import SessionManager
from mxcp.sdk.telemetry import record_counter, traced_operation

from .base import ExternalOAuthHandler, GeneralOAuthAuthorizationServer
from .context import reset_user_context, set_user_context
from .models import UserContextModel

logger = logging.getLogger(__name__)


class AuthenticationMiddleware:
    """Middleware to handle authentication for MXCP endpoints."""

    def __init__(
        self,
        oauth_handler: ExternalOAuthHandler | None,
        oauth_server: GeneralOAuthAuthorizationServer | None,
        *,
        session_manager: SessionManager | None = None,
        provider_adapter: ProviderAdapter | None = None,
        token_getter: Callable[[], Any] | None = None,
    ):
        """Initialize authentication middleware.

        Args:
            oauth_handler: OAuth handler instance (None if auth is disabled)
            oauth_server: OAuth authorization server instance (None if auth is disabled)
            session_manager: Session manager for new auth flow
            provider_adapter: Provider adapter for fetching user context
            token_getter: Override for access token retrieval (useful for tests)
        """
        self.oauth_handler = oauth_handler
        self.oauth_server = oauth_server
        self.session_manager = session_manager
        self.provider_adapter = provider_adapter
        self.token_getter = token_getter or get_access_token

        self.using_session_manager = session_manager is not None and provider_adapter is not None
        self.auth_enabled = self.using_session_manager or (
            oauth_handler is not None and oauth_server is not None
        )

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
                access_token_obj = self.token_getter()
                token_value = (
                    access_token_obj.token
                    if hasattr(access_token_obj, "token")
                    else access_token_obj
                )

                if not token_value:
                    logger.warning("No access token found in request context")
                    if span:
                        span.set_attribute("mxcp.auth.has_token", False)
                    record_counter(
                        "mxcp.auth.attempts_total",
                        attributes={"provider": provider, "status": "no_token"},
                        description="Total authentication attempts",
                    )
                    return None

                logger.info("Access token found in request context")
                if span:
                    span.set_attribute("mxcp.auth.has_token", True)

                if self.using_session_manager:
                    return await self._check_with_session_manager(
                        token_value, span=span, provider_override=provider
                    )

                # Legacy path using oauth_server/oauth_handler
                if not self.oauth_server:
                    logger.warning("OAuth server not configured")
                    return None

                with traced_operation("mxcp.auth.validate_token") as token_span:
                    token_info = await self.oauth_server.load_access_token(token_value)
                    if not token_info:
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
                        token_span.set_attribute("mxcp.auth.client_id", token_info.client_id)

                logger.info(f"Token validated successfully for client: {token_info.client_id}")

                external_token = self.oauth_server._token_mapping.get(token_value)
                if not external_token:
                    logger.warning("No external token mapping found")
                    return None

                logger.info("External token mapping found")

                try:
                    with traced_operation("mxcp.auth.get_user_context") as user_span:
                        if not self.oauth_handler:
                            logger.warning("OAuth handler not configured")
                            return None

                        user_context = await self.oauth_handler.get_user_context(external_token)
                        user_context = user_context.model_copy(
                            update={"external_token": external_token}
                        )
                        logger.info(
                            f"Successfully retrieved user context for {user_context.username} (provider: {user_context.provider})"
                        )

                        if user_span:
                            user_span.set_attribute("mxcp.auth.provider", user_context.provider)
                            user_span.set_attribute("mxcp.auth.user_id", user_context.user_id)
                            user_span.set_attribute(
                                "mxcp.auth.has_username", bool(user_context.username)
                            )
                            user_span.set_attribute("mxcp.auth.success", True)

                        if span:
                            span.set_attribute("mxcp.auth.authenticated", True)
                            span.set_attribute("mxcp.auth.provider", user_context.provider)

                        provider = user_context.provider

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

    async def _check_with_session_manager(
        self, token_value: str, span: Any | None = None, provider_override: str = "unknown"
    ) -> UserContextModel | None:
        """Validate tokens using SessionManager / ProviderAdapter path."""
        session = (
            await self.session_manager.get_session(token_value) if self.session_manager else None
        )
        if not session:
            logger.warning("Invalid or expired access token (session manager)")
            record_counter(
                "mxcp.auth.attempts_total",
                attributes={"provider": provider_override, "status": "invalid_token"},
                description="Total authentication attempts",
            )
            return None

        provider = session.provider
        if span:
            span.set_attribute("mxcp.auth.token_valid", True)
            span.set_attribute("mxcp.auth.provider", provider)

        user_info = session.user_info

        if self.provider_adapter and session.provider_access_token:
            try:
                user_info = await self.provider_adapter.fetch_user_info(
                    access_token=session.provider_access_token
                )
            except ProviderError as exc:
                logger.warning(f"Failed to fetch user info from provider: {exc}")
                record_counter(
                    "mxcp.auth.attempts_total",
                    attributes={"provider": provider, "status": "error"},
                    description="Total authentication attempts",
                )
                return None

        user_context = UserContextModel(
            provider=user_info.provider,
            user_id=user_info.user_id,
            username=user_info.username,
            email=user_info.email,
            name=user_info.name,
            avatar_url=user_info.avatar_url,
            raw_profile=user_info.raw_profile,
            external_token=session.provider_access_token,
        )

        if span:
            span.set_attribute("mxcp.auth.authenticated", True)
            span.set_attribute("mxcp.auth.user_id", user_context.user_id)

        record_counter(
            "mxcp.auth.attempts_total",
            attributes={"provider": provider, "status": "success"},
            description="Total authentication attempts",
        )

        return user_context
