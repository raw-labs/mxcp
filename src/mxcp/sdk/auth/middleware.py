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
import time
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
        provider_token_skew_seconds: int = 120,
        refresh_backoff_seconds: int = 30,
        fetch_userinfo_after_refresh: bool = False,
    ):
        """Initialize authentication middleware.

        Args:
            session_manager: Session manager for issuer-mode auth (None if auth is disabled)
            provider_adapter: Provider adapter for optionally refreshing user info (may be None)
            token_getter: Callable returning the access token string (or None)
            provider_token_skew_seconds: Time skew to consider provider tokens near expiry
            refresh_backoff_seconds: Backoff window after refresh failures
            fetch_userinfo_after_refresh: If True, fetch userinfo once after refresh
        """
        self.session_manager = session_manager
        self.provider_adapter = provider_adapter
        self.token_getter = token_getter
        self.provider_token_skew_seconds = provider_token_skew_seconds
        self.refresh_backoff_seconds = refresh_backoff_seconds
        self.fetch_userinfo_after_refresh = fetch_userinfo_after_refresh

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

                logger.info("Access token found in request context")
                if span:
                    span.set_attribute("mxcp.auth.has_token", True)

                return await self._check_with_session_manager(
                    token_value, span=span, provider_override=provider
                )

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
        refreshed = False

        if self.provider_adapter:
            session, refreshed = await self._refresh_provider_tokens_if_needed(
                session, provider, span=span
            )
            if session is None:
                return None

            if self.fetch_userinfo_after_refresh and refreshed and session.provider_access_token:
                try:
                    user_info = await self.provider_adapter.fetch_user_info(
                        access_token=session.provider_access_token
                    )
                except ProviderError as exc:
                    logger.warning(
                        "Failed to refresh user info after provider token refresh",
                        extra={"provider": provider, "error": exc.error},
                    )
                    record_counter(
                        "mxcp.auth.userinfo_refresh_total",
                        attributes={"provider": provider, "status": "error"},
                        description="Total provider userinfo refresh attempts",
                    )
                else:
                    record_counter(
                        "mxcp.auth.userinfo_refresh_total",
                        attributes={"provider": provider, "status": "success"},
                        description="Total provider userinfo refresh attempts",
                    )
                    if self.session_manager:
                        session = await self.session_manager.persist_provider_tokens(
                            session,
                            provider_access_token=session.provider_access_token,
                            provider_refresh_token=session.provider_refresh_token,
                            provider_expires_at=session.provider_expires_at,
                            provider_refresh_expires_at=session.provider_refresh_expires_at,
                            provider_refresh_backoff_until=session.provider_refresh_backoff_until,
                            user_info=user_info,
                        )

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

    async def _refresh_provider_tokens_if_needed(
        self, session: Any, provider: str, span: Any | None = None
    ) -> tuple[Any | None, bool]:
        """Refresh provider tokens when near expiry with skew and backoff handling."""
        if not self.provider_adapter or not self.session_manager:
            return session, False

        now = time.time()

        backoff_until = getattr(session, "provider_refresh_backoff_until", None)
        if backoff_until and backoff_until > now:
            logger.info(
                "Skipping provider token refresh due to backoff",
                extra={"provider": provider},
            )
            if span:
                span.set_attribute("mxcp.auth.provider_refresh_skipped_backoff", True)
            return session, False

        expires_at = getattr(session, "provider_expires_at", None)
        refresh_token = getattr(session, "provider_refresh_token", None)
        access_token = getattr(session, "provider_access_token", None)
        refresh_expires_at = getattr(session, "provider_refresh_expires_at", None)

        needs_refresh = access_token is None
        if expires_at is not None and expires_at - now < self.provider_token_skew_seconds:
            needs_refresh = True

        if not needs_refresh:
            return session, False

        if refresh_expires_at is not None and refresh_expires_at <= now:
            logger.warning(
                "Provider refresh token expired; re-auth required",
                extra={"provider": provider},
            )
            await self.session_manager.persist_provider_tokens(
                session,
                provider_access_token=None,
                provider_refresh_token=None,
                provider_expires_at=None,
                provider_refresh_expires_at=refresh_expires_at,
                provider_refresh_backoff_until=now + self.refresh_backoff_seconds,
            )
            return None, False

        if not refresh_token:
            logger.warning(
                "Provider access token expired and no refresh token available",
                extra={"provider": provider},
            )
            return None, False

        record_counter(
            "mxcp.auth.provider_refresh_total",
            attributes={"provider": provider, "status": "attempt"},
            description="Total provider token refresh attempts",
        )
        try:
            grant = await self.provider_adapter.refresh_token(
                refresh_token=refresh_token, scopes=session.scopes or []
            )
        except ProviderError as exc:
            logger.warning(
                "Provider token refresh failed; requiring re-auth",
                extra={"provider": provider, "error": exc.error, "status_code": exc.status_code},
            )
            backoff_until = now + self.refresh_backoff_seconds
            drop_refresh = exc.error == "invalid_grant" or exc.status_code in {400, 401}
            await self.session_manager.persist_provider_tokens(
                session,
                provider_access_token=None,
                provider_refresh_token=None if drop_refresh else refresh_token,
                provider_expires_at=None,
                provider_refresh_expires_at=refresh_expires_at,
                provider_refresh_backoff_until=backoff_until,
            )
            record_counter(
                "mxcp.auth.provider_refresh_total",
                attributes={"provider": provider, "status": "failure"},
                description="Total provider token refresh attempts",
            )
            if span:
                span.set_attribute("mxcp.auth.provider_refresh_error", exc.error)
            return None, False

        new_refresh_expires_at = grant.refresh_expires_at
        if new_refresh_expires_at is None and grant.refresh_expires_in is not None:
            new_refresh_expires_at = now + grant.refresh_expires_in

        updated_session = await self.session_manager.persist_provider_tokens(
            session,
            provider_access_token=grant.access_token,
            provider_refresh_token=grant.refresh_token or refresh_token,
            provider_expires_at=grant.expires_at,
            provider_refresh_expires_at=new_refresh_expires_at,
            provider_refresh_backoff_until=None,
        )
        record_counter(
            "mxcp.auth.provider_refresh_total",
            attributes={"provider": provider, "status": "success"},
            description="Total provider token refresh attempts",
        )
        if span:
            span.set_attribute("mxcp.auth.provider_refreshed", True)
        return updated_session, True
