"""Type definitions for the MXCP SDK audit module.

This module contains all type definitions and dataclasses used by the audit system.
"""

from collections.abc import AsyncIterator, Callable
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import (
    Any,
    Literal,
    Protocol,
    runtime_checkable,
)
from uuid import uuid4

# Type aliases
CallerType = Literal["cli", "http", "stdio", "api", "system", "unknown"]
EventType = Literal["tool", "resource", "prompt"]
PolicyDecision = Literal["allow", "deny", "warn"] | None
Status = Literal["success", "error"]

# New type aliases
RedactionFunc = Callable[[Any, dict[str, Any] | None], Any]


@dataclass
class FieldDefinition:
    """Definition of a field in an audit schema."""

    name: str
    type: str  # "string", "number", "boolean", "object", "array"
    required: bool = True
    description: str | None = None
    sensitive: bool = False  # If true, field may be redacted


class EvidenceLevel(Enum):
    """Level of evidence detail for audit records."""

    BASIC = "basic"  # Minimal information
    DETAILED = "detailed"  # More context
    REGULATORY = "regulatory"  # Compliance-focused
    FORENSIC = "forensic"  # Maximum detail


class RedactionStrategy(Enum):
    """Well-defined redaction strategies."""

    FULL = "full"  # Complete redaction: "[REDACTED]"
    PARTIAL = "partial"  # Partial: "ab***ef"
    HASH = "hash"  # Hash value: "sha256:abc123..."
    TRUNCATE = "truncate"  # Truncate: "hello wo..."
    EMAIL = "email"  # Email-specific: "u***@example.com"
    PRESERVE_TYPE = "preserve_type"  # Keep type: "" for strings, 0 for numbers


@dataclass
class FieldRedaction:
    """Configuration for redacting a specific field."""

    field_path: str  # Dot notation: "user.email", "config.password"
    strategy: RedactionStrategy  # Redaction strategy to apply
    options: dict[str, Any] | None = None  # Strategy-specific options


@dataclass
class AuditSchema:
    """Defines the structure and policies for a type of audit record.

    Schemas are defined at setup time and referenced by records at runtime.
    This allows for consistent policies across all records of the same type
    and avoids per-record policy overhead.
    """

    # Identity
    schema_name: str  # e.g., "authentication_events", "api_calls", "data_changes"
    version: int = 1
    description: str = ""

    # Structure
    fields: list[FieldDefinition] = field(default_factory=list)
    indexes: list[str] = field(default_factory=list)  # Fields to index for querying

    # Policies (defined at schema level)
    retention_days: int | None = None
    evidence_level: EvidenceLevel = EvidenceLevel.BASIC
    field_redactions: list[FieldRedaction] = field(default_factory=list)
    extract_fields: list[str] = field(default_factory=list)  # For business context
    require_signature: bool = False

    # Metadata
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    created_by: str = "system"
    active: bool = True  # Can be disabled without deletion

    def get_schema_id(self) -> str:
        """Get unique identifier for this schema."""
        return f"{self.schema_name}:v{self.version}"


@dataclass
class IntegrityResult:
    """Result of integrity verification."""

    valid: bool
    records_checked: int
    chain_breaks: list[str] = field(default_factory=list)  # Record IDs where chain breaks
    error: str | None = None


@dataclass
class AuditRecord:
    """Schema-based audit record.

    Records reference a schema that defines their structure and policies.
    This separation allows for consistent policy enforcement and efficient
    storage without per-record policy overhead.
    """

    # Schema reference (required)
    schema_name: str
    schema_version: int = 1

    # Identity
    record_id: str = field(default_factory=lambda: str(uuid4()))
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    # Operation details
    operation_type: str = "unknown"  # "tool", "resource", "prompt", etc.
    operation_name: str = ""
    operation_status: Status = "success"
    duration_ms: int = 0

    # Context
    caller_type: CallerType = "unknown"
    user_id: str | None = None
    session_id: str | None = None
    trace_id: str | None = None

    # Data (before redaction - schema defines what gets redacted)
    input_data: dict[str, Any] = field(default_factory=dict)
    output_data: Any | None = None
    error: str | None = None

    # Policy evaluation results (but not the policies themselves)
    policies_evaluated: list[str] = field(default_factory=list)
    policy_decision: PolicyDecision = None
    policy_reason: str | None = None

    # Business context (extracted based on schema's extract_fields)
    business_context: dict[str, Any] = field(default_factory=dict)

    # Backend-specific (populated by backend)
    prev_hash: str | None = None
    record_hash: str | None = None
    signature: str | None = None

    def get_schema_id(self) -> str:
        """Get the schema identifier for this record."""
        return f"{self.schema_name}:v{self.schema_version}"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result = asdict(self)
        # Convert datetime to ISO format
        result["timestamp"] = self.timestamp.isoformat()
        return result


# Protocol definitions for extensibility
@runtime_checkable
class AuditBackend(Protocol):
    """Protocol for audit backends with schema management."""

    # Schema management methods
    async def create_schema(self, schema: AuditSchema) -> None:
        """Create or update a schema definition."""
        ...

    async def get_schema(self, schema_name: str, version: int | None = None) -> AuditSchema | None:
        """Get a schema definition. If version is None, get latest active version."""
        ...

    async def list_schemas(self, active_only: bool = True) -> list[AuditSchema]:
        """List all schemas."""
        ...

    async def deactivate_schema(self, schema_name: str, version: int | None = None) -> None:
        """Deactivate a schema (soft delete)."""
        ...

    # Writing methods
    async def write_record(self, record: AuditRecord) -> str:
        """Write an audit record. Policies come from the referenced schema."""
        ...

    # Query methods
    def query_records(
        self,
        schema_name: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        operation_types: list[str] | None = None,
        operation_names: list[str] | None = None,
        operation_status: list[Status] | None = None,
        policy_decisions: list[PolicyDecision] | None = None,
        user_ids: list[str] | None = None,
        session_ids: list[str] | None = None,
        trace_ids: list[str] | None = None,
        business_context_filters: dict[str, Any] | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> AsyncIterator[AuditRecord]:
        """Query audit records with filters.

        Yields records one at a time for memory-efficient processing.
        If limit is None, yields all matching records.
        """
        ...

    async def get_record(self, record_id: str) -> AuditRecord | None:
        """Get a specific record by ID."""
        ...

    async def verify_integrity(self, start_record_id: str, end_record_id: str) -> IntegrityResult:
        """Verify integrity between two records."""
        ...

    # Retention management
    async def apply_retention_policies(self) -> dict[str, int]:
        """Apply retention policies. Returns count of records deleted per schema."""
        ...

    async def close(self) -> None:
        """Close backend and release resources."""
        ...
