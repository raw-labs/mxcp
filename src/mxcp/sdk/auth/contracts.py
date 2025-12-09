"""Contracts and shared types for the MXCP authentication stack."""

from __future__ import annotations

from typing import Any, Mapping, Protocol, Sequence, runtime_checkable

from mxcp.sdk.models import SdkBaseModel


class ProviderError(Exception):
    """Standardized provider error with HTTP-style status information."""

    def __init__(self, error: str, description: str | None = None, status_code: int = 400):
        super().__init__(description or error)
        self.error = error
        self.description = description
        self.status_code = status_code


class GrantResult(SdkBaseModel):
    """Result of exchanging or refreshing a grant with an IdP."""

    access_token: str
    refresh_token: str | None = None
    expires_at: float | None = None
    provider_scopes_granted: list[str] | None = None
    raw_profile: dict[str, Any] | None = None
    token_type: str = "Bearer"


class UserInfo(SdkBaseModel):
    """Normalized user information returned by providers."""

    provider: str
    user_id: str
    username: str
    email: str | None = None
    name: str | None = None
    avatar_url: str | None = None
    raw_profile: dict[str, Any] | None = None
    provider_scopes_granted: list[str] | None = None
    mxcp_scopes: list[str] | None = None


class Session(SdkBaseModel):
    """Session record kept by the auth service."""

    session_id: str
    provider: str
    user_info: UserInfo
    access_token: str
    refresh_token: str | None = None
    provider_access_token: str | None = None
    provider_refresh_token: str | None = None
    provider_expires_at: float | None = None
    expires_at: float | None = None
    issued_at: float | None = None
    scopes: list[str] | None = None


@runtime_checkable
class ProviderAdapter(Protocol):
    """Interface all provider adapters must implement."""

    provider_name: str

    def build_authorize_url(
        self,
        *,
        redirect_uri: str,
        state: str,
        scopes: Sequence[str],
        code_challenge: str | None = None,
        code_challenge_method: str | None = None,
        extra_params: Mapping[str, str] | None = None,
    ) -> str:
        """Construct the provider authorize URL using the MXCP callback."""

    async def exchange_code(
        self,
        *,
        code: str,
        redirect_uri: str,
        code_verifier: str | None = None,
        scopes: Sequence[str] | None = None,
    ) -> GrantResult:
        """Exchange an authorization code for provider tokens."""

    async def refresh_token(
        self, *, refresh_token: str, scopes: Sequence[str] | None = None
    ) -> GrantResult:
        """Refresh provider tokens."""

    async def fetch_user_info(self, *, access_token: str) -> UserInfo:
        """Fetch user information associated with a provider access token."""

    async def revoke_token(self, *, token: str, token_type_hint: str | None = None) -> bool:
        """Revoke a provider token if supported."""


class ScopeMapper(Protocol):
    """Placeholder for future scope mapping; implemented in later phases."""

    def map_scopes(self, user_info: UserInfo) -> list[str]: ...


__all__ = [
    "GrantResult",
    "ProviderAdapter",
    "ProviderError",
    "ScopeMapper",
    "Session",
    "UserInfo",
]
