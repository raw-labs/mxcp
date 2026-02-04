"""Contracts and shared types for the MXCP authentication stack.

This module defines the stable interfaces between:
- **Issuer orchestration** (MXCP) and **provider integrations** (IdP adapters)
- the rest of the SDK/server code that consumes normalized auth results

## Design boundaries (important)

- **Downstream OAuth** (MCP client ↔ MXCP): handled by the MCP auth framework.
  PKCE verification for the token endpoint is performed *upstream* of
  `mxcp.sdk.auth.auth_service.AuthService.exchange_token()`.

- **Upstream OAuth** (MXCP ↔ IdP): implemented by `ProviderAdapter` methods.
  Provider PKCE support is expressed via `ProviderAdapter.pkce_methods_supported`
  (capability, not configuration).

## Security invariants (“do not break”)

- Never log tokens, secrets, or PII in provider adapters or error paths.
- `ProviderError.error` should be a stable OAuth-style error code suitable for clients.
  Keep `description` high-level; do not propagate provider response bodies.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Protocol, runtime_checkable

from pydantic import Field

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
    refresh_expires_at: float | None = None
    provider_scopes_granted: list[str] = Field(default_factory=list)
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
    provider_scopes_granted: list[str] = Field(default_factory=list)
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
    access_expires_at: float | None = None
    refresh_expires_at: float | None = None
    issued_at: float | None = None


@runtime_checkable
class ProviderAdapter(Protocol):
    """Interface all provider adapters must implement."""

    provider_name: str
    # Upstream (MXCP ↔ IdP) PKCE capability.
    #
    # OAuth note: This is a provider capability, not user configuration. When empty,
    # AuthService should not attempt upstream PKCE. When it contains "S256",
    # AuthService may always enable upstream PKCE as defense-in-depth.
    pkce_methods_supported: Sequence[str]

    def build_authorize_url(
        self,
        *,
        redirect_uri: str,
        state: str,
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
        scopes: Sequence[str],
    ) -> GrantResult:
        """Exchange an authorization code for provider tokens."""

    async def refresh_token(self, *, refresh_token: str, scopes: Sequence[str]) -> GrantResult:
        """Refresh provider tokens."""

    async def fetch_user_info(self, *, access_token: str) -> UserInfo:
        """Fetch user information associated with a provider access token."""


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
