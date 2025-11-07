"""
Configuration reload endpoints.

Provides endpoints for triggering and managing configuration reloads.
"""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from ..models import ReloadResponse
from ..protocol import AdminServerProtocol

logger = logging.getLogger(__name__)


def create_reload_router(server: AdminServerProtocol) -> APIRouter:
    """
    Create reload router with server dependency.

    Args:
        server: The MXCP server instance

    Returns:
        Configured APIRouter
    """
    router = APIRouter(tags=["reload"])

    @router.post("/reload", response_model=ReloadResponse, summary="Trigger configuration reload")
    async def trigger_reload() -> ReloadResponse:
        """
        Trigger configuration reload (equivalent to SIGHUP).

        Initiates an asynchronous reload of external configuration values including:
        - Vault secrets
        - File references
        - Environment variables
        - Database connections
        - Python runtime environment

        **Note**: The reload is asynchronous. Use GET /status to check progress.

        **What Gets Reloaded**:
        - ✅ External configuration values (vault://, file://, env vars)
        - ✅ Secret values
        - ✅ Database connections
        - ✅ Python runtime environment

        **What Does NOT Reload** (requires restart):
        - ❌ Endpoint definitions
        - ❌ OAuth configuration
        - ❌ Transport settings

        Returns:
            Reload confirmation with request ID for tracking
        """
        logger.info("[admin] Reload requested via API")

        try:
            reload_request = server.reload_configuration()

            return ReloadResponse(
                timestamp=datetime.now(timezone.utc),
                reload_request_id=reload_request.id,
            )

        except Exception as e:
            logger.error(f"[admin] Reload failed: {e}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail=f"Reload failed: {e}",
            )

    return router

