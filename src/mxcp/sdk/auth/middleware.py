"""Authentication middleware for MXCP endpoints."""

import asyncio
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, replace
from functools import wraps
from typing import Any

from mcp.server.auth.middleware.auth_context import get_access_token
from starlette.exceptions import HTTPException

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

        # Cleanup task management to prevent task spam
        self._cleanup_task: asyncio.Task[None] | None = None
        self._cleanup_lock = asyncio.Lock()

        # Per-MCP-token locks for refresh operations to prevent race conditions
        self._refresh_locks: dict[str, asyncio.Lock] = {}
        self._refresh_locks_lock = asyncio.Lock()

    async def _get_refresh_lock(self, mcp_token: str) -> asyncio.Lock:
        """Get or create a refresh lock for the given MCP token.

        Args:
            mcp_token: MCP token to get lock for

        Returns:
            Lock specific to this MCP token
        """
        async with self._refresh_locks_lock:
            if mcp_token not in self._refresh_locks:
                self._refresh_locks[mcp_token] = asyncio.Lock()
            return self._refresh_locks[mcp_token]

    async def _remove_refresh_lock(self, mcp_token: str) -> None:
        """Remove the refresh lock for the given MCP token.

        Args:
            mcp_token: MCP token to remove lock for
        """
        async with self._refresh_locks_lock:
            if mcp_token in self._refresh_locks:
                del self._refresh_locks[mcp_token]
                logger.debug(f"🔓 Removed refresh lock for token {mcp_token[:20]}...")

    async def _get_cached_user_context(self, mcp_token: str) -> UserContext | None:
        """Get user context from cache if valid and not expired.

        Args:
            mcp_token: MCP token to use as cache key

        Returns:
            Cached user context if valid, None if expired or not found
        """
        should_remove_lock = False

        async with self._cache_lock:
            cached_entry = self._user_context_cache.get(mcp_token)
            if cached_entry is None:
                return None

            if cached_entry.is_expired():
                # Remove expired entry
                del self._user_context_cache[mcp_token]
                logger.debug(f"⏰ Cache EXPIRED - removed entry for token {mcp_token[:20]}...")
                should_remove_lock = True

            else:
                logger.debug(
                    f"🎯 Cache HIT - using cached user context for token {mcp_token[:20]}..."
                )
                return cached_entry.user_context

        # Clean up the refresh lock outside the cache lock to avoid lock ordering issues
        if should_remove_lock:
            await self._remove_refresh_lock(mcp_token)

        return None

    async def _cache_user_context(self, mcp_token: str, user_context: UserContext) -> None:
        """Store user context in cache with expiration.

        Args:
            mcp_token: MCP token to use as cache key
            user_context: User context to cache
        """
        expires_at = time.time() + self.cache_ttl
        cached_entry = CachedUserContext(user_context=user_context, expires_at=expires_at)

        async with self._cache_lock:
            self._user_context_cache[mcp_token] = cached_entry
            logger.debug(
                f"💾 Cache STORE - cached user context for token {mcp_token[:20]}... (TTL: {self.cache_ttl}s)"
            )

    async def _cleanup_expired_cache_entries(self) -> None:
        """Clean up expired cache entries and their refresh locks to prevent memory leaks."""
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

        # Clean up refresh locks for expired tokens (outside cache_lock to avoid deadlock)
        for key in expired_keys:
            await self._remove_refresh_lock(key)

    async def _schedule_cleanup_if_needed(self) -> None:
        """Schedule cleanup task if one isn't already running."""
        async with self._cleanup_lock:
            # Only start a new cleanup task if one isn't already running
            if self._cleanup_task is None or self._cleanup_task.done():
                self._cleanup_task = asyncio.create_task(self._cleanup_expired_cache_entries())

    async def _attempt_token_refresh(
        self, mcp_token: str, original_external_token: str
    ) -> str | None:
        """Attempt to refresh an expired external token.

        Args:
            mcp_token: The MCP token that needs its external token refreshed
            original_external_token: The original (expired) external token that triggered the refresh

        Returns:
            New external token if refresh successful, None if failed
        """
        if not self.oauth_server:
            logger.warning("No OAuth server available for token refresh")
            return None

        # Get the refresh lock for this specific MCP token to prevent race conditions
        refresh_lock = await self._get_refresh_lock(mcp_token)

        async with refresh_lock:
            try:
                # Check if another request already refreshed the token
                # by comparing the current token mapping with the original expired token
                current_external_token = self.oauth_server._token_mapping.get(mcp_token)
                if current_external_token != original_external_token:
                    logger.debug(
                        f"🎯 Token already refreshed by another request: {original_external_token[:10]}... -> {current_external_token[:10] if current_external_token else 'None'}..."
                    )
                    return current_external_token

                # Clear cache for the expired MCP token before attempting refresh
                async with self._cache_lock:
                    if mcp_token in self._user_context_cache:
                        del self._user_context_cache[mcp_token]
                        logger.debug(f"🗑️ Cleared expired cache entry: {mcp_token[:20]}...")

                # Note: We don't remove the refresh lock here since we're currently using it

                # Attempt refresh through the OAuth server
                new_external_token = await self.oauth_server.refresh_external_token(mcp_token)

                if new_external_token:
                    logger.info(
                        f"🔄 Successfully refreshed external token: {original_external_token[:10]}... -> {new_external_token[:10]}..."
                    )

                    # Immediately fetch and cache new user context to avoid future API calls
                    if self.oauth_handler:
                        try:
                            new_user_context = await self.oauth_handler.get_user_context(
                                new_external_token
                            )
                            await self._cache_user_context(mcp_token, new_user_context)
                        except Exception as e:
                            logger.warning(f"Failed to cache new user context after refresh: {e}")

                    return new_external_token
                else:
                    logger.warning("Token refresh returned no new token")
                    return None

            except Exception as e:
                logger.error(f"Error during token refresh: {e}")
                return None

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

                logger.debug("Access token found in request context")
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

                logger.debug(f"Token validated successfully for client: {token_info.client_id}")

                # Get the external token to fetch user context
                if not self.oauth_server:
                    logger.warning("OAuth server not configured")
                    return None

                external_token = self.oauth_server._token_mapping.get(access_token.token)
                if not external_token:
                    logger.warning("No external token mapping found")
                    return None

                logger.debug("External token mapping found")

                # Get standardized user context from the provider (with caching)
                try:
                    with traced_operation("mxcp.auth.get_user_context") as user_span:
                        if not self.oauth_handler:
                            logger.warning("OAuth handler not configured")
                            return None

                        # Try to get user context from cache first (quick check without lock)
                        cached_user_context = await self._get_cached_user_context(
                            access_token.token
                        )

                        if cached_user_context is None:
                            # Cache miss - use per-token lock to prevent stampede
                            refresh_lock = await self._get_refresh_lock(access_token.token)
                            
                            async with refresh_lock:
                                # Double-check cache after acquiring lock
                                # Another request might have filled it while we waited
                                cached_user_context = await self._get_cached_user_context(
                                    access_token.token
                                )
                                
                                if cached_user_context is None:
                                    # Still a cache miss - make the API call
                                    provider_name = getattr(
                                        self.oauth_handler, "__class__", type(self.oauth_handler)
                                    ).__name__
                                    logger.debug(
                                        f"🔄 Cache MISS - calling {provider_name}.get_user_context() - Provider API call #{hash(external_token) % 10000}"
                                    )

                                    try:
                                        cached_user_context = await self.oauth_handler.get_user_context(
                                            external_token
                                        )
                                        # Cache the successful result immediately
                                        await self._cache_user_context(
                                            access_token.token, cached_user_context
                                        )
                                    except HTTPException as e:
                                        # Check if this is a 401/token expired error
                                        if e.status_code == 401:
                                            logger.info("🔄 Access token expired, attempting refresh...")

                                            # Attempt to refresh the token
                                            refreshed_token = await self._attempt_token_refresh(
                                                access_token.token, external_token
                                            )

                                            if refreshed_token:
                                                logger.info(
                                                    "✅ Token refresh successful, retrying user context"
                                                )
                                                # Update external_token to the refreshed token
                                                external_token = refreshed_token
                                                # Retry with the new token
                                                cached_user_context = (
                                                    await self.oauth_handler.get_user_context(
                                                        refreshed_token
                                                    )
                                                )
                                                # Cache the result after successful refresh
                                                await self._cache_user_context(
                                                    access_token.token, cached_user_context
                                                )
                                            else:
                                                logger.error(
                                                    "❌ Token refresh failed, re-raising original error"
                                                )
                                                raise
                                        else:
                                            # Not a token expiry error, re-raise
                                            raise
                                    except Exception as e:
                                        # Handle non-HTTP exceptions (network errors, etc.)
                                        logger.error(f"Non-HTTP error during get_user_context: {e}")
                                        raise
                                else:
                                    # Cache hit after waiting for lock
                                    logger.debug(
                                        f"🎯 Cache HIT (after lock wait) - another request filled cache for token {access_token.token[:20]}..."
                                    )

                        # Trigger periodic cleanup of expired cache entries (non-blocking)
                        await self._schedule_cleanup_if_needed()
                        # Add external token to the user context for use in DuckDB functions
                        user_context = replace(cached_user_context, external_token=external_token)
                        logger.debug(
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
                    logger.debug(
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
