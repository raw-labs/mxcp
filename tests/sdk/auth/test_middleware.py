"""Tests for authentication middleware caching and concurrency fixes."""

import asyncio
import time
from typing import Any
from unittest.mock import AsyncMock, Mock

import pytest

from mxcp.sdk.auth._types import UserContext
from mxcp.sdk.auth.base import ExternalOAuthHandler
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


class TestOAuthHandlerRefreshToken:
    """Test cases for OAuth handler refresh token behavior."""

    async def test_refresh_access_token_not_implemented_by_default(self) -> None:
        """Test that base ExternalOAuthHandler raises NotImplementedError for refresh."""
        # Create a minimal concrete implementation that only implements abstract methods
        class MinimalOAuthHandler(ExternalOAuthHandler):
            """Minimal OAuth handler for testing default refresh behavior."""

            def get_authorize_url(self, client_id: str, params: Any) -> str:
                return "https://example.com/authorize"

            async def exchange_code(self, code: str, state: str) -> tuple[Any, Any]:
                from mxcp.sdk.auth._types import ExternalUserInfo, StateMeta

                user_info = ExternalUserInfo(
                    id="test_user",
                    scopes=[],
                    raw_token="test_token",
                    provider="test",
                )
                meta = StateMeta(
                    redirect_uri="https://example.com/callback",
                    code_challenge="",
                    redirect_uri_provided_explicitly=False,
                    client_id="test_client",
                )
                return user_info, meta

            @property
            def callback_path(self) -> str:
                return "/test/callback"

            async def on_callback(self, request: Any, provider: Any) -> Any:
                return None

            async def get_user_context(self, token: str) -> UserContext:
                return UserContext(
                    user_id="test_user",
                    username="testuser",
                    email="test@example.com",
                    provider="test",
                )

        handler = MinimalOAuthHandler()

        # Verify that refresh_access_token raises NotImplementedError
        with pytest.raises(NotImplementedError) as exc_info:
            await handler.refresh_access_token("test_refresh_token")

        assert "does not support token refresh" in str(exc_info.value)
        assert "MinimalOAuthHandler" in str(exc_info.value)

    async def test_oauth_server_handles_not_implemented_gracefully(self) -> None:
        """Test that OAuth server gracefully handles providers without refresh support."""
        from unittest.mock import MagicMock, patch

        from mxcp.sdk.auth._types import ExternalUserInfo, StateMeta
        from mxcp.sdk.auth.base import GeneralOAuthAuthorizationServer
        from mxcp.sdk.auth.persistence import PersistedAccessToken

        # Create a handler that doesn't support refresh (raises NotImplementedError)
        class NoRefreshHandler(ExternalOAuthHandler):
            """Handler that doesn't support token refresh."""

            def get_authorize_url(self, client_id: str, params: Any) -> str:
                return "https://example.com/authorize"

            async def exchange_code(self, code: str, state: str) -> tuple[Any, Any]:
                user_info = ExternalUserInfo(
                    id="test_user",
                    scopes=[],
                    raw_token="test_token",
                    provider="test",
                )
                meta = StateMeta(
                    redirect_uri="https://example.com/callback",
                    code_challenge="",
                    redirect_uri_provided_explicitly=False,
                    client_id="test_client",
                )
                return user_info, meta

            @property
            def callback_path(self) -> str:
                return "/test/callback"

            async def on_callback(self, request: Any, provider: Any) -> Any:
                return None

            async def get_user_context(self, token: str) -> UserContext:
                return UserContext(
                    user_id="test_user",
                    username="testuser",
                    email="test@example.com",
                    provider="test",
                )

        handler = NoRefreshHandler()
        server = GeneralOAuthAuthorizationServer(handler)

        # Mock the persistence to return a token with a refresh token
        mock_persistence = MagicMock()
        mock_persisted_token = PersistedAccessToken(
            token="mcp_test_token",
            client_id="test_client",
            external_token="external_token",
            refresh_token="refresh_token_123",
            scopes=["read"],
            expires_at=None,
            created_at=1234567890.0,
        )
        mock_persistence.load_token = AsyncMock(return_value=mock_persisted_token)
        server.persistence = mock_persistence

        # Set up the token mapping
        server._token_mapping["mcp_test_token"] = "external_token"

        # Call refresh_external_token - should return None gracefully
        result = await server.refresh_external_token("mcp_test_token")

        # Should return None (not crash) when provider doesn't support refresh
        assert result is None


class TestRefreshTokenResponse:
    """Test cases for RefreshTokenResponse Pydantic model."""

    def test_refresh_token_response_validation(self) -> None:
        """Test that RefreshTokenResponse validates correctly."""
        from mxcp.sdk.auth._types import RefreshTokenResponse

        # Valid response with all fields
        response = RefreshTokenResponse(
            access_token="new_access_token",
            token_type="Bearer",
            expires_in=3600,
            refresh_token="new_refresh_token",
            scope="read write",
        )

        assert response.access_token == "new_access_token"
        assert response.token_type == "Bearer"
        assert response.expires_in == 3600
        assert response.refresh_token == "new_refresh_token"
        assert response.scope == "read write"

    def test_refresh_token_response_minimal(self) -> None:
        """Test that RefreshTokenResponse works with minimal required fields."""
        from mxcp.sdk.auth._types import RefreshTokenResponse

        # Only access_token is required
        response = RefreshTokenResponse(access_token="new_access_token")

        assert response.access_token == "new_access_token"
        assert response.token_type == "Bearer"  # Default value
        assert response.expires_in is None
        assert response.refresh_token is None
        assert response.scope is None

    def test_refresh_token_response_from_dict(self) -> None:
        """Test that RefreshTokenResponse can be constructed from OAuth provider response."""
        from mxcp.sdk.auth._types import RefreshTokenResponse

        # Simulate a typical OAuth provider response
        provider_response = {
            "access_token": "ya29.a0AfB_byC...",
            "expires_in": 3599,
            "token_type": "Bearer",
            "scope": "openid profile email",
            # refresh_token might not be present in some responses
        }

        response = RefreshTokenResponse(**provider_response)

        assert response.access_token == "ya29.a0AfB_byC..."
        assert response.expires_in == 3599
        assert response.token_type == "Bearer"
        assert response.scope == "openid profile email"
        assert response.refresh_token is None  # Not in provider response

    def test_refresh_token_response_extra_fields(self) -> None:
        """Test that RefreshTokenResponse allows extra provider-specific fields."""
        from mxcp.sdk.auth._types import RefreshTokenResponse

        # Some providers may include additional fields
        response = RefreshTokenResponse(
            access_token="token",
            provider_specific_field="some_value",
            another_field=123,
        )

        assert response.access_token == "token"
        # Extra fields should be allowed (model_config = {"extra": "allow"})

    def test_refresh_token_response_validation_error(self) -> None:
        """Test that RefreshTokenResponse raises validation error for invalid data."""
        from pydantic import ValidationError

        from mxcp.sdk.auth._types import RefreshTokenResponse

        # Missing required access_token field
        with pytest.raises(ValidationError) as exc_info:
            RefreshTokenResponse()

        assert "access_token" in str(exc_info.value)
