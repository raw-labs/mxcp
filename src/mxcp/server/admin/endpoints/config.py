"""
Configuration query endpoints.

Provides endpoints for retrieving configuration metadata and settings.
"""

import logging

from fastapi import APIRouter, HTTPException

from ..models import ConfigResponse
from ..service import AdminService

logger = logging.getLogger(__name__)


def create_config_router(admin_service: AdminService) -> APIRouter:
    """
    Create config router with admin service dependency.

    Args:
        admin_service: The admin service wrapping RAWMCP

    Returns:
        Configured APIRouter
    """
    router = APIRouter(tags=["config"])

    @router.get("/config", response_model=ConfigResponse, summary="Get configuration metadata")
    async def get_config() -> ConfigResponse:
        """
        Get configuration metadata and settings.

        Returns information about the loaded configuration including:
        - Project and profile settings
        - Database paths and access mode
        - Registered endpoint counts
        - Enabled features
        - Transport protocol

        This endpoint is useful for understanding the current server configuration
        without exposing sensitive values.
        """
        try:
            return admin_service.get_config_snapshot()
        except Exception as e:
            logger.error(f"[admin] Config query failed: {e}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail=f"Config query failed: {e}",
            ) from e

    return router
