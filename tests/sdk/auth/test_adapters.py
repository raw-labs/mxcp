"""Tests for provider adapters.

This module tests the provider adapter implementations from mxcp.sdk.auth.adapters.
Tests use mocks to avoid actual network calls to identity providers.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mxcp.sdk.auth.adapter import GrantResult, ProviderError, UserInfo
from mxcp.sdk.auth.adapters.google import GoogleAdapter
from mxcp.sdk.auth.models import GoogleAuthConfigModel


class TestGoogleAdapter:
    """Tests for GoogleAdapter."""

    @pytest.fixture
    def google_config(self) -> GoogleAuthConfigModel:
        """Create a Google config for testing."""
        return GoogleAuthConfigModel(
            client_id="test-client-id",
            client_secret="test-client-secret",
            scope="openid email profile",
            callback_path="/auth/callback/google",
            auth_url="https://accounts.google.com/o/oauth2/v2/auth",
            token_url="https://oauth2.googleapis.com/token",
        )

    @pytest.fixture
    def adapter(self, google_config: GoogleAuthConfigModel) -> GoogleAdapter:
        """Create a GoogleAdapter for testing."""
        return GoogleAdapter(config=google_config)

    def test_provider_name(self, adapter: GoogleAdapter) -> None:
        """GoogleAdapter should return 'google' as provider name."""
        assert adapter.provider_name == "google"

    @pytest.mark.asyncio
    async def test_build_authorize_url(self, adapter: GoogleAdapter) -> None:
        """GoogleAdapter should build proper authorize URL."""
        url = await adapter.build_authorize_url(
            redirect_uri="http://localhost:8000/auth/callback",
            state="test-state-123",
        )

        assert "accounts.google.com" in url
        assert "client_id=test-client-id" in url
        assert "redirect_uri=http%3A%2F%2Flocalhost%3A8000%2Fauth%2Fcallback" in url
        assert "state=test-state-123" in url
        assert "response_type=code" in url
        assert "scope=" in url

    @pytest.mark.asyncio
    async def test_build_authorize_url_with_pkce(self, adapter: GoogleAdapter) -> None:
        """GoogleAdapter should include PKCE parameters when provided."""
        url = await adapter.build_authorize_url(
            redirect_uri="http://localhost:8000/auth/callback",
            state="test-state-123",
            code_challenge="test-challenge",
            code_challenge_method="S256",
        )

        assert "code_challenge=test-challenge" in url
        assert "code_challenge_method=S256" in url

    @pytest.mark.asyncio
    async def test_build_authorize_url_with_custom_scopes(
        self, adapter: GoogleAdapter
    ) -> None:
        """GoogleAdapter should use custom scopes when provided."""
        url = await adapter.build_authorize_url(
            redirect_uri="http://localhost:8000/auth/callback",
            state="test-state-123",
            scopes=["openid", "custom-scope"],
        )

        assert "scope=openid+custom-scope" in url

    @pytest.mark.asyncio
    async def test_exchange_code_success(self, adapter: GoogleAdapter) -> None:
        """GoogleAdapter should exchange code for tokens successfully."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "google-access-token",
            "refresh_token": "google-refresh-token",
            "expires_in": 3600,
            "token_type": "Bearer",
            "scope": "openid email profile",
        }

        with patch(
            "mxcp.sdk.auth.adapters.google.create_mcp_http_client"
        ) as mock_client:
            mock_http = AsyncMock()
            mock_http.post = AsyncMock(return_value=mock_response)
            mock_http.__aenter__ = AsyncMock(return_value=mock_http)
            mock_http.__aexit__ = AsyncMock(return_value=None)
            mock_client.return_value = mock_http

            result = await adapter.exchange_code(
                code="test-auth-code",
                redirect_uri="http://localhost:8000/auth/callback",
            )

        assert isinstance(result, GrantResult)
        assert result.access_token == "google-access-token"
        assert result.refresh_token == "google-refresh-token"
        assert result.expires_in == 3600

    @pytest.mark.asyncio
    async def test_exchange_code_error(self, adapter: GoogleAdapter) -> None:
        """GoogleAdapter should raise ProviderError on exchange failure."""
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.json.return_value = {
            "error": "invalid_grant",
            "error_description": "Code has expired",
        }

        with patch(
            "mxcp.sdk.auth.adapters.google.create_mcp_http_client"
        ) as mock_client:
            mock_http = AsyncMock()
            mock_http.post = AsyncMock(return_value=mock_response)
            mock_http.__aenter__ = AsyncMock(return_value=mock_http)
            mock_http.__aexit__ = AsyncMock(return_value=None)
            mock_client.return_value = mock_http

            with pytest.raises(ProviderError) as exc_info:
                await adapter.exchange_code(
                    code="expired-code",
                    redirect_uri="http://localhost:8000/auth/callback",
                )

        assert exc_info.value.error == "invalid_grant"
        assert "expired" in (exc_info.value.error_description or "").lower()

    @pytest.mark.asyncio
    async def test_refresh_token_success(self, adapter: GoogleAdapter) -> None:
        """GoogleAdapter should refresh tokens successfully."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "new-access-token",
            "expires_in": 3600,
            "token_type": "Bearer",
        }

        with patch(
            "mxcp.sdk.auth.adapters.google.create_mcp_http_client"
        ) as mock_client:
            mock_http = AsyncMock()
            mock_http.post = AsyncMock(return_value=mock_response)
            mock_http.__aenter__ = AsyncMock(return_value=mock_http)
            mock_http.__aexit__ = AsyncMock(return_value=None)
            mock_client.return_value = mock_http

            result = await adapter.refresh_token(refresh_token="test-refresh-token")

        assert isinstance(result, GrantResult)
        assert result.access_token == "new-access-token"
        # Should preserve original refresh token if not returned
        assert result.refresh_token == "test-refresh-token"

    @pytest.mark.asyncio
    async def test_fetch_user_info_success(self, adapter: GoogleAdapter) -> None:
        """GoogleAdapter should fetch user info successfully."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "sub": "12345",
            "email": "test@example.com",
            "name": "Test User",
            "picture": "https://example.com/avatar.jpg",
        }

        with patch(
            "mxcp.sdk.auth.adapters.google.create_mcp_http_client"
        ) as mock_client:
            mock_http = AsyncMock()
            mock_http.get = AsyncMock(return_value=mock_response)
            mock_http.__aenter__ = AsyncMock(return_value=mock_http)
            mock_http.__aexit__ = AsyncMock(return_value=None)
            mock_client.return_value = mock_http

            result = await adapter.fetch_user_info(access_token="test-access-token")

        assert isinstance(result, UserInfo)
        assert result.user_id == "12345"
        assert result.email == "test@example.com"
        assert result.name == "Test User"
        assert result.username == "test"  # Extracted from email

    @pytest.mark.asyncio
    async def test_fetch_user_info_error(self, adapter: GoogleAdapter) -> None:
        """GoogleAdapter should raise ProviderError on user info failure."""
        mock_response = MagicMock()
        mock_response.status_code = 401

        with patch(
            "mxcp.sdk.auth.adapters.google.create_mcp_http_client"
        ) as mock_client:
            mock_http = AsyncMock()
            mock_http.get = AsyncMock(return_value=mock_response)
            mock_http.__aenter__ = AsyncMock(return_value=mock_http)
            mock_http.__aexit__ = AsyncMock(return_value=None)
            mock_client.return_value = mock_http

            with pytest.raises(ProviderError) as exc_info:
                await adapter.fetch_user_info(access_token="invalid-token")

        assert exc_info.value.error == "userinfo_failed"
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_revoke_token_success(self, adapter: GoogleAdapter) -> None:
        """GoogleAdapter should revoke tokens successfully."""
        mock_response = MagicMock()
        mock_response.status_code = 200

        with patch(
            "mxcp.sdk.auth.adapters.google.create_mcp_http_client"
        ) as mock_client:
            mock_http = AsyncMock()
            mock_http.post = AsyncMock(return_value=mock_response)
            mock_http.__aenter__ = AsyncMock(return_value=mock_http)
            mock_http.__aexit__ = AsyncMock(return_value=None)
            mock_client.return_value = mock_http

            result = await adapter.revoke_token(token="test-token")

        assert result is True

    @pytest.mark.asyncio
    async def test_revoke_token_failure(self, adapter: GoogleAdapter) -> None:
        """GoogleAdapter should return False on revoke failure."""
        mock_response = MagicMock()
        mock_response.status_code = 400

        with patch(
            "mxcp.sdk.auth.adapters.google.create_mcp_http_client"
        ) as mock_client:
            mock_http = AsyncMock()
            mock_http.post = AsyncMock(return_value=mock_response)
            mock_http.__aenter__ = AsyncMock(return_value=mock_http)
            mock_http.__aexit__ = AsyncMock(return_value=None)
            mock_client.return_value = mock_http

            result = await adapter.revoke_token(token="invalid-token")

        assert result is False


class TestGrantResult:
    """Tests for GrantResult dataclass."""

    def test_grant_result_minimal(self) -> None:
        """GrantResult should work with just access_token."""
        result = GrantResult(access_token="test-token")

        assert result.access_token == "test-token"
        assert result.refresh_token is None
        assert result.expires_in is None
        assert result.token_type == "Bearer"

    def test_grant_result_full(self) -> None:
        """GrantResult should store all fields."""
        result = GrantResult(
            access_token="access",
            refresh_token="refresh",
            expires_in=3600,
            token_type="Bearer",
            scope="openid email",
            id_token="id-token",
            user_id="user-123",
            raw_response={"custom": "data"},
        )

        assert result.access_token == "access"
        assert result.refresh_token == "refresh"
        assert result.expires_in == 3600
        assert result.scope == "openid email"
        assert result.id_token == "id-token"
        assert result.user_id == "user-123"
        assert result.raw_response == {"custom": "data"}


class TestUserInfo:
    """Tests for UserInfo dataclass."""

    def test_user_info_minimal(self) -> None:
        """UserInfo should work with just user_id."""
        info = UserInfo(user_id="user-123")

        assert info.user_id == "user-123"
        assert info.username is None
        assert info.email is None

    def test_user_info_full(self) -> None:
        """UserInfo should store all fields."""
        info = UserInfo(
            user_id="user-123",
            username="testuser",
            email="test@example.com",
            name="Test User",
            avatar_url="https://example.com/avatar.jpg",
            raw_profile={"custom": "profile"},
        )

        assert info.user_id == "user-123"
        assert info.username == "testuser"
        assert info.email == "test@example.com"
        assert info.name == "Test User"
        assert info.avatar_url == "https://example.com/avatar.jpg"
        assert info.raw_profile == {"custom": "profile"}


class TestProviderError:
    """Tests for ProviderError exception."""

    def test_provider_error_minimal(self) -> None:
        """ProviderError should work with just error code."""
        error = ProviderError(error="invalid_request")

        assert error.error == "invalid_request"
        assert error.error_description is None
        assert str(error) == "invalid_request"

    def test_provider_error_with_description(self) -> None:
        """ProviderError should include description in message."""
        error = ProviderError(
            error="invalid_grant",
            error_description="Code has expired",
            status_code=400,
        )

        assert error.error == "invalid_grant"
        assert error.error_description == "Code has expired"
        assert error.status_code == 400
        assert str(error) == "invalid_grant: Code has expired"

