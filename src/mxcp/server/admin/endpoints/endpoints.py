"""
Endpoints discovery API.

Provides endpoints for discovering and listing all registered endpoints
(tools, resources, prompts) with their metadata.
"""

import logging
from typing import Literal

from fastapi import APIRouter, HTTPException

from ..models import EndpointListResponse, EndpointMetadata
from ..service import AdminService

logger = logging.getLogger(__name__)


def create_endpoints_router(admin_service: AdminService) -> APIRouter:
    """
    Create endpoints router with admin service dependency.

    Args:
        admin_service: The admin service wrapping RAWMCP

    Returns:
        Configured APIRouter
    """
    router = APIRouter(tags=["endpoints"])

    @router.get("/endpoints", response_model=EndpointListResponse, summary="List all endpoints")
    async def list_endpoints() -> EndpointListResponse:
        """
        List all registered endpoints with metadata.

        Discovers and returns metadata for all endpoint definitions (tools, resources, prompts)
        loaded in the MXCP instance. Includes:
        - Endpoint type (tool, resource, prompt)
        - Name, description, language
        - Enabled status

        This is useful for:
        - Dashboard displays
        - Monitoring which endpoints are available
        - Integration with external systems

        Note: Aggregations (counts by type/status) can be computed by the client from this list.
        """
        try:
            endpoints = []

            # Discover all endpoints via the server's endpoint loader
            discovered = admin_service.discover_endpoints()

            for path, endpoint_def, error in discovered:
                if error:
                    # Include failed endpoints with error info
                    endpoints.append(
                        EndpointMetadata(
                            path=str(path),
                            type=None,
                            name=None,
                            description=None,
                            language=None,
                            enabled=False,
                            status="error",
                            error=error,
                        )
                    )
                elif endpoint_def:
                    # Extract endpoint data from definition
                    endpoint_type: Literal["tool", "resource", "prompt"] | None = None
                    endpoint_data = None
                    enabled = True

                    if "tool" in endpoint_def:
                        endpoint_type = "tool"
                        endpoint_data = endpoint_def["tool"]
                    elif "resource" in endpoint_def:
                        endpoint_type = "resource"
                        endpoint_data = endpoint_def["resource"]
                    elif "prompt" in endpoint_def:
                        endpoint_type = "prompt"
                        endpoint_data = endpoint_def["prompt"]

                    if endpoint_data:
                        enabled = bool(endpoint_data.get("enabled", True))

                    # Extract metadata
                    name = endpoint_data.get("name") if endpoint_data else None
                    description = endpoint_data.get("description") if endpoint_data else None
                    language = endpoint_data.get("language") if endpoint_data else None

                    endpoints.append(
                        EndpointMetadata(
                            path=str(path),
                            type=endpoint_type,
                            name=name,
                            description=description,
                            language=language,
                            enabled=enabled,
                            status="ok" if enabled else "disabled",
                            error=None,
                        )
                    )

            return EndpointListResponse(endpoints=endpoints)

        except Exception as e:
            logger.error(f"[admin] Failed to list endpoints: {e}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail=f"Failed to list endpoints: {e}",
            ) from e

    return router
