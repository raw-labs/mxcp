"""Atlassian OAuth ProviderAdapter implementation for issuer-mode auth."""

from __future__ import annotations

import logging
import time
from collections.abc import Mapping, Sequence
from typing import Any
from urllib.parse import urlencode

import httpx
from mcp.shared._httpx_utils import create_mcp_http_client
from pydantic import ConfigDict, ValidationError

from mxcp.sdk.models import SdkBaseModel

from ..contracts import GrantResult, ProviderAdapter, ProviderError, UserInfo
from ..models import AtlassianAuthConfigModel

logger = logging.getLogger(__name__)


class _AtlassianTokenResponse(SdkBaseModel):
    """Minimal token endpoint response (successful or error)."""

    model_config = ConfigDict(extra="ignore", frozen=True)

    access_token: str | None = None
    refresh_token: str | None = None
    expires_in: float | None = None
    scope: str | None = None
    token_type: str | None = None

    error: str | None = None
    error_description: str | None = None


class _AtlassianMeResponse(SdkBaseModel):
    """Minimal `/me` response used to normalize UserInfo."""

    model_config = ConfigDict(extra="ignore", frozen=True)

    account_id: str | None = None
    email: str | None = None
    name: str | None = None
    picture: str | None = None
    nickname: str | None = None
    scope: str | None = None


class AtlassianProviderAdapter(ProviderAdapter):
    """Atlassian OAuth ProviderAdapter that uses real HTTP calls."""

    provider_name = "atlassian"
    # OAuth: Atlassian 3LO supports PKCE with S256 for the authorization code flow.
    pkce_methods_supported = ["S256"]

    def __init__(self, atlassian_config: AtlassianAuthConfigModel):
        self.client_id = atlassian_config.client_id
        self.client_secret = atlassian_config.client_secret
        self.auth_url = atlassian_config.auth_url
        self.token_url = atlassian_config.token_url
        # OAuth 2.0 provider scope string to request at Atlassian's /authorize endpoint.
        # Intentionally required by config (no SDK-side defaults) to avoid accidental
        # privilege expansion and to keep consent UX predictable.
        self.scope = atlassian_config.scope
        self._callback_path = atlassian_config.callback_path

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
        # `scopes` are upstream provider scopes (Atlassian 3LO scopes), not MXCP
        # permissions.
        #
        # Issuer-mode policy: OAuth client-requested scopes (from MCP clients) must not
        # influence what we request from the upstream IdP. Provider scopes come from
        # server/provider configuration and will later be mapped to MXCP permissions.
        scope_str = " ".join(scopes) if scopes else self.scope

        params: list[tuple[str, str]] = [
            # Atlassian 3LO requires `audience=api.atlassian.com` so that the resulting
            # access token is valid for calling Atlassian APIs via api.atlassian.com.
            ("audience", "api.atlassian.com"),
            ("client_id", self.client_id),
            ("redirect_uri", redirect_uri),
            ("response_type", "code"),
            ("scope", scope_str),
            ("state", state),
            # Atlassian-specific: `prompt=consent` forces the consent screen. This may
            # affect refresh token issuance and re-consent behavior. Keep explicit.
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
        payload: dict[str, Any] = {
            "grant_type": "authorization_code",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "code": code,
            "redirect_uri": redirect_uri,
        }
        if code_verifier:
            # PKCE: include verifier when the authorize request used a challenge.
            payload["code_verifier"] = code_verifier

        token = await self._request_token(payload=payload, context="exchange_code")

        access_token = token.access_token
        refresh_token = token.refresh_token
        expires_in = token.expires_in
        if not access_token:
            raise ProviderError("invalid_grant", "No access_token in response", status_code=400)

        expires_at = time.time() + float(expires_in) if expires_in is not None else None

        # OAuth scope semantics:
        # - The token endpoint `scope` field is OPTIONAL. When absent, it generally means
        #   the granted scopes are identical to those requested at the authorize step.
        # - Do NOT interpret missing `scope` as “zero scopes”.
        granted_scopes = token.scope.split() if token.scope else list(scopes)
        token_type = token.token_type if token.token_type is not None else "Bearer"

        return GrantResult(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_at=expires_at,
            provider_scopes_granted=granted_scopes,
            token_type=token_type,
        )

    async def refresh_token(self, *, refresh_token: str, scopes: Sequence[str]) -> GrantResult:
        payload: dict[str, Any] = {
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

        expires_at = time.time() + float(expires_in) if expires_in is not None else None
        granted_scopes = (token.scope.split() if token.scope else []) or list(scopes)
        token_type = token.token_type if token.token_type is not None else "Bearer"

        return GrantResult(
            access_token=access_token,
            refresh_token=token.refresh_token if token.refresh_token is not None else refresh_token,
            expires_at=expires_at,
            provider_scopes_granted=granted_scopes,
            token_type=token_type,
        )

    async def fetch_user_info(self, *, access_token: str) -> UserInfo:
        profile = await self._fetch_me(access_token)
        try:
            parsed = _AtlassianMeResponse.model_validate(profile)
        except ValidationError as exc:
            raise ProviderError(
                "invalid_token",
                "Atlassian profile response was invalid",
                status_code=400,
            ) from exc

        user_id = parsed.account_id or ""
        if not user_id:
            raise ProviderError("invalid_token", "Atlassian profile missing account_id", 400)

        email = parsed.email
        username = parsed.nickname or (email.split("@")[0] if email else None) or user_id

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

    async def _fetch_me(self, token: str) -> dict[str, Any]:
        async with create_mcp_http_client() as client:
            try:
                resp = await client.get(
                    "https://api.atlassian.com/me",
                    headers={"Authorization": f"Bearer {token}"},
                )
            except httpx.RequestError as exc:
                logger.warning(
                    "Atlassian /me endpoint request failed",
                    extra={
                        "provider": self.provider_name,
                        "endpoint": "userinfo",
                        "error_type": exc.__class__.__name__,
                    },
                )
                raise ProviderError(
                    "temporarily_unavailable",
                    "Atlassian userinfo request failed",
                    status_code=503,
                ) from exc

        if resp.status_code != 200:
            logger.warning(
                "Atlassian /me endpoint returned non-200",
                extra={
                    "provider": self.provider_name,
                    "endpoint": "userinfo",
                    "status_code": resp.status_code,
                },
            )
            raise ProviderError(
                "invalid_token",
                "Atlassian userinfo request failed",
                status_code=resp.status_code,
            )

        try:
            payload = resp.json()
        except Exception as exc:
            logger.warning(
                "Atlassian /me endpoint returned invalid JSON",
                extra={
                    "provider": self.provider_name,
                    "endpoint": "userinfo",
                    "status_code": resp.status_code,
                },
            )
            raise ProviderError(
                "invalid_token",
                "Atlassian userinfo response was invalid",
                status_code=resp.status_code,
            ) from exc

        if not isinstance(payload, dict):
            logger.warning(
                "Atlassian /me endpoint returned non-object JSON",
                extra={
                    "provider": self.provider_name,
                    "endpoint": "userinfo",
                    "status_code": resp.status_code,
                },
            )
            raise ProviderError(
                "invalid_token",
                "Atlassian userinfo response was invalid",
                status_code=resp.status_code,
            )

        return payload

    async def _request_token(
        self,
        *,
        payload: Mapping[str, Any],
        context: str,
    ) -> _AtlassianTokenResponse:
        """Request tokens from Atlassian's token endpoint.

        OAuth notes:
        - The token endpoint MAY return structured OAuth errors (`error`,
          `error_description`) in non-200 responses or (rarely) 200 responses.
        - We log only the OAuth error code (not description/body) to avoid leaking
          sensitive information.
        """
        async with create_mcp_http_client() as client:
            try:
                resp = await client.post(
                    self.token_url,
                    json=payload,
                    headers={"Content-Type": "application/json"},
                )
            except httpx.RequestError as exc:
                logger.warning(
                    "Atlassian token endpoint request failed",
                    extra={
                        "provider": self.provider_name,
                        "endpoint": "token",
                        "context": context,
                        "error_type": exc.__class__.__name__,
                    },
                )
                raise ProviderError(
                    "temporarily_unavailable",
                    "Atlassian token request failed",
                    status_code=503,
                ) from exc
        return self._parse_token_response(resp, context=context)

    def _parse_token_response(self, resp: Any, *, context: str) -> _AtlassianTokenResponse:
        if resp.status_code != 200:
            error_code = self._try_extract_oauth_error_code(resp)
            logger.warning(
                "Atlassian token endpoint returned non-200",
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
                "Atlassian token request failed",
                status_code=resp.status_code,
            )

        try:
            data = resp.json()
        except Exception as exc:
            logger.warning(
                "Atlassian token endpoint returned invalid JSON",
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
                "Atlassian token endpoint returned non-object JSON",
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
            token = _AtlassianTokenResponse.model_validate(data)
        except ValidationError as exc:
            raise ProviderError(
                "invalid_grant",
                "Invalid token response payload",
                status_code=resp.status_code,
            ) from exc

        if token.error is not None:
            logger.warning(
                "Atlassian token endpoint returned OAuth error",
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
                "Atlassian token request failed",
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
