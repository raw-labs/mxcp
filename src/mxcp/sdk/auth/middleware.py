"""Authentication middleware for MXCP endpoints.

This module validates MXCP access tokens (issuer-mode) and sets a request-scoped
`UserContextModel`.

## Design notes

- The middleware should primarily rely on the **MXCP session** stored in the
  `TokenStore` (via `SessionManager`). Calling the upstream IdP on every request
  introduces availability and latency coupling; if enabled, it should be a conscious
  policy decision.

## Security invariants (“do not break”)

- Never log tokens, secrets, email addresses, or user identifiers.
- Avoid attaching sensitive values to traces/metrics.
"""

import logging
from collections.abc import Callable
from functools import wraps
from typing import Any

from starlette.exceptions import HTTPException

from mxcp.sdk.auth.contracts import ProviderAdapter, ProviderError
from mxcp.sdk.auth.session_manager import SessionManager
from mxcp.sdk.telemetry import record_counter, traced_operation

from .context import reset_user_context, set_user_context
from .models import UserContextModel

logger = logging.getLogger(__name__)


class AuthenticationMiddleware:
    """Middleware to handle authentication for MXCP endpoints."""

    def __init__(
        self,
        *,
        session_manager: SessionManager | None = None,
        provider_adapter: ProviderAdapter | None = None,
        token_getter: Callable[[], str | None],
    ):
        """Initialize authentication middleware.

        Args:
            session_manager: Session manager for issuer-mode auth (None if auth is disabled)
            provider_adapter: Provider adapter for optionally refreshing user info (may be None)
            token_getter: Callable returning the access token string (or None)
        """
        self.session_manager = session_manager
        self.provider_adapter = provider_adapter
        self.token_getter = token_getter

        self.auth_enabled = session_manager is not None

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
                token_value = self.token_getter()

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

                logger.info("Access token present in request context")
                if span:
                    span.set_attribute("mxcp.auth.has_token", True)

                return await self._check_with_session_manager(
                    token_value, span=span, provider_override=provider
                )

            except Exception:
                logger.error("Authentication check failed")
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
                    logger.info(
                        "Executing %s for authenticated request (provider: %s)",
                        func.__name__,
                        user_context.provider,
                    )
                else:
                    logger.error("Authentication required but failed for %s", func.__name__)
                    raise HTTPException(401, "Authentication required")
            else:
                logger.debug("Executing %s (authentication disabled)", func.__name__)

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
        if not self.session_manager:
            logger.debug("Session manager not configured")
            return None

        session = await self.session_manager.get_session(token_value)
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
            except ProviderError:
                logger.warning("Failed to fetch user info from provider; using cached session data")
                if span:
                    span.set_attribute("mxcp.auth.user_info_source", "session")
        elif span:
            span.set_attribute("mxcp.auth.user_info_source", "session")
        if span and user_info is not session.user_info:
            span.set_attribute("mxcp.auth.user_info_source", "provider")

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

        record_counter(
            "mxcp.auth.attempts_total",
            attributes={"provider": provider, "status": "success"},
            description="Total authentication attempts",
        )

        return user_context
