"""Google OAuth ProviderAdapter implementation for issuer-mode auth."""

from __future__ import annotations

import logging
import time
from collections.abc import Mapping, Sequence
from typing import Any, cast
from urllib.parse import urlencode

from mcp.shared._httpx_utils import create_mcp_http_client

from ..contracts import GrantResult, ProviderAdapter, ProviderError, UserInfo
from ..models import GoogleAuthConfigModel, HttpTransportConfigModel
from ..url_utils import URLBuilder

logger = logging.getLogger(__name__)


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

        data = resp.json()
        if "error" in data:
            raise ProviderError(
                data.get("error", "invalid_grant"),
                data.get("error_description", "Failed to exchange code"),
                status_code=resp.status_code,
            )

        access_token = data.get("access_token")
        refresh_token = data.get("refresh_token")
        expires_in = data.get("expires_in")

        if not access_token:
            raise ProviderError("invalid_grant", "No access_token in response", status_code=400)

        user_profile = await self._fetch_user_profile(access_token)
        user_scopes = list(scopes) if scopes is not None else []
        expires_at = time.time() + float(expires_in) if expires_in else None

        return GrantResult(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_at=expires_at,
            provider_scopes_granted=user_scopes or data.get("scope", "").split(),
            raw_profile=user_profile,
            token_type=data.get("token_type", "Bearer"),
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

        data = resp.json()
        if "error" in data:
            raise ProviderError(
                data.get("error", "invalid_grant"),
                data.get("error_description", "Failed to refresh token"),
                status_code=resp.status_code,
            )

        access_token = data.get("access_token")
        expires_in = data.get("expires_in")
        if not access_token:
            raise ProviderError("invalid_grant", "No access_token in refresh response", 400)

        granted_scopes = data.get("scope", "").split() or list(scopes or [])
        expires_at = time.time() + float(expires_in) if expires_in else None

        return GrantResult(
            access_token=access_token,
            refresh_token=data.get("refresh_token", refresh_token),
            expires_at=expires_at,
            provider_scopes_granted=granted_scopes,
            raw_profile=None,
            token_type=data.get("token_type", "Bearer"),
        )

    async def fetch_user_info(self, *, access_token: str) -> UserInfo:
        profile = await self._fetch_user_profile(access_token)
        user_id = str(profile.get("sub") or profile.get("id") or "")
        if not user_id:
            raise ProviderError("invalid_token", "Google profile missing id", status_code=400)

        email = profile.get("email")
        username = (email.split("@")[0] if email else user_id) or user_id

        return UserInfo(
            provider=self.provider_name,
            user_id=user_id,
            username=username,
            email=email,
            name=profile.get("name"),
            avatar_url=profile.get("picture"),
            raw_profile=profile,
            provider_scopes_granted=profile.get("scope", "").split() or None,
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

        return cast(dict[str, Any], resp.json())
