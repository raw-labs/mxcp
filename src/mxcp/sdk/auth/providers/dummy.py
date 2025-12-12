"""Deterministic dummy provider for auth flow testing (no network calls)."""

from __future__ import annotations

import time
from collections.abc import Mapping, Sequence

from ..contracts import GrantResult, ProviderAdapter, ProviderError, UserInfo


class DummyProviderAdapter(ProviderAdapter):
    """In-process provider adapter used for tests and demos."""

    provider_name = "dummy"

    def __init__(
        self,
        *,
        expected_code: str = "TEST_CODE_OK",
        expected_code_verifier: str | None = None,
        issued_scopes: Sequence[str] | None = None,
    ):
        self.expected_code = expected_code
        self.expected_code_verifier = expected_code_verifier
        self.issued_scopes = list(issued_scopes) if issued_scopes is not None else ["dummy.read"]
        self._access_token = "DUMMY_ACCESS_TOKEN"
        self._refresh_token = "DUMMY_REFRESH_TOKEN"

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
        """Return a predictable URL that encodes state and redirect."""
        parts = [
            f"state={state}",
            f"redirect_uri={redirect_uri}",
            f"scope={' '.join(scopes)}",
        ]
        if code_challenge:
            parts.append(f"code_challenge={code_challenge}")
        if code_challenge_method:
            parts.append(f"code_challenge_method={code_challenge_method}")
        if extra_params:
            for key, value in extra_params.items():
                parts.append(f"{key}={value}")
        return "https://dummy.provider/authorize?" + "&".join(parts)

    async def exchange_code(
        self,
        *,
        code: str,
        redirect_uri: str,
        code_verifier: str | None = None,
        scopes: Sequence[str] | None = None,
    ) -> GrantResult:
        """Return fixed tokens when the expected code (and PKCE) are presented."""
        if code != self.expected_code:
            raise ProviderError("invalid_grant", "Unknown authorization code", status_code=400)

        if self.expected_code_verifier is not None and code_verifier != self.expected_code_verifier:
            raise ProviderError("invalid_grant", "PKCE verification failed", status_code=400)

        granted_scopes = list(scopes) if scopes is not None else list(self.issued_scopes)
        now = time.time()
        return GrantResult(
            access_token=self._access_token,
            refresh_token=self._refresh_token,
            expires_at=now + 3600,
            provider_scopes_granted=granted_scopes,
            raw_profile={"dummy": True},
        )

    async def refresh_token(
        self, *, refresh_token: str, scopes: Sequence[str] | None = None
    ) -> GrantResult:
        """Rotate the access token when a valid refresh token is supplied."""
        if refresh_token != self._refresh_token:
            raise ProviderError("invalid_grant", "Unknown refresh token", status_code=400)

        self._access_token = f"{self._access_token}_refreshed"
        granted_scopes = list(scopes) if scopes is not None else list(self.issued_scopes)
        now = time.time()
        return GrantResult(
            access_token=self._access_token,
            refresh_token=self._refresh_token,
            expires_at=now + 3600,
            provider_scopes_granted=granted_scopes,
            raw_profile={"dummy": True, "refreshed": True},
        )

    async def fetch_user_info(self, *, access_token: str) -> UserInfo:
        """Return a fixed user profile for recognized tokens."""
        if access_token != self._access_token:
            raise ProviderError("invalid_token", "Access token not recognized", status_code=401)

        return UserInfo(
            provider=self.provider_name,
            user_id="dummy-user",
            username="dummy-user",
            email="dummy@example.com",
            name="Dummy User",
            avatar_url=None,
            raw_profile={"provider": "dummy"},
            provider_scopes_granted=list(self.issued_scopes),
        )

    async def revoke_token(self, *, token: str, token_type_hint: str | None = None) -> bool:
        """Always report successful revocation."""
        if token not in {self._access_token, self._refresh_token}:
            raise ProviderError("invalid_token", "Token not recognized", status_code=400)
        return True
