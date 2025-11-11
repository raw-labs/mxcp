"""
API endpoints for admin interface.

Endpoints are organized by feature area to support future expansion.
Each endpoint module can contain multiple related routes.
"""

from .audit import create_audit_router
from .config import create_config_router
from .endpoints import create_endpoints_router
from .reload import create_reload_router
from .status import create_status_router
from .system import create_system_router

__all__ = [
    "create_status_router",
    "create_reload_router",
    "create_config_router",
    "create_endpoints_router",
    "create_system_router",
    "create_audit_router",
]
