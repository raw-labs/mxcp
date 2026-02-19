"""Token verifier implementations for verifier-mode auth."""

from __future__ import annotations

import logging
from typing import Any

import httpx
import jwt
from jwt import PyJWKClient
from mcp.server.auth.provider import AccessToken, TokenVerifier
from mcp.shared._httpx_utils import create_mcp_http_client

from mxcp.sdk.auth.context import set_verified_user_info
from mxcp.sdk.auth.contracts import UserInfo
from mxcp.sdk.auth.models import OIDCVerifierAuthConfigModel
from mxcp.sdk.auth.providers.oidc import OIDCDiscoveryDocument, fetch_oidc_discovery

logger = logging.getLogger(__name__)


class OIDCTokenVerifier(TokenVerifier):
    """Verifier-mode OIDC token verifier using discovery + introspection or userinfo."""

    def __init__(self, oidc_config: OIDCVerifierAuthConfigModel):
        self.client_id = oidc_config.client_id
        self.client_secret = oidc_config.client_secret
        self.scope = oidc_config.scope
        self._config_url = oidc_config.config_url
        self._audience = oidc_config.audience
        self._provider_name = oidc_config.provider_name or "oidc"

        self._discovery: OIDCDiscoveryDocument | None = None
        self._jwks_client: PyJWKClient | None = None
        self._introspection_url: str | None = None
        self._userinfo_url: str | None = None
        self._issuer: str | None = None

    async def _ensure_ready(self) -> None:
        if self._discovery is not None:
            return
        discovery = await fetch_oidc_discovery(self._config_url)
        self._discovery = discovery
        self._issuer = discovery.issuer
        if discovery.jwks_uri:
            self._jwks_client = PyJWKClient(discovery.jwks_uri)
        self._introspection_url = getattr(discovery, "introspection_endpoint", None)
        self._userinfo_url = discovery.userinfo_endpoint

    async def verify_token(self, token: str) -> AccessToken | None:
        await self._ensure_ready()
        claims: dict[str, Any] | None = None
        verification_path: str | None = None

        # Prefer JWT validation if token looks like JWT and jwks is available.
        if self._jwks_client and _looks_like_jwt(token):
            claims = await self._verify_jwt(token)
            if claims is not None:
                verification_path = "jwt"
                logger.debug("OIDC verifier: JWT verification succeeded")
            else:
                logger.debug("OIDC verifier: JWT verification failed; trying fallbacks")

        # Fallback to introspection
        if claims is None and self._introspection_url:
            claims = await self._call_introspection(token)
            if claims is not None:
                verification_path = "introspection"
                logger.debug("OIDC verifier: introspection succeeded")

        # Fallback to userinfo (weak)
        if claims is None and self._userinfo_url:
            claims = await self._call_userinfo(token)
            if claims is not None:
                verification_path = "userinfo"
                logger.debug("OIDC verifier: userinfo fallback succeeded")

        if claims is None:
            logger.warning(
                "OIDC verifier: unable to validate token (no jwt/introspection/userinfo)"
            )
            return None

        user_info = self._build_user_info(claims)
        if not user_info:
            return None
        set_verified_user_info(user_info)

        if verification_path:
            logger.debug(
                "OIDC verifier: selected validation path",
                extra={
                    "provider": self._provider_name,
                    "issuer": self._issuer,
                    "path": verification_path,
                },
            )

        scopes = _split_scopes(claims.get("scope")) or _split_scopes(self.scope)
        exp = claims.get("exp")
        expires_at = int(exp) if isinstance(exp, (int | float)) else None
        client_id = claims.get("client_id") or claims.get("azp") or self.client_id

        return AccessToken(
            token=token,
            client_id=str(client_id),
            scopes=scopes,
            expires_at=expires_at,
        )

    async def _verify_jwt(self, token: str) -> dict[str, Any] | None:
        if not self._jwks_client:
            return None
        try:
            signing_key = await _get_signing_key(self._jwks_client, token)
            options = {
                "verify_signature": True,
                "verify_exp": True,
                "verify_nbf": True,
                "verify_iss": bool(self._issuer),
                "verify_aud": bool(self._audience),
            }
            claims = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256", "PS256", "ES256", "RS384", "RS512", "ES384", "ES512"],
                audience=self._audience,
                issuer=self._issuer,
                options=options,
            )
            if not isinstance(claims, dict):
                return None
            return claims
        except Exception as exc:  # broad: decode errors vary
            logger.warning(
                "OIDC JWT verification failed",
                extra={"error": exc.__class__.__name__, "detail": str(exc)[:200]},
            )
            return None

    async def _call_introspection(self, token: str) -> dict[str, Any] | None:
        if not self._introspection_url:
            return None
        data = {
            "token": token,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
        }
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        async with create_mcp_http_client() as client:
            try:
                resp = await client.post(self._introspection_url, data=data, headers=headers)
            except httpx.RequestError as exc:
                logger.warning(
                    "OIDC introspection request failed", extra={"error": exc.__class__.__name__}
                )
                return None
        if resp.status_code != 200:
            logger.warning("OIDC introspection non-200", extra={"status_code": resp.status_code})
            return None
        try:
            payload = resp.json()
        except Exception:
            return None
        if not isinstance(payload, dict):
            return None
        if not payload.get("active"):
            return None
        return payload

    async def _call_userinfo(self, token: str) -> dict[str, Any] | None:
        if not self._userinfo_url:
            return None
        headers = {"Authorization": f"Bearer {token}"}
        async with create_mcp_http_client() as client:
            try:
                resp = await client.get(self._userinfo_url, headers=headers)
            except httpx.RequestError as exc:
                logger.warning(
                    "OIDC userinfo request failed", extra={"error": exc.__class__.__name__}
                )
                return None
        if resp.status_code != 200:
            return None
        try:
            payload = resp.json()
        except Exception:
            return None
        return payload if isinstance(payload, dict) else None

    def _build_user_info(self, claims: dict[str, Any]) -> UserInfo | None:
        sub = claims.get("sub")
        if not sub or not isinstance(sub, str):
            return None
        preferred = claims.get("preferred_username")
        email = claims.get("email")
        username = preferred or claims.get("username")
        if not username and isinstance(email, str):
            username = email.split("@")[0]
        username = username or sub

        scope_str = claims.get("scope") if isinstance(claims.get("scope"), str) else None
        provider_scopes = _split_scopes(scope_str)

        return UserInfo(
            provider=self._provider_name,
            user_id=sub,
            username=username,
            email=email if isinstance(email, str) else None,
            name=claims.get("name") if isinstance(claims.get("name"), str) else None,
            avatar_url=claims.get("picture") if isinstance(claims.get("picture"), str) else None,
            raw_profile=claims,
            provider_scopes_granted=provider_scopes,
        )


def _split_scopes(scope_str: str | None) -> list[str]:
    if not scope_str:
        return []
    return [s for s in scope_str.split() if s]


def _looks_like_jwt(token: str) -> bool:
    return token.count(".") == 2


async def _get_signing_key(jwks_client: PyJWKClient, token: str) -> Any:
    # PyJWKClient's get_signing_key_from_jwt is blocking; run in thread?
    # For simplicity here, call directly (short-lived).
    return jwks_client.get_signing_key_from_jwt(token)
