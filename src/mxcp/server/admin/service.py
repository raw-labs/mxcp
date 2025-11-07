"""
Admin API service implementation.

Simple service class that receives RAWMCP and provides admin operations.
No protocols, no abstractions - just direct, simple code.
"""

from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .models import ConfigResponse, EndpointCounts, Features

if TYPE_CHECKING:
    from mxcp.server.core.reload import ReloadRequest
    from mxcp.server.interfaces.server.mcp import RAWMCP


class AdminService:
    """
    Admin API service - receives RAWMCP and provides admin operations.

    This service exposes helpers so endpoints don't need to know RAWMCP's internals.
    Only AdminService needs to know about RAWMCP's structure.
    """

    def __init__(self, server: "RAWMCP"):
        """Initialize admin service with RAWMCP server instance."""
        self._server = server

    # Expose commonly-used properties
    @property
    def debug(self) -> bool:
        """Whether debug mode is enabled."""
        return self._server.debug

    @property
    def readonly(self) -> bool:
        """Whether server is in read-only mode."""
        return self._server.readonly

    @property
    def profile_name(self) -> str:
        """Active profile name."""
        return self._server.profile_name

    @property
    def start_time(self) -> datetime:
        """Server start time."""
        return self._server._start_time

    @property
    def pid(self) -> int:
        """Server process ID."""
        return self._server._pid

    @property
    def socket_path(self) -> Path:
        """Admin API socket path."""
        return self._server.admin_api._socket_path

    def get_endpoint_counts(self) -> dict[str, int]:
        """Get counts of registered endpoints by type."""
        return self._server.get_endpoint_counts()

    def get_reload_status(self) -> dict[str, Any]:
        """Get current reload status."""
        return self._server.reload_manager.get_status()

    def reload_configuration(self) -> "ReloadRequest":
        """Trigger a configuration reload."""
        return self._server.reload_configuration()

    def get_config_snapshot(self) -> ConfigResponse:
        """
        Create a config snapshot from RAWMCP's current state.

        Reads public fields directly - no intermediate types needed.
        """
        return ConfigResponse(
            project=self._server.site_config.get("project"),
            profile=self._server.profile_name,
            repository_path=(
                str(self._server.runtime_environment.duckdb_runtime.database_config.path)
                if self._server.runtime_environment
                else None
            ),
            duckdb_path=(
                str(self._server.runtime_environment.duckdb_runtime.database_config.path)
                if self._server.runtime_environment
                else None
            ),
            readonly=self._server.readonly,
            debug=self._server.debug,
            endpoints=EndpointCounts(**self.get_endpoint_counts()),
            features=Features(
                sql_tools=bool(self._server.enable_sql_tools),
                audit_logging=self._server.audit_logger is not None,
                telemetry=self._server.telemetry_enabled,
            ),
            transport=self._server.transport,
        )
