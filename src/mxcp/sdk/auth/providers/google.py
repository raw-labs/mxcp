"""Google OAuth ProviderAdapter implementation for issuer-mode auth."""

from __future__ import annotations

import logging
import time
from collections.abc import Mapping, Sequence
from typing import Any
from urllib.parse import urlencode

from mcp.shared._httpx_utils import create_mcp_http_client
from pydantic import ConfigDict, ValidationError

from mxcp.sdk.models import SdkBaseModel

from ..contracts import GrantResult, ProviderAdapter, ProviderError, UserInfo
from ..models import GoogleAuthConfigModel, HttpTransportConfigModel
from ..url_utils import URLBuilder

logger = logging.getLogger(__name__)


class _GoogleTokenResponse(SdkBaseModel):
    """Minimal token endpoint response (successful or error)."""

    model_config = ConfigDict(extra="ignore", frozen=True)

    access_token: str | None = None
    refresh_token: str | None = None
    expires_in: float | None = None
    scope: str | None = None
    token_type: str | None = None

    error: str | None = None
    error_description: str | None = None


class _GoogleUserInfoResponse(SdkBaseModel):
    """Minimal userinfo response used to normalize UserInfo."""

    model_config = ConfigDict(extra="ignore", frozen=True)

    sub: str | None = None
    id: str | None = None
    email: str | None = None
    name: str | None = None
    picture: str | None = None
    scope: str | None = None

    @property
    def resolved_user_id(self) -> str:
        return self.sub or self.id or ""


class GoogleProviderAdapter(ProviderAdapter):
    """Google OAuth ProviderAdapter that uses real HTTP calls."""

    provider_name = "google"

    def __init__(
        self,
        google_config: GoogleAuthConfigModel,
        transport_config: HttpTransportConfigModel | None = None,
        *,
        host: str = "localhost",
        port: int = 8000,
    ):
        self.client_id = google_config.client_id
        self.client_secret = google_config.client_secret
        self.auth_url = google_config.auth_url
        self.token_url = google_config.token_url
        self.scope = (
            google_config.scope
            or "https://www.googleapis.com/auth/calendar.readonly openid profile email"
        )
        self._callback_path = google_config.callback_path
        self.host = host
        self.port = port
        self.url_builder = URLBuilder(transport_config)

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
        scope_str = " ".join(scopes) if scopes else self.scope
        params = [
            ("client_id", self.client_id),
            ("redirect_uri", redirect_uri),
            ("response_type", "code"),
            ("scope", scope_str),
            ("state", state),
            ("access_type", "offline"),
            ("prompt", "consent"),
        ]
        if code_challenge:
            params.append(("code_challenge", code_challenge))
        if code_challenge_method:
            params.append(("code_challenge_method", code_challenge_method))
        if extra_params:
            params.extend(extra_params.items())
        query_string = urlencode(params, doseq=True)
        return f"{self.auth_url}?{query_string}"

    async def exchange_code(
        self,
        *,
        code: str,
        redirect_uri: str,
        code_verifier: str | None = None,
        scopes: Sequence[str] | None = None,
    ) -> GrantResult:
        payload = {
            "grant_type": "authorization_code",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "code": code,
            "redirect_uri": redirect_uri,
        }
        if code_verifier:
            payload["code_verifier"] = code_verifier

        async with create_mcp_http_client() as client:
            resp = await client.post(
                self.token_url,
                data=payload,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )

        if resp.status_code != 200:
            description = ""
            try:
                description = resp.text
            except Exception:
                description = "Unknown error"
            raise ProviderError("invalid_grant", description, status_code=resp.status_code)

        data: dict[str, Any] = resp.json()
        try:
            token = _GoogleTokenResponse.model_validate(data)
        except ValidationError as exc:
            raise ProviderError(
                "invalid_grant",
                "Invalid token response payload",
                status_code=resp.status_code,
            ) from exc

        if token.error is not None:
            raise ProviderError(
                token.error or "invalid_grant",
                token.error_description or "Failed to exchange code",
                status_code=resp.status_code,
            )

        access_token = token.access_token
        refresh_token = token.refresh_token
        expires_in = token.expires_in

        if not access_token:
            raise ProviderError("invalid_grant", "No access_token in response", status_code=400)

        user_profile = await self._fetch_user_profile(access_token)
        user_scopes = list(scopes) if scopes is not None else []
        expires_at = time.time() + float(expires_in) if expires_in else None

        token_type = token.token_type if token.token_type is not None else "Bearer"
        return GrantResult(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_at=expires_at,
            provider_scopes_granted=user_scopes or (token.scope.split() if token.scope else []),
            raw_profile=user_profile,
            token_type=token_type,
        )

    async def refresh_token(
        self, *, refresh_token: str, scopes: Sequence[str] | None = None
    ) -> GrantResult:
        payload = {
            "grant_type": "refresh_token",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "refresh_token": refresh_token,
        }
        if scopes:
            payload["scope"] = " ".join(scopes)

        async with create_mcp_http_client() as client:
            resp = await client.post(
                self.token_url,
                data=payload,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )

        if resp.status_code != 200:
            description = ""
            try:
                description = resp.text
            except Exception:
                description = "Unknown error"
            raise ProviderError("invalid_grant", description, status_code=resp.status_code)

        data: dict[str, Any] = resp.json()
        try:
            token = _GoogleTokenResponse.model_validate(data)
        except ValidationError as exc:
            raise ProviderError(
                "invalid_grant",
                "Invalid refresh response payload",
                status_code=resp.status_code,
            ) from exc

        if token.error is not None:
            raise ProviderError(
                token.error or "invalid_grant",
                token.error_description or "Failed to refresh token",
                status_code=resp.status_code,
            )

        access_token = token.access_token
        expires_in = token.expires_in
        if not access_token:
            raise ProviderError("invalid_grant", "No access_token in refresh response", 400)

        granted_scopes = (token.scope.split() if token.scope else []) or list(scopes or [])
        expires_at = time.time() + float(expires_in) if expires_in else None

        token_type = token.token_type if token.token_type is not None else "Bearer"
        return GrantResult(
            access_token=access_token,
            refresh_token=token.refresh_token if token.refresh_token is not None else refresh_token,
            expires_at=expires_at,
            provider_scopes_granted=granted_scopes,
            raw_profile=None,
            token_type=token_type,
        )

    async def fetch_user_info(self, *, access_token: str) -> UserInfo:
        profile = await self._fetch_user_profile(access_token)
        try:
            parsed = _GoogleUserInfoResponse.model_validate(profile)
        except ValidationError as exc:
            raise ProviderError(
                "invalid_token",
                "Google profile response was invalid",
                status_code=400,
            ) from exc

        user_id = parsed.resolved_user_id
        if not user_id:
            raise ProviderError("invalid_token", "Google profile missing id", status_code=400)

        email = parsed.email
        username = (email.split("@")[0] if email else user_id) or user_id

        return UserInfo(
            provider=self.provider_name,
            user_id=user_id,
            username=username,
            email=email,
            name=parsed.name,
            avatar_url=parsed.picture,
            raw_profile=profile,
            provider_scopes_granted=parsed.scope.split() if parsed.scope else None,
        )

    async def revoke_token(self, *, token: str, token_type_hint: str | None = None) -> bool:
        async with create_mcp_http_client() as client:
            resp = await client.post(
                "https://oauth2.googleapis.com/revoke",
                params={"token": token},
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
        if resp.status_code in {200, 400}:
            # 400 for invalid token per Google docs; treat as already revoked
            return True
        raise ProviderError("invalid_token", f"Failed to revoke token: {resp.status_code}", 400)

    # ── helpers ──────────────────────────────────────────────────────────────
    def build_callback_url(self) -> str:
        """Public helper to build callback URL for router registration."""
        return self.url_builder.build_callback_url(
            self._callback_path, host=self.host, port=self.port
        )

    @property
    def callback_path(self) -> str:
        return self._callback_path

    async def _fetch_user_profile(self, token: str) -> dict[str, Any]:
        async with create_mcp_http_client() as client:
            resp = await client.get(
                "https://www.googleapis.com/oauth2/v2/userinfo",
                headers={"Authorization": f"Bearer {token}"},
            )

        if resp.status_code != 200:
            description = ""
            try:
                description = resp.text
            except Exception:
                description = "Unknown error"
            raise ProviderError(
                "invalid_token",
                f"Google UserInfo failed: {description}",
                status_code=resp.status_code,
            )

        payload: dict[str, Any] = resp.json()
        try:
            _GoogleUserInfoResponse.model_validate(payload)
        except ValidationError as exc:
            raise ProviderError(
                "invalid_token",
                "Invalid userinfo payload",
                status_code=resp.status_code,
            ) from exc
        return payload
