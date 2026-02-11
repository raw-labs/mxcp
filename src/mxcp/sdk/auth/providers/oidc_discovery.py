"""OpenID Connect discovery document fetching and parsing."""

from __future__ import annotations

import logging

import httpx
from mcp.shared._httpx_utils import create_mcp_http_client
from pydantic import ConfigDict

from mxcp.sdk.models import SdkBaseModel

from ..contracts import ProviderError

logger = logging.getLogger(__name__)


class OIDCDiscoveryDocument(SdkBaseModel):
    """Parsed OpenID Connect discovery document.

    Only the fields MXCP needs are extracted; unknown fields are silently
    ignored (``extra="ignore"``).
    """

    model_config = ConfigDict(extra="ignore", frozen=True)

    issuer: str
    authorization_endpoint: str
    token_endpoint: str
    userinfo_endpoint: str | None = None
    revocation_endpoint: str | None = None
    code_challenge_methods_supported: list[str] | None = None


async def fetch_oidc_discovery(config_url: str) -> OIDCDiscoveryDocument:
    """Fetch and parse an OIDC discovery document from *config_url*.

    Raises ``ProviderError`` on network errors, non-200 responses, or
    invalid JSON payloads.
    """
    async with create_mcp_http_client() as client:
        try:
            resp = await client.get(config_url)
        except httpx.RequestError as exc:
            logger.warning(
                "OIDC discovery endpoint request failed",
                extra={
                    "provider": "oidc",
                    "endpoint": "discovery",
                    "error_type": exc.__class__.__name__,
                },
            )
            raise ProviderError(
                "temporarily_unavailable",
                "OIDC discovery request failed",
                status_code=503,
            ) from exc

    if resp.status_code != 200:
        logger.warning(
            "OIDC discovery endpoint returned non-200",
            extra={
                "provider": "oidc",
                "endpoint": "discovery",
                "status_code": resp.status_code,
            },
        )
        raise ProviderError(
            "server_error",
            "OIDC discovery request failed",
            status_code=resp.status_code,
        )

    try:
        data = resp.json()
    except Exception as exc:
        logger.warning(
            "OIDC discovery endpoint returned invalid JSON",
            extra={
                "provider": "oidc",
                "endpoint": "discovery",
                "status_code": resp.status_code,
            },
        )
        raise ProviderError(
            "server_error",
            "OIDC discovery response was invalid",
            status_code=resp.status_code,
        ) from exc

    if not isinstance(data, dict):
        raise ProviderError(
            "server_error",
            "OIDC discovery response was not a JSON object",
            status_code=resp.status_code,
        )

    return OIDCDiscoveryDocument.model_validate(data)
