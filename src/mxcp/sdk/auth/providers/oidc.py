"""Generic OIDC ProviderAdapter implementation for issuer-mode auth.

Endpoints are resolved lazily from an OpenID Connect discovery document.
Call ``ensure_ready()`` once at startup before using the adapter.
"""

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
from ..models import OIDCAuthConfigModel
from .oidc_discovery import OIDCDiscoveryDocument, fetch_oidc_discovery

logger = logging.getLogger(__name__)


class _OIDCTokenResponse(SdkBaseModel):
    """Minimal token endpoint response (successful or error)."""

    model_config = ConfigDict(extra="ignore", frozen=True)

    access_token: str | None = None
    refresh_token: str | None = None
    expires_in: float | None = None
    scope: str | None = None
    token_type: str | None = None

    error: str | None = None
    error_description: str | None = None


class _OIDCUserInfoResponse(SdkBaseModel):
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


class OIDCProviderAdapter(ProviderAdapter):
    """Generic OIDC ProviderAdapter using real HTTP calls.

    Endpoints are auto-discovered from a ``/.well-known/openid-configuration``
    document.  Call :meth:`ensure_ready` once before using the adapter so that
    endpoints are resolved.
    """

    # The discovery document ``issuer`` field (e.g.
    # ``https://keycloak.corp.com/realms/prod``) would be the most descriptive
    # value here, but it is a URL that may expose internal infrastructure
    # details (hostnames, realm names, IdP software) to clients via
    # ``get_user_provider()``.  Default to the generic "oidc" label and let
    # users override it with ``provider_name`` in config if they want a
    # more meaningful value.
    provider_name = "oidc"
    pkce_methods_supported: Sequence[str] = []

    def __init__(self, oidc_config: OIDCAuthConfigModel):
        self.provider_name = oidc_config.provider_name or "oidc"
        self.client_id = oidc_config.client_id
        self.client_secret = oidc_config.client_secret
        self.scope = oidc_config.scope
        self._callback_path = oidc_config.callback_path
        self._config_url = oidc_config.config_url
        self._audience = oidc_config.audience
        self._extra_authorize_params = oidc_config.extra_authorize_params or {}

        # Populated by ensure_ready()
        self._discovery: OIDCDiscoveryDocument | None = None
        self.auth_url: str | None = None
        self.token_url: str | None = None
        self.userinfo_url: str | None = None
        self.revoke_url: str | None = None

    async def ensure_ready(self) -> None:
        """Fetch the OIDC discovery document and populate endpoints.

        This must be called once (typically at server startup) before any
        other method is invoked.  Repeated calls are no-ops.
        """
        if self._discovery is not None:
            return

        discovery = await fetch_oidc_discovery(self._config_url)
        self._discovery = discovery
        self.auth_url = discovery.authorization_endpoint
        self.token_url = discovery.token_endpoint
        self.userinfo_url = discovery.userinfo_endpoint
        self.revoke_url = discovery.revocation_endpoint

        # Derive PKCE capability from the discovery document.
        if discovery.code_challenge_methods_supported:
            self.pkce_methods_supported = list(discovery.code_challenge_methods_supported)
        else:
            # Default to S256 when the discovery doc does not advertise support
            # (many IdPs support S256 but omit the field).
            self.pkce_methods_supported = ["S256"]

        logger.info("OIDC discovery completed for issuer %s", discovery.issuer)

    # ── ProviderAdapter interface ───────────────────────────────────────

    def build_authorize_url(
        self,
        *,
        redirect_uri: str,
        state: str,
        code_challenge: str | None = None,
        code_challenge_method: str | None = None,
        extra_params: Mapping[str, str] | None = None,
    ) -> str:
        assert self.auth_url is not None, "ensure_ready() must be called before build_authorize_url()"

        params: list[tuple[str, str]] = [
            ("client_id", self.client_id),
            ("response_type", "code"),
            ("redirect_uri", redirect_uri),
            ("scope", self.scope),
            ("state", state),
        ]
        if self._audience:
            params.append(("audience", self._audience))
        if code_challenge:
            params.append(("code_challenge", code_challenge))
        if code_challenge_method:
            params.append(("code_challenge_method", code_challenge_method))
        elif code_challenge:
            params.append(("code_challenge_method", "S256"))
        if self._extra_authorize_params:
            params.extend(self._extra_authorize_params.items())
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
        payload: dict[str, str] = {
            "grant_type": "authorization_code",
            "code": code,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "redirect_uri": redirect_uri,
        }
        if code_verifier:
            payload["code_verifier"] = code_verifier
        if self._audience:
            payload["audience"] = self._audience

        token = await self._request_token(payload=payload, context="exchange_code")

        access_token = token.access_token
        refresh_token = token.refresh_token
        expires_in = token.expires_in
        if not access_token:
            raise ProviderError("invalid_grant", "No access_token in response", status_code=400)

        expires_at = time.time() + float(expires_in) if expires_in is not None else None
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
        payload: dict[str, str] = {
            "grant_type": "refresh_token",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "refresh_token": refresh_token,
        }
        if scopes:
            payload["scope"] = " ".join(scopes)
        if self._audience:
            payload["audience"] = self._audience

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
            parsed = _OIDCUserInfoResponse.model_validate(profile)
        except ValidationError as exc:
            raise ProviderError(
                "invalid_token",
                "OIDC profile response was invalid",
                status_code=400,
            ) from exc

        user_id = parsed.resolved_user_id
        if not user_id:
            raise ProviderError("invalid_token", "OIDC profile missing sub", status_code=400)

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
            provider_scopes_granted=parsed.scope.split() if parsed.scope else [],
        )

    # ── helpers ──────────────────────────────────────────────────────────

    @property
    def callback_path(self) -> str:
        return self._callback_path

    async def _fetch_user_profile(self, token: str) -> dict[str, Any]:
        if not self.userinfo_url:
            raise ProviderError(
                "server_error",
                "OIDC provider does not expose a userinfo endpoint",
                status_code=500,
            )

        async with create_mcp_http_client() as client:
            try:
                resp = await client.get(
                    self.userinfo_url,
                    headers={"Authorization": f"Bearer {token}"},
                )
            except httpx.RequestError as exc:
                logger.warning(
                    "OIDC userinfo endpoint request failed",
                    extra={
                        "provider": self.provider_name,
                        "endpoint": "userinfo",
                        "error_type": exc.__class__.__name__,
                    },
                )
                raise ProviderError(
                    "temporarily_unavailable",
                    "OIDC userinfo request failed",
                    status_code=503,
                ) from exc

        if resp.status_code != 200:
            logger.warning(
                "OIDC userinfo endpoint returned non-200",
                extra={
                    "provider": self.provider_name,
                    "endpoint": "userinfo",
                    "status_code": resp.status_code,
                },
            )
            raise ProviderError(
                "invalid_token",
                "OIDC userinfo request failed",
                status_code=resp.status_code,
            )

        try:
            payload = resp.json()
        except Exception as exc:
            logger.warning(
                "OIDC userinfo endpoint returned invalid JSON",
                extra={
                    "provider": self.provider_name,
                    "endpoint": "userinfo",
                    "status_code": resp.status_code,
                },
            )
            raise ProviderError(
                "invalid_token",
                "OIDC userinfo response was invalid",
                status_code=resp.status_code,
            ) from exc

        if not isinstance(payload, dict):
            logger.warning(
                "OIDC userinfo endpoint returned non-object JSON",
                extra={
                    "provider": self.provider_name,
                    "endpoint": "userinfo",
                    "status_code": resp.status_code,
                },
            )
            raise ProviderError(
                "invalid_token",
                "OIDC userinfo response was invalid",
                status_code=resp.status_code,
            )
        return payload

    async def _request_token(
        self,
        *,
        payload: Mapping[str, str],
        context: str,
    ) -> _OIDCTokenResponse:
        assert self.token_url is not None, "ensure_ready() must be called before _request_token()"

        async with create_mcp_http_client() as client:
            try:
                resp = await client.post(
                    self.token_url,
                    data=payload,
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )
            except httpx.RequestError as exc:
                logger.warning(
                    "OIDC token endpoint request failed",
                    extra={
                        "provider": self.provider_name,
                        "endpoint": "token",
                        "context": context,
                        "error_type": exc.__class__.__name__,
                    },
                )
                raise ProviderError(
                    "temporarily_unavailable",
                    "OIDC token request failed",
                    status_code=503,
                ) from exc
        return self._parse_token_response(resp, context=context)

    def _parse_token_response(self, resp: Any, *, context: str) -> _OIDCTokenResponse:
        if resp.status_code != 200:
            error_code = self._try_extract_oauth_error_code(resp)
            logger.warning(
                "OIDC token endpoint returned non-200",
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
                "OIDC token request failed",
                status_code=resp.status_code,
            )

        try:
            data = resp.json()
        except Exception as exc:
            logger.warning(
                "OIDC token endpoint returned invalid JSON",
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
                "OIDC token endpoint returned non-object JSON",
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
            token = _OIDCTokenResponse.model_validate(data)
        except ValidationError as exc:
            raise ProviderError(
                "invalid_grant",
                "Invalid token response payload",
                status_code=resp.status_code,
            ) from exc

        if token.error is not None:
            logger.warning(
                "OIDC token endpoint returned OAuth error",
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
                "OIDC token request failed",
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
