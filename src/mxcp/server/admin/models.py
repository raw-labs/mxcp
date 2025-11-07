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
    reload status, and endpoint counts.
    """

    status: Literal["ok"] = "ok"
    version: str = Field(..., description="MXCP package version")
    uptime: str = Field(..., description="Human-readable uptime (e.g., '2h12m35s')")
    uptime_seconds: int = Field(..., description="Uptime in seconds")
    pid: int = Field(..., description="Process ID")
    profile: str = Field(..., description="Active profile name")
    mode: Literal["readonly", "readwrite"] = Field(..., description="Database access mode")
    debug: bool = Field(..., description="Whether debug logging is enabled")
    endpoints: EndpointCounts = Field(..., description="Registered endpoint counts")
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
