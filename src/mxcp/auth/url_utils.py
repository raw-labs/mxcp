# -*- coding: utf-8 -*-
"""URL generation utilities for OAuth authentication with reverse proxy support."""
import logging
import os
from typing import Any, Dict, Optional
from urllib.parse import urljoin, urlparse, urlunparse

from starlette.requests import Request

from mxcp.config.types import UserAuthConfig, UserHttpTransportConfig

logger = logging.getLogger(__name__)


class URLBuilder:
    """Utility class for building URLs with proper scheme detection for OAuth flows.

    Handles:
    - Explicit scheme configuration (http/https)
    - Base URL override
    - Reverse proxy header detection (X-Forwarded-Proto, X-Forwarded-Scheme)
    - Fallback to request scheme
    """

    def __init__(self, transport_config: Optional[UserHttpTransportConfig] = None):
        """Initialize URL builder with transport configuration.

        Args:
            transport_config: HTTP transport configuration from user config
        """
        self.transport_config = transport_config or {}

    def get_base_url(
        self,
        request: Optional[Request] = None,
        host: Optional[str] = None,
        port: Optional[int] = None,
    ) -> str:
        """Get the base URL for the server, handling all scheme detection logic.

        Args:
            request: Optional Starlette request for header inspection
            host: Override host (defaults to config or 'localhost')
            port: Override port (defaults to config or 8000)

        Returns:
            Complete base URL (e.g., 'https://api.example.com:8000')
        """
        # 1. Check for explicit base_url override
        base_url = self.transport_config.get("base_url")
        if base_url:
            logger.debug(f"Using explicit base_url from config: {base_url}")
            return base_url.rstrip("/")

        # 2. Determine scheme
        scheme = self._detect_scheme(request)

        # 3. Determine host and port
        final_host = host or self.transport_config.get("host", "localhost")
        final_port = port or self.transport_config.get("port", 8000)

        # 4. Build URL
        if (scheme == "https" and final_port == 443) or (scheme == "http" and final_port == 80):
            # Standard ports - omit from URL
            base_url = f"{scheme}://{final_host}"
        else:
            base_url = f"{scheme}://{final_host}:{final_port}"

        logger.debug(
            f"Built base URL: {base_url} (scheme={scheme}, host={final_host}, port={final_port})"
        )
        return base_url

    def build_callback_url(
        self,
        callback_path: str,
        request: Optional[Request] = None,
        host: Optional[str] = None,
        port: Optional[int] = None,
    ) -> str:
        """Build a complete callback URL for OAuth flows.

        Args:
            callback_path: The callback path (e.g., '/github/callback')
            request: Optional request for header inspection
            host: Override host
            port: Override port

        Returns:
            Complete callback URL
        """
        base_url = self.get_base_url(request, host, port)
        callback_path = callback_path.lstrip("/")  # Remove leading slash
        return f"{base_url}/{callback_path}"

    def _detect_scheme(self, request: Optional[Request] = None) -> str:
        """Detect the appropriate URL scheme (http/https).

        Priority order:
        1. Explicit scheme in transport config
        2. X-Forwarded-Proto header (if trust_proxy enabled)
        3. X-Forwarded-Scheme header (if trust_proxy enabled)
        4. Request scheme (if available)
        5. Default to 'http'

        Args:
            request: Optional request for header inspection

        Returns:
            URL scheme ('http' or 'https')
        """
        # 1. Check explicit configuration
        config_scheme = self.transport_config.get("scheme")
        if config_scheme:
            logger.debug(f"Using explicit scheme from config: {config_scheme}")
            return config_scheme

        # 2. Check proxy headers (if enabled)
        if self.transport_config.get("trust_proxy", False) and request:
            # X-Forwarded-Proto (most common)
            forwarded_proto = request.headers.get("x-forwarded-proto")
            if forwarded_proto:
                # Handle comma-separated values (take first)
                scheme = forwarded_proto.split(",")[0].strip().lower()
                if scheme in ("http", "https"):
                    logger.debug(f"Using scheme from X-Forwarded-Proto header: {scheme}")
                    return scheme

            # X-Forwarded-Scheme (alternative)
            forwarded_scheme = request.headers.get("x-forwarded-scheme")
            if forwarded_scheme:
                scheme = forwarded_scheme.strip().lower()
                if scheme in ("http", "https"):
                    logger.debug(f"Using scheme from X-Forwarded-Scheme header: {scheme}")
                    return scheme

        # 3. Check request scheme
        if request and hasattr(request.url, "scheme"):
            scheme = request.url.scheme.lower()
            if scheme in ("http", "https"):
                logger.debug(f"Using scheme from request: {scheme}")
                return scheme

        # 4. Default fallback
        logger.debug("Using default scheme: http")
        return "http"


def create_url_builder(user_config: Dict[str, Any]) -> URLBuilder:
    """Create a URL builder from user configuration.

    Args:
        user_config: User configuration dictionary

    Returns:
        Configured URLBuilder instance
    """
    transport_config = user_config.get("transport", {}).get("http", {})
    return URLBuilder(transport_config)
