"""
Admin API service implementation.

Simple service class that receives RAWMCP and provides admin operations.
No protocols, no abstractions - just direct, simple code.
"""

from collections.abc import AsyncIterator
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from mxcp.sdk.audit.backends.noop import NoOpAuditBackend
from mxcp.server.definitions.endpoints.models import EndpointDefinitionModel

from .models import ConfigResponse, EndpointCounts, Features

if TYPE_CHECKING:
    from mxcp.sdk.audit._types import AuditRecord
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
        site_config_obj = self._server.site_config
        project_name = site_config_obj.project
        return ConfigResponse(
            project=project_name,
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
                audit_logging=self.is_audit_enabled(),
                telemetry=self._server.telemetry_enabled,
            ),
            transport=self._server.transport,
        )

    def discover_endpoints(self) -> list[tuple[Path, EndpointDefinitionModel | None, str | None]]:
        """
        Discover all endpoints using the server's endpoint loader.

        Returns:
            List of tuples (path, endpoint_def, error) where:
            - path: Path to the endpoint file
            - endpoint_def: Parsed endpoint definition (or None if error)
            - error: Error message (or None if successful)
        """
        return self._server.loader.discover_endpoints()

    def is_audit_enabled(self) -> bool:
        """Check if audit logging is enabled."""
        # Check if audit logger exists AND is not a no-op backend
        if self._server.audit_logger is None:
            return False
        # Check if it's a no-op backend by checking the backend type
        return not isinstance(self._server.audit_logger.backend, NoOpAuditBackend)

    async def query_audit_records(
        self,
        schema_name: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        operation_types: list[str] | None = None,
        operation_names: list[str] | None = None,
        operation_status: list[str] | None = None,
        user_ids: list[str] | None = None,
        trace_ids: list[str] | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> AsyncIterator["AuditRecord"]:
        """
        Query audit records with filters.

        This is a convenience method that delegates to the audit logger if available.
        Returns an async iterator of AuditRecord objects.

        Args:
            schema_name: Filter by schema name
            start_time: Filter by start time
            end_time: Filter by end time
            operation_types: Filter by operation types
            operation_names: Filter by operation names
            operation_status: Filter by operation status
            user_ids: Filter by user IDs
            trace_ids: Filter by trace IDs
            limit: Maximum number of records to return
            offset: Number of records to skip

        Yields:
            AuditRecord objects matching the filters
        """
        if not self._server.audit_logger:
            return

        async for record in self._server.audit_logger.query_records(
            schema_name=schema_name,
            start_time=start_time,
            end_time=end_time,
            operation_types=operation_types,
            operation_names=operation_names,
            operation_status=operation_status,
            user_ids=user_ids,
            trace_ids=trace_ids,
            limit=limit,
            offset=offset,
        ):
            yield record
