"""Salesforce OAuth ProviderAdapter implementation for issuer-mode auth."""

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
from ..models import SalesforceAuthConfigModel

logger = logging.getLogger(__name__)


class _SalesforceTokenResponse(SdkBaseModel):
    """Minimal token endpoint response (successful or error)."""

    model_config = ConfigDict(extra="ignore", frozen=True)

    access_token: str | None = None
    refresh_token: str | None = None
    expires_in: float | None = None
    scope: str | None = None
    token_type: str | None = None

    error: str | None = None
    error_description: str | None = None


class _SalesforceUserInfoResponse(SdkBaseModel):
    """Minimal userinfo response used to normalize UserInfo."""

    model_config = ConfigDict(extra="ignore", frozen=True)

    user_id: str | None = None
    username: str | None = None
    email: str | None = None
    name: str | None = None
    photos: Mapping[str, Any] | None = None
    scope: str | None = None

    @property
    def resolved_user_id(self) -> str:
        return self.user_id or ""


class SalesforceProviderAdapter(ProviderAdapter):
    """Salesforce OAuth ProviderAdapter that uses real HTTP calls."""

    provider_name = "salesforce"
    # PKCE support is not assumed; enable only when confirmed.
    pkce_methods_supported: Sequence[str] = []

    def __init__(self, salesforce_config: SalesforceAuthConfigModel):
        self.client_id = salesforce_config.client_id
        self.client_secret = salesforce_config.client_secret
        self.auth_url = salesforce_config.auth_url
        self.token_url = salesforce_config.token_url
        # Preserve legacy default scope behavior if none provided.
        self.scope = salesforce_config.scope or "api refresh_token openid profile email"
        self._callback_path = salesforce_config.callback_path

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
        # Provider scopes come from configuration; client-requested scopes do not alter them.
        scope_str = " ".join(scopes) if scopes else self.scope
        params: list[tuple[str, str]] = [
            ("client_id", self.client_id),
            ("redirect_uri", redirect_uri),
            ("response_type", "code"),
            ("scope", scope_str),
            ("state", state),
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
        payload: dict[str, str] = {
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
        granted_scopes = token.scope.split() if token.scope else list(scopes or [])
        token_type = token.token_type if token.token_type is not None else "Bearer"

        return GrantResult(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_at=expires_at,
            provider_scopes_granted=granted_scopes,
            token_type=token_type,
        )

    async def refresh_token(
        self, *, refresh_token: str, scopes: Sequence[str] | None = None
    ) -> GrantResult:
        payload: dict[str, str] = {
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

        granted_scopes = (token.scope.split() if token.scope else []) or list(scopes or [])
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
            parsed = _SalesforceUserInfoResponse.model_validate(profile)
        except ValidationError as exc:
            raise ProviderError(
                "invalid_token",
                "Salesforce profile response was invalid",
                status_code=400,
            ) from exc

        user_id = parsed.resolved_user_id
        if not user_id:
            raise ProviderError("invalid_token", "Salesforce profile missing user_id", 400)

        username = parsed.username or (parsed.email.split("@")[0] if parsed.email else user_id)
        photos = parsed.photos or {}
        avatar_url = photos.get("picture") if isinstance(photos, Mapping) else None

        return UserInfo(
            provider=self.provider_name,
            user_id=user_id,
            username=username or user_id,
            email=parsed.email,
            name=parsed.name,
            avatar_url=avatar_url,
            raw_profile=profile,
            provider_scopes_granted=parsed.scope.split() if parsed.scope else None,
        )

    # ── helpers ──────────────────────────────────────────────────────────────
    @property
    def callback_path(self) -> str:
        return self._callback_path

    async def _fetch_user_profile(self, token: str) -> dict[str, Any]:
        async with create_mcp_http_client() as client:
            resp = await client.get(
                "https://login.salesforce.com/services/oauth2/userinfo",
                headers={"Authorization": f"Bearer {token}"},
            )

        if resp.status_code != 200:
            logger.warning(
                "Salesforce userinfo endpoint returned non-200",
                extra={
                    "provider": self.provider_name,
                    "endpoint": "userinfo",
                    "status_code": resp.status_code,
                },
            )
            raise ProviderError(
                "invalid_token",
                "Salesforce userinfo request failed",
                status_code=resp.status_code,
            )

        try:
            payload = resp.json()
        except Exception as exc:
            logger.warning(
                "Salesforce userinfo endpoint returned invalid JSON",
                extra={
                    "provider": self.provider_name,
                    "endpoint": "userinfo",
                    "status_code": resp.status_code,
                },
            )
            raise ProviderError(
                "invalid_token",
                "Salesforce userinfo response was invalid",
                status_code=resp.status_code,
            ) from exc

        if not isinstance(payload, dict):
            logger.warning(
                "Salesforce userinfo endpoint returned non-object JSON",
                extra={
                    "provider": self.provider_name,
                    "endpoint": "userinfo",
                    "status_code": resp.status_code,
                },
            )
            raise ProviderError(
                "invalid_token",
                "Salesforce userinfo response was invalid",
                status_code=resp.status_code,
            )
        return payload

    async def _request_token(
        self,
        *,
        payload: Mapping[str, str],
        context: str,
    ) -> _SalesforceTokenResponse:
        async with create_mcp_http_client() as client:
            resp = await client.post(
                self.token_url,
                data=payload,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
        return self._parse_token_response(resp, context=context)

    def _parse_token_response(self, resp: Any, *, context: str) -> _SalesforceTokenResponse:
        if resp.status_code != 200:
            error_code = self._try_extract_oauth_error_code(resp)
            logger.warning(
                "Salesforce token endpoint returned non-200",
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
                "Salesforce token request failed",
                status_code=resp.status_code,
            )

        try:
            data = resp.json()
        except Exception as exc:
            logger.warning(
                "Salesforce token endpoint returned invalid JSON",
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
                "Salesforce token endpoint returned non-object JSON",
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
            token = _SalesforceTokenResponse.model_validate(data)
        except ValidationError as exc:
            raise ProviderError(
                "invalid_grant",
                "Invalid token response payload",
                status_code=resp.status_code,
            ) from exc

        if token.error is not None:
            logger.warning(
                "Salesforce token endpoint returned OAuth error",
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
                "Salesforce token request failed",
                status_code=resp.status_code,
            )

        return token

    def _try_extract_oauth_error_code(self, resp: Any) -> str | None:
        """Best-effort extraction of OAuth `error` code from a response."""
        try:
            payload = resp.json()
        except Exception:
            return None
        if not isinstance(payload, dict):
            return None
        error = payload.get("error")
        return error if isinstance(error, str) and error else None
