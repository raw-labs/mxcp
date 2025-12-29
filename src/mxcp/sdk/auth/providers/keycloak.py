"""Keycloak OAuth ProviderAdapter implementation for issuer-mode auth."""

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
from ..models import KeycloakAuthConfigModel

logger = logging.getLogger(__name__)


class _KeycloakTokenResponse(SdkBaseModel):
    """Minimal token endpoint response (successful or error)."""

    model_config = ConfigDict(extra="ignore", frozen=True)

    access_token: str | None = None
    refresh_token: str | None = None
    expires_in: float | None = None
    scope: str | None = None
    token_type: str | None = None

    error: str | None = None
    error_description: str | None = None


class _KeycloakUserInfoResponse(SdkBaseModel):
    """Minimal userinfo response used to normalize UserInfo."""

    model_config = ConfigDict(extra="ignore", frozen=True)

    sub: str | None = None
    preferred_username: str | None = None
    email: str | None = None
    name: str | None = None
    picture: str | None = None
    scope: str | None = None

    @property
    def resolved_user_id(self) -> str:
        return self.sub or ""


class KeycloakProviderAdapter(ProviderAdapter):
    """Keycloak OAuth ProviderAdapter using real HTTP calls."""

    provider_name = "keycloak"
    # Keycloak supports PKCE S256; enable capability so AuthService can drive upstream PKCE.
    pkce_methods_supported: Sequence[str] = ["S256"]

    def __init__(self, keycloak_config: KeycloakAuthConfigModel):
        self.client_id = keycloak_config.client_id
        self.client_secret = keycloak_config.client_secret
        self.realm = keycloak_config.realm
        self.server_url = keycloak_config.server_url.rstrip("/")
        self.scope = keycloak_config.scope or "openid profile email"
        self._callback_path = keycloak_config.callback_path

        realm_base = f"{self.server_url}/realms/{self.realm}/protocol/openid-connect"
        self.auth_url = f"{realm_base}/auth"
        self.token_url = f"{realm_base}/token"
        self.userinfo_url = f"{realm_base}/userinfo"
        self.revoke_url = f"{realm_base}/revoke"

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
        params: list[tuple[str, str]] = [
            ("client_id", self.client_id),
            ("response_type", "code"),
            ("redirect_uri", redirect_uri),
            ("scope", scope_str),
            ("state", state),
        ]
        if code_challenge:
            params.append(("code_challenge", code_challenge))
        if code_challenge_method:
            params.append(("code_challenge_method", code_challenge_method))
        elif code_challenge:
            # Keycloak requires method when a challenge is present; default to S256.
            params.append(("code_challenge_method", "S256"))
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
            "code": code,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
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

        user_profile = await self._fetch_user_profile(access_token)
        expires_at = time.time() + float(expires_in) if expires_in else None
        granted_scopes = token.scope.split() if token.scope else list(scopes or [])
        token_type = token.token_type if token.token_type is not None else "Bearer"

        return GrantResult(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_at=expires_at,
            provider_scopes_granted=granted_scopes,
            raw_profile=user_profile,
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
            parsed = _KeycloakUserInfoResponse.model_validate(profile)
        except ValidationError as exc:
            raise ProviderError(
                "invalid_token",
                "Keycloak profile response was invalid",
                status_code=400,
            ) from exc

        user_id = parsed.resolved_user_id
        if not user_id:
            raise ProviderError("invalid_token", "Keycloak profile missing sub", status_code=400)

        username = parsed.preferred_username or (
            parsed.email.split("@")[0] if parsed.email else user_id
        )

        return UserInfo(
            provider=self.provider_name,
            user_id=user_id,
            username=username,
            email=parsed.email,
            name=parsed.name,
            avatar_url=parsed.picture,
            raw_profile=profile,
            provider_scopes_granted=parsed.scope.split() if parsed.scope else None,
        )

    async def revoke_token(self, *, token: str, token_type_hint: str | None = None) -> bool:
        data: dict[str, str] = {
            "token": token,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
        }
        if token_type_hint:
            data["token_type_hint"] = token_type_hint
        async with create_mcp_http_client() as client:
            resp = await client.post(
                self.revoke_url,
                data=data,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
        if resp.status_code in {200, 400}:
            # 400 for invalid token; treat as already revoked.
            return True
        logger.warning(
            "Keycloak revoke endpoint returned unexpected status",
            extra={
                "provider": self.provider_name,
                "endpoint": "revoke",
                "status_code": resp.status_code,
            },
        )
        raise ProviderError(
            "invalid_token",
            "Keycloak token revocation failed",
            status_code=resp.status_code,
        )

    # ── helpers ──────────────────────────────────────────────────────────────
    @property
    def callback_path(self) -> str:
        return self._callback_path

    async def _fetch_user_profile(self, token: str) -> dict[str, Any]:
        async with create_mcp_http_client() as client:
            resp = await client.get(
                self.userinfo_url,
                headers={"Authorization": f"Bearer {token}"},
            )

        if resp.status_code != 200:
            logger.warning(
                "Keycloak userinfo endpoint returned non-200",
                extra={
                    "provider": self.provider_name,
                    "endpoint": "userinfo",
                    "status_code": resp.status_code,
                },
            )
            raise ProviderError(
                "invalid_token",
                "Keycloak userinfo request failed",
                status_code=resp.status_code,
            )

        try:
            payload = resp.json()
        except Exception as exc:
            logger.warning(
                "Keycloak userinfo endpoint returned invalid JSON",
                extra={
                    "provider": self.provider_name,
                    "endpoint": "userinfo",
                    "status_code": resp.status_code,
                },
            )
            raise ProviderError(
                "invalid_token",
                "Keycloak userinfo response was invalid",
                status_code=resp.status_code,
            ) from exc

        if not isinstance(payload, dict):
            logger.warning(
                "Keycloak userinfo endpoint returned non-object JSON",
                extra={
                    "provider": self.provider_name,
                    "endpoint": "userinfo",
                    "status_code": resp.status_code,
                },
            )
            raise ProviderError(
                "invalid_token",
                "Keycloak userinfo response was invalid",
                status_code=resp.status_code,
            )

        try:
            _KeycloakUserInfoResponse.model_validate(payload)
        except ValidationError as exc:
            raise ProviderError(
                "invalid_token",
                "Invalid userinfo payload",
                status_code=resp.status_code,
            ) from exc
        return payload

    async def _request_token(
        self,
        *,
        payload: Mapping[str, str],
        context: str,
    ) -> _KeycloakTokenResponse:
        async with create_mcp_http_client() as client:
            resp = await client.post(
                self.token_url,
                data=payload,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
        return self._parse_token_response(resp, context=context)

    def _parse_token_response(self, resp: Any, *, context: str) -> _KeycloakTokenResponse:
        if resp.status_code != 200:
            error_code = self._try_extract_oauth_error_code(resp)
            logger.warning(
                "Keycloak token endpoint returned non-200",
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
                "Keycloak token request failed",
                status_code=resp.status_code,
            )

        try:
            data = resp.json()
        except Exception as exc:
            logger.warning(
                "Keycloak token endpoint returned invalid JSON",
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
                "Keycloak token endpoint returned non-object JSON",
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
            token = _KeycloakTokenResponse.model_validate(data)
        except ValidationError as exc:
            raise ProviderError(
                "invalid_grant",
                "Invalid token response payload",
                status_code=resp.status_code,
            ) from exc

        if token.error is not None:
            logger.warning(
                "Keycloak token endpoint returned OAuth error",
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
                "Keycloak token request failed",
                status_code=resp.status_code,
            )

        return token

    def _try_extract_oauth_error_code(self, resp: Any) -> str | None:
        try:
            payload = resp.json()
        except Exception:
            return None
        if not isinstance(payload, dict):
            return None
        error = payload.get("error")
        return error if isinstance(error, str) and error else None
