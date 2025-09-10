"""Authentication middleware for MXCP endpoints."""

import asyncio
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from functools import wraps
from typing import Any

from mcp.server.auth.middleware.auth_context import get_access_token

from mxcp.sdk.telemetry import record_counter, traced_operation

from ._types import UserContext
from .base import ExternalOAuthHandler, GeneralOAuthAuthorizationServer
from .context import reset_user_context, set_user_context

logger = logging.getLogger(__name__)

# Default cache TTL in seconds (5 minutes)
DEFAULT_USER_CONTEXT_CACHE_TTL = 300


@dataclass
class CachedUserContext:
    """Cached user context with expiration timestamp."""

    user_context: UserContext
    expires_at: float

    def is_expired(self) -> bool:
        """Check if the cached context has expired."""
        return time.time() >= self.expires_at


class AuthenticationMiddleware:
    """Middleware to handle authentication for MXCP endpoints."""

    def __init__(
        self,
        oauth_handler: ExternalOAuthHandler | None,
        oauth_server: GeneralOAuthAuthorizationServer | None,
        cache_ttl: int = DEFAULT_USER_CONTEXT_CACHE_TTL,
    ):
        """Initialize authentication middleware.

        Args:
            oauth_handler: OAuth handler instance (None if auth is disabled)
            oauth_server: OAuth authorization server instance (None if auth is disabled)
            cache_ttl: Cache TTL in seconds for user context caching
        """
        self.oauth_handler = oauth_handler
        self.oauth_server = oauth_server
        self.auth_enabled = oauth_handler is not None and oauth_server is not None
        self.cache_ttl = cache_ttl

        # Thread-safe cache for user contexts
        self._user_context_cache: dict[str, CachedUserContext] = {}
        self._cache_lock = asyncio.Lock()

    async def _get_cached_user_context(self, external_token: str) -> UserContext | None:
        """Get user context from cache if valid and not expired.

        Args:
            external_token: External OAuth token to use as cache key

        Returns:
            Cached user context if valid, None if expired or not found
        """
        async with self._cache_lock:
            cached_entry = self._user_context_cache.get(external_token)
            if cached_entry is None:
                return None

            if cached_entry.is_expired():
                # Remove expired entry
                del self._user_context_cache[external_token]
                logger.debug(f"⏰ Cache EXPIRED - removed entry for token {external_token[:20]}...")
                return None

            logger.info(
                f"🎯 Cache HIT - using cached user context for token {external_token[:20]}..."
            )
            return cached_entry.user_context

    async def _cache_user_context(self, external_token: str, user_context: UserContext) -> None:
        """Store user context in cache with expiration.

        Args:
            external_token: External OAuth token to use as cache key
            user_context: User context to cache
        """
        expires_at = time.time() + self.cache_ttl
        cached_entry = CachedUserContext(user_context=user_context, expires_at=expires_at)

        async with self._cache_lock:
            self._user_context_cache[external_token] = cached_entry
            logger.info(
                f"💾 Cache STORE - cached user context for token {external_token[:20]}... (TTL: {self.cache_ttl}s)"
            )

    async def _cleanup_expired_cache_entries(self) -> None:
        """Clean up expired cache entries to prevent memory leaks."""
        current_time = time.time()
        expired_keys = []

        async with self._cache_lock:
            for token, cached_entry in self._user_context_cache.items():
                if cached_entry.expires_at <= current_time:
                    expired_keys.append(token)

            for key in expired_keys:
                del self._user_context_cache[key]

            if expired_keys:
                logger.debug(f"🧹 Cache CLEANUP - removed {len(expired_keys)} expired entries")

    async def check_authentication(self) -> UserContext | None:
        """Check if the current request is authenticated.

        Returns:
            UserContext if authenticated, None if not authenticated or auth is disabled
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
                        # Record failed auth attempt
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

                # Get the external token to fetch user context
                if not self.oauth_server:
                    logger.warning("OAuth server not configured")
                    return None

                external_token = self.oauth_server._token_mapping.get(access_token.token)
                if not external_token:
                    logger.warning("No external token mapping found")
                    return None

                logger.info("External token mapping found")

                # Get standardized user context from the provider (with caching)
                try:
                    with traced_operation("mxcp.auth.get_user_context") as user_span:
                        if not self.oauth_handler:
                            logger.warning("OAuth handler not configured")
                            return None

                        # Try to get user context from cache first
                        user_context = await self._get_cached_user_context(external_token)

                        if user_context is None:
                            # Cache miss - call provider API
                            provider_name = getattr(
                                self.oauth_handler, "__class__", type(self.oauth_handler)
                            ).__name__
                            logger.info(
                                f"🔄 Cache MISS - calling {provider_name}.get_user_context() - Provider API call #{hash(external_token) % 10000}"
                            )

                            user_context = await self.oauth_handler.get_user_context(external_token)

                            # Cache the result for future requests
                            await self._cache_user_context(external_token, user_context)

                        # Trigger periodic cleanup of expired cache entries (non-blocking)
                        asyncio.create_task(self._cleanup_expired_cache_entries())
                        # Add external token to the user context for use in DuckDB functions
                        user_context.external_token = external_token
                        logger.info(
                            f"Successfully retrieved user context for {user_context.username} (provider: {user_context.provider})"
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

                        # Set success flags for metrics
                        provider = user_context.provider

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
            Wrapped function that checks authentication and sets UserContext in context
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
