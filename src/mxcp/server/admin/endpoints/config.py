"""
Configuration query endpoints.

Provides endpoints for retrieving configuration metadata and settings.
"""

import logging

from fastapi import APIRouter, HTTPException

from ..models import ConfigResponse, EndpointCounts, Features
from ..protocol import AdminServerProtocol

logger = logging.getLogger(__name__)


def create_config_router(server: AdminServerProtocol) -> APIRouter:
    """
    Create config router with server dependency.

    Args:
        server: The MXCP server instance

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
            config_info = server.get_config_info()
            endpoint_counts_dict = server.get_endpoint_counts()

            return ConfigResponse(
                project=server.site_config.get("project"),
                profile=server.profile_name,
                repository_path=config_info.get("repository_path"),
                duckdb_path=config_info.get("duckdb_path"),
                readonly=server.readonly,
                debug=server.debug,
                endpoints=EndpointCounts(**endpoint_counts_dict),
                features=Features(
                    sql_tools=config_info.get("sql_tools_enabled", False),
                    audit_logging=config_info.get("audit_enabled", False),
                    telemetry=config_info.get("telemetry_enabled", False),
                ),
                transport=config_info.get("transport"),
            )

        except Exception as e:
            logger.error(f"[admin] Config query failed: {e}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail=f"Config query failed: {e}",
            )

    return router

