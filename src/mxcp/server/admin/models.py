"""
Pydantic models for admin API requests and responses.

These models provide type safety, validation, and automatic OpenAPI documentation.
Models are organized by feature area to support future expansion.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

# ==============================================================================
# Status Models
# ==============================================================================


class EndpointCounts(BaseModel):
    """Counts of registered endpoints by type."""

    tools: int = Field(0, description="Number of registered tool endpoints")
    prompts: int = Field(0, description="Number of registered prompt endpoints")
    resources: int = Field(0, description="Number of registered resource endpoints")


class ReloadInfo(BaseModel):
    """Reload status information."""

    in_progress: bool = Field(..., description="Whether a reload is currently in progress")
    draining: bool = Field(..., description="Whether server is draining requests before reload")
    active_requests: int = Field(..., description="Number of currently active requests")
    last_reload: datetime | None = Field(None, description="Timestamp of last successful reload")
    last_reload_status: Literal["success", "error"] | None = Field(
        None, description="Status of last reload attempt"
    )
    last_reload_error: str | None = Field(None, description="Error message if last reload failed")


class AdminSocketInfo(BaseModel):
    """Admin API socket metadata."""

    path: str = Field(..., description="Unix socket path")


class StatusResponse(BaseModel):
    """
    Server status and health response.

    Provides comprehensive runtime information including version, uptime,
    and reload status.
    """

    status: Literal["ok"] = "ok"
    version: str = Field(..., description="MXCP package version")
    uptime: str = Field(..., description="Human-readable uptime (e.g., '2h12m35s')")
    uptime_seconds: int = Field(..., description="Uptime in seconds")
    pid: int = Field(..., description="Process ID")
    profile: str = Field(..., description="Active profile name")
    mode: Literal["readonly", "readwrite"] = Field(..., description="Database access mode")
    debug: bool = Field(..., description="Whether debug logging is enabled")
    reload: ReloadInfo = Field(..., description="Reload status information")
    admin_socket: AdminSocketInfo = Field(..., description="Admin socket metadata")


class HealthResponse(BaseModel):
    """Simple health check response."""

    status: Literal["ok"] = "ok"
    timestamp: datetime = Field(..., description="Current server time")


# ==============================================================================
# Reload Models
# ==============================================================================


class ReloadResponse(BaseModel):
    """
    Reload initiated response.

    Indicates that a configuration reload has been queued. The reload
    is asynchronous - use GET /status to check progress.
    """

    status: Literal["reload_initiated"] = "reload_initiated"
    timestamp: datetime = Field(..., description="Time when reload was initiated")
    reload_request_id: str = Field(..., description="Unique ID for this reload request")
    message: str = Field(
        "Reload request queued. Use GET /status to check progress.",
        description="Human-readable status message",
    )


# ==============================================================================
# Config Models
# ==============================================================================


class Features(BaseModel):
    """Feature flags and capabilities."""

    sql_tools: bool = Field(False, description="Whether SQL tools are enabled")
    audit_logging: bool = Field(False, description="Whether audit logging is enabled")
    telemetry: bool = Field(False, description="Whether telemetry is enabled")


class ConfigResponse(BaseModel):
    """
    Configuration metadata response.

    Provides information about loaded configuration including paths,
    enabled features, and plugin counts.
    """

    status: Literal["ok"] = "ok"
    project: str | None = Field(None, description="Project name from site config")
    profile: str = Field(..., description="Active profile name")
    repository_path: str | None = Field(None, description="Path to MXCP repository")
    duckdb_path: str | None = Field(None, description="Path to DuckDB database file")
    readonly: bool = Field(..., description="Whether database is in read-only mode")
    debug: bool = Field(..., description="Whether debug logging is enabled")
    endpoints: EndpointCounts = Field(..., description="Registered endpoint counts")
    features: Features = Field(..., description="Enabled features")
    transport: str | None = Field(None, description="Active transport protocol")


# ==============================================================================
# Error Models
# ==============================================================================


class ErrorResponse(BaseModel):
    """Error response for API failures."""

    error: str = Field(..., description="Error code")
    message: str | None = Field(None, description="Human-readable error message")
    detail: str | None = Field(None, description="Detailed error information (debug mode only)")


# ==============================================================================
# Endpoints Models
# ==============================================================================


class EndpointMetadata(BaseModel):
    """Metadata for a single endpoint."""

    path: str = Field(..., description="Relative path to endpoint file")
    type: Literal["tool", "resource", "prompt"] | None = Field(None, description="Endpoint type")
    name: str | None = Field(None, description="Endpoint name")
    description: str | None = Field(None, description="Endpoint description")
    language: str | None = Field(None, description="Implementation language (sql, python)")
    enabled: bool = Field(..., description="Whether endpoint is enabled")
    status: Literal["ok", "disabled", "error"] = Field(..., description="Endpoint status")
    error: str | None = Field(None, description="Error message if status is error")


class EndpointListResponse(BaseModel):
    """Response for listing all endpoints."""

    endpoints: list[EndpointMetadata] = Field(..., description="List of endpoint metadata")


# ==============================================================================
# Audit Log Models
# ==============================================================================


class AuditRecordResponse(BaseModel):
    """Audit record response model."""

    record_id: str = Field(..., description="Unique record identifier")
    timestamp: str = Field(..., description="ISO 8601 timestamp")
    schema_name: str = Field(..., description="Schema name")
    schema_version: int = Field(..., description="Schema version")
    operation_type: str = Field(..., description="Operation type (tool, resource, prompt)")
    operation_name: str = Field(..., description="Operation name")
    operation_status: str = Field(..., description="Operation status (success, error)")
    duration_ms: int | None = Field(None, description="Duration in milliseconds")
    caller_type: str | None = Field(None, description="Caller type (http, stdio)")
    user_id: str | None = Field(None, description="User ID")
    session_id: str | None = Field(None, description="Session ID")
    trace_id: str | None = Field(None, description="Trace ID")
    policy_decision: str | None = Field(None, description="Policy decision")
    error_message: str | None = Field(None, description="Error message if failed")


class AuditQueryResponse(BaseModel):
    """Response for audit log queries."""

    records: list[AuditRecordResponse] = Field(..., description="List of audit records")
    count: int = Field(..., description="Number of records returned")


class AuditStatsResponse(BaseModel):
    """Audit log statistics response."""

    total_records: int = Field(..., description="Total number of records")
    by_type: dict[str, int] = Field(..., description="Count by operation type")
    by_status: dict[str, int] = Field(..., description="Count by status")
    by_policy: dict[str, int] = Field(..., description="Count by policy decision")
    earliest_timestamp: str | None = Field(None, description="Earliest record timestamp")
    latest_timestamp: str | None = Field(None, description="Latest record timestamp")


# ==============================================================================
# System Metrics Models
# ==============================================================================


class SystemInfoResponse(BaseModel):
    """Basic system information."""

    boot_time_seconds: int = Field(..., description="System boot time (Unix timestamp)")
    cpu_count_physical: int = Field(..., description="Number of physical CPU cores")
    cpu_count_logical: int = Field(..., description="Number of logical CPU cores")
    memory_total_bytes: int = Field(..., description="Total system memory in bytes")


class CPUStatsResponse(BaseModel):
    """CPU usage statistics."""

    percent: float = Field(..., description="Overall CPU usage percentage")
    per_cpu_percent: list[float] = Field(..., description="Per-core CPU usage percentages")
    load_avg_1min: float = Field(..., description="1-minute load average")
    load_avg_5min: float = Field(..., description="5-minute load average")
    load_avg_15min: float = Field(..., description="15-minute load average")


class MemoryStatsResponse(BaseModel):
    """Memory usage statistics."""

    total_bytes: int = Field(..., description="Total memory in bytes")
    available_bytes: int = Field(..., description="Available memory in bytes")
    used_bytes: int = Field(..., description="Used memory in bytes")
    free_bytes: int = Field(..., description="Free memory in bytes")
    percent: float = Field(..., description="Memory usage percentage")
    swap_total_bytes: int = Field(..., description="Total swap memory in bytes")
    swap_used_bytes: int = Field(..., description="Used swap memory in bytes")
    swap_free_bytes: int = Field(..., description="Free swap memory in bytes")
    swap_percent: float = Field(..., description="Swap usage percentage")
    mxcp_process_rss_bytes: int = Field(..., description="MXCP process RSS memory in bytes")
    mxcp_process_vms_bytes: int = Field(..., description="MXCP process VMS memory in bytes")


class DiskStatsResponse(BaseModel):
    """Disk usage and I/O statistics."""

    total_bytes: int = Field(..., description="Total disk space in bytes")
    used_bytes: int = Field(..., description="Used disk space in bytes")
    free_bytes: int = Field(..., description="Free disk space in bytes")
    percent: float = Field(..., description="Disk usage percentage")
    read_bytes: int = Field(..., description="Total bytes read from disk")
    write_bytes: int = Field(..., description="Total bytes written to disk")
    read_count: int = Field(..., description="Total number of read operations")
    write_count: int = Field(..., description="Total number of write operations")


class NetworkStatsResponse(BaseModel):
    """Network I/O statistics."""

    bytes_sent: int = Field(..., description="Total bytes sent")
    bytes_recv: int = Field(..., description="Total bytes received")
    packets_sent: int = Field(..., description="Total packets sent")
    packets_recv: int = Field(..., description="Total packets received")
    errin: int = Field(..., description="Total incoming errors")
    errout: int = Field(..., description="Total outgoing errors")
    dropin: int = Field(..., description="Total incoming packets dropped")
    dropout: int = Field(..., description="Total outgoing packets dropped")


class ProcessStatsResponse(BaseModel):
    """MXCP process statistics."""

    pid: int = Field(..., description="Process ID")
    status: str = Field(..., description="Process status")
    cpu_percent: float = Field(..., description="CPU usage percentage")
    memory_rss_bytes: int = Field(..., description="Resident Set Size in bytes")
    memory_vms_bytes: int = Field(..., description="Virtual Memory Size in bytes")
    num_threads: int = Field(..., description="Number of threads")
    num_fds: int = Field(..., description="Number of file descriptors")
