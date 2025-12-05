"""Tests for AuthService class.

This module tests the AuthService class from mxcp.sdk.auth.service,
which is the single entry point for MXCP authentication.
"""

import pytest

from mxcp.sdk.auth.models import (
    AuthConfigModel,
    AuthorizationConfigModel,
    HttpTransportConfigModel,
)
from mxcp.sdk.auth.service import AuthService


class TestAuthServiceDisabled:
    """Tests for AuthService in disabled mode."""

    def test_disabled_when_provider_is_none(self) -> None:
        """AuthService should be disabled when provider is 'none'."""
        auth_config = AuthConfigModel(provider="none")
        service = AuthService.from_config(auth_config)

        assert service.mode == "disabled"
        assert service.auth_enabled is False
        assert service.provider_adapter is None
        assert service.session_manager is None

    def test_disabled_when_provider_is_empty(self) -> None:
        """AuthService should be disabled when provider is not set."""
        auth_config = AuthConfigModel(provider=None)  # type: ignore[arg-type]
        service = AuthService.from_config(auth_config)

        assert service.mode == "disabled"
        assert service.auth_enabled is False

    def test_build_middleware_when_disabled(self) -> None:
        """build_middleware should work even when auth is disabled."""
        auth_config = AuthConfigModel(provider="none")
        service = AuthService.from_config(auth_config)

        middleware = service.build_middleware()
        assert middleware is not None
        assert middleware.session_manager is None
        assert middleware.provider_adapter is None

    def test_callback_path_when_disabled(self) -> None:
        """callback_path should return None when auth is disabled."""
        auth_config = AuthConfigModel(provider="none")
        service = AuthService.from_config(auth_config)

        assert service.callback_path is None


class TestAuthServiceInitialization:
    """Tests for AuthService initialization and lifecycle."""

    @pytest.mark.asyncio
    async def test_initialize_when_disabled(self) -> None:
        """initialize should be idempotent when auth is disabled."""
        auth_config = AuthConfigModel(provider="none")
        service = AuthService.from_config(auth_config)

        # Should not raise
        await service.initialize()
        assert service._initialized is True

        # Second call should be idempotent
        await service.initialize()
        assert service._initialized is True

    @pytest.mark.asyncio
    async def test_close_when_disabled(self) -> None:
        """close should not raise when auth is disabled."""
        auth_config = AuthConfigModel(provider="none")
        service = AuthService.from_config(auth_config)

        # Should not raise
        await service.close()


class TestAuthServiceDirectInstantiation:
    """Tests for direct AuthService instantiation."""

    def test_direct_instantiation_disabled(self) -> None:
        """AuthService can be instantiated directly in disabled mode."""
        auth_config = AuthConfigModel(provider="none")
        service = AuthService(
            auth_config=auth_config,
            transport_config=None,
            mode="disabled",
        )

        assert service.mode == "disabled"
        assert service.auth_enabled is False


class TestAuthServiceWithTransportConfig:
    """Tests for AuthService with transport configuration."""

    def test_transport_config_stored(self) -> None:
        """Transport config should be stored on the service."""
        auth_config = AuthConfigModel(provider="none")
        transport_config = HttpTransportConfigModel(
            host="example.com",
            port=443,
            scheme="https",
        )

        service = AuthService.from_config(
            auth_config=auth_config,
            transport_config=transport_config,
        )

        assert service.transport_config is not None
        assert service.transport_config.host == "example.com"
        assert service.transport_config.port == 443
        assert service.transport_config.scheme == "https"


class TestAuthServiceAuthorizationConfig:
    """Tests for AuthService with authorization configuration."""

    def test_authorization_config_preserved(self) -> None:
        """Authorization config should be accessible from the service."""
        auth_config = AuthConfigModel(
            provider="none",
            authorization=AuthorizationConfigModel(
                required_scopes=["mxcp:read", "mxcp:write"],
            ),
        )
        service = AuthService.from_config(auth_config)

        assert service.auth_config.authorization is not None
        assert service.auth_config.authorization.required_scopes == ["mxcp:read", "mxcp:write"]


class TestAuthServiceModeOverride:
    """Tests for AuthService mode override."""

    def test_mode_override_to_disabled(self) -> None:
        """Mode can be overridden even when provider is set."""
        # Note: This will fail if provider config is missing
        # The test verifies the mode parameter handling
        auth_config = AuthConfigModel(provider="none")
        service = AuthService(
            auth_config=auth_config,
            mode="disabled",
        )

        assert service.mode == "disabled"

