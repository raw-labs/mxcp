"""
FastAPI application for MXCP admin interface.

This module creates the FastAPI application with all admin endpoints.
"""

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from mxcp.sdk.core import PACKAGE_VERSION

from .models import ErrorResponse
from .protocol import AdminServerProtocol

logger = logging.getLogger(__name__)


def create_admin_app(server: AdminServerProtocol) -> FastAPI:
    """
    Create the FastAPI admin application.

    Args:
        server: The MXCP server instance implementing AdminServerProtocol

    Returns:
        Configured FastAPI application with all admin endpoints
    """
    app = FastAPI(
        title="MXCP Admin API",
        description="""
Local administration interface for MXCP server.

This API provides management and monitoring capabilities for MXCP instances
via Unix domain socket. All operations are local-only for security.

**Features:**
- Server status and health monitoring
- Configuration reload (hot reload)
- Configuration metadata queries

**Security:** Unix socket with 0600 permissions (owner-only access)
        """.strip(),
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    # Global exception handler
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        """Handle unexpected exceptions."""
        logger.error(f"Unhandled exception in admin API: {exc}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content=ErrorResponse(
                error="internal_error",
                message="Internal server error",
                detail=str(exc) if server.debug else None,
            ).model_dump(),
        )

    # Include routers with server dependency
    from .endpoints import create_config_router, create_reload_router, create_status_router

    app.include_router(create_status_router(server))
    app.include_router(create_reload_router(server))
    app.include_router(create_config_router(server))

    @app.get("/", include_in_schema=False)
    async def root() -> dict[str, str]:
        """Root endpoint with API information."""
        return {
            "service": "mxcp-admin",
            "version": PACKAGE_VERSION,
            "docs": "/docs",
            "openapi": "/openapi.json",
        }

    return app

