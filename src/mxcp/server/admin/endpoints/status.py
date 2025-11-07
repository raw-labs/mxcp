"""
Status and health endpoints.

Provides server status, health checks, and runtime information.
"""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from mxcp.sdk.core import PACKAGE_VERSION

from ..models import AdminSocketInfo, EndpointCounts, HealthResponse, ReloadInfo, StatusResponse
from ..protocol import AdminServerProtocol

logger = logging.getLogger(__name__)


def create_status_router(server: AdminServerProtocol) -> APIRouter:
    """
    Create status router with server dependency.

    Args:
        server: The MXCP server instance

    Returns:
        Configured APIRouter
    """
    router = APIRouter(tags=["status"])

    @router.get("/health", response_model=HealthResponse, summary="Health check")
    async def health() -> HealthResponse:
        """
        Simple health check endpoint.

        Returns current timestamp to confirm the service is responsive.
        """
        return HealthResponse(
            status="ok",
            timestamp=datetime.now(timezone.utc),
        )

    @router.get("/status", response_model=StatusResponse, summary="Get server status")
    async def get_status() -> StatusResponse:
        """
        Get comprehensive server status and health information.

        Returns runtime information including:
        - Version and uptime
        - Process ID and profile
        - Reload status
        - Endpoint counts
        - Admin socket metadata

        This endpoint is useful for monitoring and health checks.
        """
        try:
            # Calculate uptime
            uptime_seconds = (datetime.now(timezone.utc) - server._start_time).total_seconds()
            hours, remainder = divmod(int(uptime_seconds), 3600)
            minutes, seconds = divmod(remainder, 60)
            uptime_str = f"{hours}h{minutes}m{seconds}s"

            # Get endpoint counts
            try:
                endpoint_counts_dict = server.get_endpoint_counts()
                endpoint_counts = EndpointCounts(**endpoint_counts_dict)
            except Exception as e:
                logger.warning(f"Failed to get endpoint counts: {e}")
                endpoint_counts = EndpointCounts()

            # Get reload status
            reload_status_dict = server.reload_manager.get_status()
            reload_info = ReloadInfo(
                in_progress=reload_status_dict["processing"],
                draining=reload_status_dict["draining"],
                active_requests=reload_status_dict["active_requests"],
                last_reload=reload_status_dict.get("last_reload"),
                last_reload_status=reload_status_dict.get("last_reload_status"),
                last_reload_error=reload_status_dict.get("last_reload_error"),
            )

            return StatusResponse(
                version=PACKAGE_VERSION,
                uptime=uptime_str,
                uptime_seconds=int(uptime_seconds),
                pid=server._pid,
                profile=server.profile_name,
                mode="readonly" if server.readonly else "readwrite",
                debug=server.debug,
                endpoints=endpoint_counts,
                reload=reload_info,
                admin_socket=AdminSocketInfo(
                    path=str(server.admin_api._socket_path),
                ),
            )

        except Exception as e:
            logger.error(f"[admin] Status query failed: {e}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail=f"Failed to retrieve status: {e}",
            )

    return router

