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
from ..models import GoogleAuthConfigModel

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
    # OAuth: Google supports PKCE with S256 for the authorization code flow.
    pkce_methods_supported = ["S256"]

    def __init__(
        self,
        google_config: GoogleAuthConfigModel,
    ):
        self.client_id = google_config.client_id
        self.client_secret = google_config.client_secret
        self.auth_url = google_config.auth_url
        self.token_url = google_config.token_url
        # OAuth 2.0 provider scope string to request at Google's /authorize endpoint.
        # This is required by config (no SDK-side defaults) to avoid accidental
        # privilege expansion and to keep consent UX predictable.
        self.scope = google_config.scope
        self._callback_path = google_config.callback_path

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
        # `scopes` here are upstream *provider scopes* (Google OAuth scopes), not
        # MXCP permissions.
        #
        # Issuer-mode policy: OAuth client-requested scopes (from MCP clients) must not
        # influence what we request from the upstream IdP. The set of provider scopes
        # comes from server/provider configuration and will later be mapped to MXCP
        # permissions.
        #
        # If `scopes` is empty, we fall back to the configured provider scope string.
        scope_str = " ".join(scopes) if scopes else self.scope
        params = [
            ("client_id", self.client_id),
            ("redirect_uri", redirect_uri),
            ("response_type", "code"),
            ("scope", scope_str),
            ("state", state),
            # Google-specific: `access_type=offline` requests a refresh token.
            #
            # Note: Google may return a refresh token only on the first consent or when
            # forcing consent via `prompt=consent` (and other account/app-specific rules).
            ("access_type", "offline"),
            # Google-specific: `prompt=consent` forces a consent screen. This improves
            # the likelihood of receiving a refresh token (offline access) but may
            # increase user friction; keep this explicit.
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
        scopes: Sequence[str],
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

        token = await self._request_token(payload=payload, context="exchange_code")

        access_token = token.access_token
        refresh_token = token.refresh_token
        expires_in = token.expires_in

        if not access_token:
            raise ProviderError("invalid_grant", "No access_token in response", status_code=400)

        expires_at = time.time() + float(expires_in) if expires_in is not None else None

        token_type = token.token_type if token.token_type is not None else "Bearer"
        # OAuth scope semantics:
        # - The token endpoint `scope` field is OPTIONAL. When absent, it generally means
        #   the granted scopes are identical to those requested at the authorize step.
        # - Do NOT interpret missing `scope` as “zero scopes”.
        #
        # In issuer-mode, the `scopes` argument is expected to reflect the provider
        # scopes used at /authorize (from configuration), not scopes supplied by the
        # OAuth client.
        granted_scopes = token.scope.split() if token.scope else list(scopes)
        return GrantResult(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_at=expires_at,
            provider_scopes_granted=granted_scopes,
            token_type=token_type,
        )

    async def refresh_token(self, *, refresh_token: str, scopes: Sequence[str]) -> GrantResult:
        payload = {
            "grant_type": "refresh_token",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "refresh_token": refresh_token,
        }
        if scopes:
            payload["scope"] = " ".join(scopes)

        token = await self._request_token(payload=payload, context="refresh_token")

        access_token = token.access_token
        expires_in = token.expires_in
        if not access_token:
            raise ProviderError("invalid_grant", "No access_token in refresh response", 400)

        granted_scopes = (token.scope.split() if token.scope else []) or list(scopes)
        expires_at = time.time() + float(expires_in) if expires_in is not None else None

        token_type = token.token_type if token.token_type is not None else "Bearer"
        return GrantResult(
            access_token=access_token,
            refresh_token=token.refresh_token if token.refresh_token is not None else refresh_token,
            expires_at=expires_at,
            provider_scopes_granted=granted_scopes,
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
            provider_scopes_granted=parsed.scope.split() if parsed.scope else [],
        )

    # ── helpers ──────────────────────────────────────────────────────────────
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
            logger.warning(
                "Google userinfo endpoint returned non-200",
                extra={
                    "provider": self.provider_name,
                    "endpoint": "userinfo",
                    "status_code": resp.status_code,
                },
            )
            raise ProviderError(
                "invalid_token",
                "Google userinfo request failed",
                status_code=resp.status_code,
            )

        try:
            payload = resp.json()
        except Exception as exc:
            logger.warning(
                "Google userinfo endpoint returned invalid JSON",
                extra={
                    "provider": self.provider_name,
                    "endpoint": "userinfo",
                    "status_code": resp.status_code,
                },
            )
            raise ProviderError(
                "invalid_token",
                "Google userinfo response was invalid",
                status_code=resp.status_code,
            ) from exc

        if not isinstance(payload, dict):
            logger.warning(
                "Google userinfo endpoint returned non-object JSON",
                extra={
                    "provider": self.provider_name,
                    "endpoint": "userinfo",
                    "status_code": resp.status_code,
                },
            )
            raise ProviderError(
                "invalid_token",
                "Google userinfo response was invalid",
                status_code=resp.status_code,
            )
        return payload

    async def _request_token(
        self,
        *,
        payload: Mapping[str, str],
        context: str,
    ) -> _GoogleTokenResponse:
        """Request tokens from Google's token endpoint.

        OAuth notes:
        - The token endpoint MAY return structured OAuth errors (`error`,
          `error_description`) in either 4xx responses or (rarely) 200 responses.
        - We log only the OAuth error code (not description/body) to avoid leaking
          sensitive information.
        """
        async with create_mcp_http_client() as client:
            resp = await client.post(
                self.token_url,
                data=payload,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
        return self._parse_token_response(resp, context=context)

    def _parse_token_response(self, resp: Any, *, context: str) -> _GoogleTokenResponse:
        if resp.status_code != 200:
            error_code = self._try_extract_oauth_error_code(resp)
            logger.warning(
                "Google token endpoint returned non-200",
                extra={
                    "provider": self.provider_name,
                    "endpoint": "token",
                    "context": context,
                    "status_code": resp.status_code,
                    "provider_error": error_code,
                },
            )
            raise ProviderError(
                error_code or "invalid_grant",
                "Google token request failed",
                status_code=resp.status_code,
            )

        try:
            data = resp.json()
        except Exception as exc:
            logger.warning(
                "Google token endpoint returned invalid JSON",
                extra={
                    "provider": self.provider_name,
                    "endpoint": "token",
                    "context": context,
                    "status_code": resp.status_code,
                },
            )
            raise ProviderError(
                "invalid_grant",
                "Invalid token response payload",
                status_code=resp.status_code,
            ) from exc

        if not isinstance(data, dict):
            logger.warning(
                "Google token endpoint returned non-object JSON",
                extra={
                    "provider": self.provider_name,
                    "endpoint": "token",
                    "context": context,
                    "status_code": resp.status_code,
                },
            )
            raise ProviderError(
                "invalid_grant",
                "Invalid token response payload",
                status_code=resp.status_code,
            )

        try:
            token = _GoogleTokenResponse.model_validate(data)
        except ValidationError as exc:
            raise ProviderError(
                "invalid_grant",
                "Invalid token response payload",
                status_code=resp.status_code,
            ) from exc

        if token.error is not None:
            # The token endpoint returned an OAuth error in a 200 response.
            logger.warning(
                "Google token endpoint returned OAuth error",
                extra={
                    "provider": self.provider_name,
                    "endpoint": "token",
                    "context": context,
                    "status_code": resp.status_code,
                    "provider_error": token.error,
                },
            )
            raise ProviderError(
                token.error or "invalid_grant",
                "Google token request failed",
                status_code=resp.status_code,
            )

        return token

    def _try_extract_oauth_error_code(self, resp: Any) -> str | None:
        """Best-effort extraction of OAuth `error` code from a response.

        We intentionally ignore `error_description` because it may contain
        sensitive details and should not be propagated into logs.
        """
        try:
            payload = resp.json()
        except Exception:
            return None
        if not isinstance(payload, dict):
            return None
        error = payload.get("error")
        return error if isinstance(error, str) and error else None
