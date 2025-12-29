"""GitHub OAuth ProviderAdapter implementation for issuer-mode auth."""

from __future__ import annotations

import base64
import logging
from collections.abc import Mapping, Sequence
from typing import Any
from urllib.parse import urlencode

from mcp.shared._httpx_utils import create_mcp_http_client
from pydantic import ConfigDict, ValidationError

from mxcp.sdk.models import SdkBaseModel

from ..contracts import GrantResult, ProviderAdapter, ProviderError, UserInfo
from ..models import GitHubAuthConfigModel

logger = logging.getLogger(__name__)


class _GitHubTokenResponse(SdkBaseModel):
    """Minimal token endpoint response (successful or error)."""

    model_config = ConfigDict(extra="ignore", frozen=True)

    access_token: str | None = None
    refresh_token: str | None = None
    expires_in: float | None = None
    scope: str | None = None
    token_type: str | None = None

    error: str | None = None
    error_description: str | None = None


class _GitHubUserResponse(SdkBaseModel):
    """Minimal `/user` response used to normalize UserInfo."""

    model_config = ConfigDict(extra="ignore", frozen=True)

    id: int | str | None = None
    login: str | None = None
    email: str | None = None
    name: str | None = None
    avatar_url: str | None = None
    scope: str | None = None

    @property
    def resolved_user_id(self) -> str:
        if self.id is None:
            return ""
        return str(self.id)


class GitHubProviderAdapter(ProviderAdapter):
    """GitHub OAuth ProviderAdapter that uses real HTTP calls."""

    provider_name = "github"
    pkce_methods_supported = ["S256"]

    def __init__(self, github_config: GitHubAuthConfigModel):
        self.client_id = github_config.client_id
        self.client_secret = github_config.client_secret
        self.auth_url = github_config.auth_url
        self.token_url = github_config.token_url
        # Preserve legacy default scope behavior if none provided.
        self.scope = github_config.scope or "user:email"
        self._callback_path = github_config.callback_path

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

        user_profile = await self._fetch_user_profile(access_token)
        expires_at = None
        if expires_in is not None:
            expires_at = float(expires_in)
        granted_scopes = token.scope.split(",") if token.scope else list(scopes or [])
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

        granted_scopes = (token.scope.split(",") if token.scope else []) or list(scopes or [])
        expires_at = float(expires_in) if expires_in is not None else None
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
            parsed = _GitHubUserResponse.model_validate(profile)
        except ValidationError as exc:
            raise ProviderError(
                "invalid_token",
                "GitHub profile response was invalid",
                status_code=400,
            ) from exc

        user_id = parsed.resolved_user_id
        if not user_id:
            raise ProviderError("invalid_token", "GitHub profile missing id", status_code=400)

        username = parsed.login or user_id

        return UserInfo(
            provider=self.provider_name,
            user_id=user_id,
            username=username,
            email=parsed.email,
            name=parsed.name,
            avatar_url=parsed.avatar_url,
            raw_profile=profile,
            provider_scopes_granted=parsed.scope.split(",") if parsed.scope else None,
        )

    async def revoke_token(self, *, token: str, token_type_hint: str | None = None) -> bool:
        # GitHub token revocation requires Basic auth with client credentials.
        basic = base64.b64encode(f"{self.client_id}:{self.client_secret}".encode()).decode()
        async with create_mcp_http_client() as client:
            resp = await client.post(
                f"https://api.github.com/applications/{self.client_id}/token",
                headers={
                    "Accept": "application/vnd.github+json",
                    "Authorization": f"Basic {basic}",
                },
                json={"access_token": token},
            )
        if resp.status_code in {200, 204, 404}:
            # 404 means token not found; treat as already revoked.
            return True
        logger.warning(
            "GitHub revoke endpoint returned unexpected status",
            extra={
                "provider": self.provider_name,
                "endpoint": "revoke",
                "status_code": resp.status_code,
            },
        )
        raise ProviderError(
            "invalid_token",
            "GitHub token revocation failed",
            status_code=resp.status_code,
        )

    # ── helpers ──────────────────────────────────────────────────────────────
    @property
    def callback_path(self) -> str:
        return self._callback_path

    async def _fetch_user_profile(self, token: str) -> dict[str, Any]:
        async with create_mcp_http_client() as client:
            resp = await client.get(
                "https://api.github.com/user",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/vnd.github+json",
                },
            )

        if resp.status_code != 200:
            logger.warning(
                "GitHub user endpoint returned non-200",
                extra={
                    "provider": self.provider_name,
                    "endpoint": "user",
                    "status_code": resp.status_code,
                },
            )
            raise ProviderError(
                "invalid_token",
                "GitHub userinfo request failed",
                status_code=resp.status_code,
            )

        try:
            payload = resp.json()
        except Exception as exc:
            logger.warning(
                "GitHub user endpoint returned invalid JSON",
                extra={
                    "provider": self.provider_name,
                    "endpoint": "user",
                    "status_code": resp.status_code,
                },
            )
            raise ProviderError(
                "invalid_token",
                "GitHub userinfo response was invalid",
                status_code=resp.status_code,
            ) from exc

        if not isinstance(payload, dict):
            logger.warning(
                "GitHub user endpoint returned non-object JSON",
                extra={
                    "provider": self.provider_name,
                    "endpoint": "user",
                    "status_code": resp.status_code,
                },
            )
            raise ProviderError(
                "invalid_token",
                "GitHub userinfo response was invalid",
                status_code=resp.status_code,
            )

        try:
            _GitHubUserResponse.model_validate(payload)
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
    ) -> _GitHubTokenResponse:
        async with create_mcp_http_client() as client:
            resp = await client.post(
                self.token_url,
                data=payload,
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Accept": "application/json",
                },
            )
        return self._parse_token_response(resp, context=context)

    def _parse_token_response(self, resp: Any, *, context: str) -> _GitHubTokenResponse:
        if resp.status_code != 200:
            error_code = self._try_extract_oauth_error_code(resp)
            logger.warning(
                "GitHub token endpoint returned non-200",
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
                "GitHub token request failed",
                status_code=resp.status_code,
            )

        try:
            data = resp.json()
        except Exception as exc:
            logger.warning(
                "GitHub token endpoint returned invalid JSON",
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
                "GitHub token endpoint returned non-object JSON",
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
            token = _GitHubTokenResponse.model_validate(data)
        except ValidationError as exc:
            raise ProviderError(
                "invalid_grant",
                "Invalid token response payload",
                status_code=resp.status_code,
            ) from exc

        if token.error is not None:
            logger.warning(
                "GitHub token endpoint returned OAuth error",
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
                "GitHub token request failed",
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
