"""Tests for authentication middleware caching and concurrency fixes."""

import asyncio
import time
from unittest.mock import AsyncMock, Mock

import pytest

from mxcp.sdk.auth._types import UserContext
from mxcp.sdk.auth.middleware import AuthenticationMiddleware, CachedUserContext


class TestAuthenticationMiddleware:
    """Test cases for AuthenticationMiddleware caching behavior."""

    @pytest.fixture
    def mock_oauth_handler(self) -> AsyncMock:
        """Create a mock OAuth handler."""
        handler = AsyncMock()
        handler.get_user_context = AsyncMock()
        return handler

    @pytest.fixture
    def mock_oauth_server(self) -> Mock:
        """Create a mock OAuth server."""
        server = Mock()
        server.load_access_token = AsyncMock()
        server._token_mapping = {}
        return server

    @pytest.fixture
    def user_context(self) -> UserContext:
        """Create a sample user context."""
        return UserContext(
            user_id="test_user_123",
            username="testuser",
            email="test@example.com",
            provider="github",
            external_token=None,  # Will be set by middleware
        )

    @pytest.fixture
    def middleware(
        self, mock_oauth_handler: AsyncMock, mock_oauth_server: Mock
    ) -> AuthenticationMiddleware:
        """Create middleware instance with mocked dependencies."""
        return AuthenticationMiddleware(
            oauth_handler=mock_oauth_handler,
            oauth_server=mock_oauth_server,
            cache_ttl=300,  # 5 minutes
        )

    async def test_user_context_caching_basic(
        self, middleware: AuthenticationMiddleware, user_context: UserContext
    ) -> None:
        """Test that user context is properly cached and retrieved."""
        external_token = "test_external_token_123"

        # First call should cache the result
        await middleware._cache_user_context(external_token, user_context)

        # Second call should retrieve from cache
        cached_context = await middleware._get_cached_user_context(external_token)

        assert cached_context is not None
        assert cached_context.user_id == user_context.user_id
        assert cached_context.username == user_context.username
        assert cached_context.email == user_context.email
        assert cached_context.provider == user_context.provider

    async def test_cache_expiration(
        self, middleware: AuthenticationMiddleware, user_context: UserContext
    ) -> None:
        """Test that cached entries expire after TTL."""
        external_token = "test_external_token_456"

        # Create middleware with very short TTL
        short_ttl_middleware = AuthenticationMiddleware(
            oauth_handler=middleware.oauth_handler,
            oauth_server=middleware.oauth_server,
            cache_ttl=1,  # 1 second
        )

        # Cache the user context
        await short_ttl_middleware._cache_user_context(external_token, user_context)

        # Should be available immediately
        cached_context = await short_ttl_middleware._get_cached_user_context(external_token)
        assert cached_context is not None

        # Wait for expiration
        await asyncio.sleep(1.1)

        # Should be expired and removed
        expired_context = await short_ttl_middleware._get_cached_user_context(external_token)
        assert expired_context is None

    async def test_cached_user_context_expiration_check(self) -> None:
        """Test CachedUserContext expiration logic."""
        user_context = UserContext(
            user_id="test",
            username="test",
            email="test@example.com",
            provider="github",
        )

        # Create expired entry
        expired_entry = CachedUserContext(
            user_context=user_context,
            expires_at=time.time() - 100,  # 100 seconds ago
        )
        assert expired_entry.is_expired()

        # Create valid entry
        valid_entry = CachedUserContext(
            user_context=user_context,
            expires_at=time.time() + 100,  # 100 seconds from now
        )
        assert not valid_entry.is_expired()

    async def test_cleanup_removes_expired_entries(
        self, middleware: AuthenticationMiddleware, user_context: UserContext
    ) -> None:
        """Test that cleanup properly removes expired entries."""
        # Create middleware with very short TTL for testing
        short_ttl_middleware = AuthenticationMiddleware(
            oauth_handler=middleware.oauth_handler,
            oauth_server=middleware.oauth_server,
            cache_ttl=1,  # 1 second
        )

        # Add multiple entries
        tokens = ["token1", "token2", "token3"]
        for token in tokens:
            await short_ttl_middleware._cache_user_context(token, user_context)

        # Verify all are cached
        assert len(short_ttl_middleware._user_context_cache) == 3

        # Wait for expiration
        await asyncio.sleep(1.1)

        # Run cleanup
        await short_ttl_middleware._cleanup_expired_cache_entries()

        # All should be removed
        assert len(short_ttl_middleware._user_context_cache) == 0

    async def test_default_cache_ttl(self) -> None:
        """Test that default cache TTL is used when not specified."""
        from mxcp.sdk.auth.middleware import DEFAULT_USER_CONTEXT_CACHE_TTL

        middleware = AuthenticationMiddleware(
            oauth_handler=None,
            oauth_server=None,
        )

        assert middleware.cache_ttl == DEFAULT_USER_CONTEXT_CACHE_TTL
        assert middleware.cache_ttl == 300  # 5 minutes

    async def test_custom_cache_ttl(self) -> None:
        """Test that custom cache TTL is properly set."""
        custom_ttl = 600  # 10 minutes

        middleware = AuthenticationMiddleware(
            oauth_handler=None,
            oauth_server=None,
            cache_ttl=custom_ttl,
        )

        assert middleware.cache_ttl == custom_ttl
