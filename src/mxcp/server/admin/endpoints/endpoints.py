"""
Endpoints discovery API.

Provides endpoints for discovering and listing all registered endpoints
(tools, resources, prompts) with their metadata.
"""

import logging
from typing import Literal

from fastapi import APIRouter, HTTPException

from mxcp.server.definitions.endpoints.models import (
    PromptDefinitionModel,
    ResourceDefinitionModel,
    ToolDefinitionModel,
)

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
                    enabled = True

                    name: str | None
                    description: str | None
                    language: str | None

                    if endpoint_def.tool is not None:
                        tool_def: ToolDefinitionModel = endpoint_def.tool
                        endpoint_type = "tool"
                        name = tool_def.name
                        description = tool_def.description
                        language = tool_def.language
                        enabled = tool_def.enabled
                    elif endpoint_def.resource is not None:
                        resource_def: ResourceDefinitionModel = endpoint_def.resource
                        endpoint_type = "resource"
                        name = resource_def.name or resource_def.uri
                        description = resource_def.description
                        language = resource_def.language
                        enabled = resource_def.enabled
                    elif endpoint_def.prompt is not None:
                        prompt_def: PromptDefinitionModel = endpoint_def.prompt
                        endpoint_type = "prompt"
                        name = prompt_def.name
                        description = prompt_def.description
                        language = None
                        enabled = prompt_def.enabled
                    else:
                        endpoint_type = None
                        name = None
                        description = None
                        language = None

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
