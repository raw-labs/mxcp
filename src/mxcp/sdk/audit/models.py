"""Pydantic models for MXCP SDK audit module.

This module contains all Pydantic model definitions used by the audit system.
"""

from collections.abc import AsyncIterator, Callable
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal, Protocol, runtime_checkable
from uuid import uuid4

from pydantic import ConfigDict, Field

from mxcp.sdk.models import SdkBaseModel

# Type aliases
CallerType = Literal["cli", "http", "stdio", "api", "system", "unknown"]
EventType = Literal["tool", "resource", "prompt"]
PolicyDecision = Literal["allow", "deny", "warn"] | None
Status = Literal["success", "error"]

# New type aliases
RedactionFunc = Callable[[Any, dict[str, Any] | None], Any]


class FieldDefinitionModel(SdkBaseModel):
    """Definition of a field in an audit schema.

    Attributes:
        name: Field name.
        type: Field type ("string", "number", "boolean", "object", "array").
        required: Whether the field is required.
        description: Optional field description.
        sensitive: If true, field may be redacted.
    """

    model_config = ConfigDict(extra="forbid", frozen=False)

    name: str
    type: str  # "string", "number", "boolean", "object", "array"
    required: bool = True
    description: str | None = None
    sensitive: bool = False


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


class FieldRedactionModel(SdkBaseModel):
    """Configuration for redacting a specific field.

    Attributes:
        field_path: Dot notation path (e.g., "user.email", "config.password").
        strategy: Redaction strategy to apply.
        options: Strategy-specific options.
    """

    model_config = ConfigDict(extra="forbid", frozen=False)

    field_path: str
    strategy: RedactionStrategy
    options: dict[str, Any] | None = None


def _utc_now() -> datetime:
    """Return current UTC time."""
    return datetime.now(timezone.utc)


class AuditSchemaModel(SdkBaseModel):
    """Defines the structure and policies for a type of audit record.

    Schemas are defined at setup time and referenced by records at runtime.
    This allows for consistent policies across all records of the same type
    and avoids per-record policy overhead.

    Attributes:
        schema_name: Schema identifier (e.g., "authentication_events", "api_calls").
        version: Schema version.
        description: Schema description.
        fields: List of field definitions.
        indexes: Fields to index for querying.
        retention_days: Days to retain records.
        evidence_level: Level of evidence detail.
        field_redactions: Field redaction configurations.
        extract_fields: Fields to extract for business context.
        require_signature: Whether to require signature.
        created_at: Creation timestamp.
        created_by: Creator identifier.
        active: Whether schema is active.
    """

    model_config = ConfigDict(extra="forbid", frozen=False)

    # Identity
    schema_name: str
    version: int = 1
    description: str = ""

    # Structure
    fields: list[FieldDefinitionModel] = Field(default_factory=list)
    indexes: list[str] = Field(default_factory=list)

    # Policies
    retention_days: int | None = None
    evidence_level: EvidenceLevel = EvidenceLevel.BASIC
    field_redactions: list[FieldRedactionModel] = Field(default_factory=list)
    extract_fields: list[str] = Field(default_factory=list)
    require_signature: bool = False

    # Metadata
    created_at: datetime = Field(default_factory=_utc_now)
    created_by: str = "system"
    active: bool = True

    def get_schema_id(self) -> str:
        """Get unique identifier for this schema."""
        return f"{self.schema_name}:v{self.version}"


class IntegrityResultModel(SdkBaseModel):
    """Result of integrity verification.

    Attributes:
        valid: Whether integrity check passed.
        records_checked: Number of records checked.
        chain_breaks: Record IDs where chain breaks occurred.
        error: Error message if any.
    """

    model_config = ConfigDict(extra="forbid", frozen=False)

    valid: bool
    records_checked: int
    chain_breaks: list[str] = Field(default_factory=list)
    error: str | None = None


def _new_uuid() -> str:
    """Generate a new UUID string."""
    return str(uuid4())


class AuditRecordModel(SdkBaseModel):
    """Schema-based audit record.

    Records reference a schema that defines their structure and policies.
    This separation allows for consistent policy enforcement and efficient
    storage without per-record policy overhead.

    Attributes:
        schema_name: Referenced schema name.
        schema_version: Referenced schema version.
        record_id: Unique record identifier.
        timestamp: Record timestamp.
        operation_type: Type of operation.
        operation_name: Name of operation.
        operation_status: Status of operation.
        duration_ms: Duration in milliseconds.
        caller_type: Type of caller.
        user_id: User identifier.
        session_id: Session identifier.
        trace_id: Trace identifier.
        input_data: Input data (before redaction).
        output_data: Output data.
        error: Error message if any.
        policies_evaluated: List of evaluated policies.
        policy_decision: Policy decision result.
        policy_reason: Reason for policy decision.
        business_context: Extracted business context.
        prev_hash: Previous record hash.
        record_hash: Current record hash.
        signature: Record signature.
    """

    model_config = ConfigDict(extra="forbid", frozen=False)

    # Schema reference
    schema_name: str
    schema_version: int = 1

    # Identity
    record_id: str = Field(default_factory=_new_uuid)
    timestamp: datetime = Field(default_factory=_utc_now)

    # Operation details
    operation_type: str = "unknown"
    operation_name: str = ""
    operation_status: Status = "success"
    duration_ms: int = 0

    # Context
    caller_type: CallerType = "unknown"
    user_id: str | None = None
    session_id: str | None = None
    trace_id: str | None = None

    # Data
    input_data: dict[str, Any] = Field(default_factory=dict)
    output_data: Any | None = None
    error: str | None = None

    # Policy evaluation results
    policies_evaluated: list[str] = Field(default_factory=list)
    policy_decision: PolicyDecision = None
    policy_reason: str | None = None

    # Business context
    business_context: dict[str, Any] = Field(default_factory=dict)

    # Backend-specific
    prev_hash: str | None = None
    record_hash: str | None = None
    signature: str | None = None

    def get_schema_id(self) -> str:
        """Get the schema identifier for this record."""
        return f"{self.schema_name}:v{self.schema_version}"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result = self.model_dump(mode="python")
        # Convert datetime to ISO format
        result["timestamp"] = self.timestamp.isoformat()
        return result


# Protocol definitions for extensibility
@runtime_checkable
class AuditBackend(Protocol):
    """Protocol for audit backends with schema management."""

    # Schema management methods
    async def create_schema(self, schema: AuditSchemaModel) -> None:
        """Create or update a schema definition."""
        ...

    async def get_schema(
        self, schema_name: str, version: int | None = None
    ) -> AuditSchemaModel | None:
        """Get a schema definition. If version is None, get latest active version."""
        ...

    async def list_schemas(self, active_only: bool = True) -> list[AuditSchemaModel]:
        """List all schemas."""
        ...

    async def deactivate_schema(self, schema_name: str, version: int | None = None) -> None:
        """Deactivate a schema (soft delete)."""
        ...

    # Writing methods
    async def write_record(self, record: AuditRecordModel) -> str:
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
    ) -> AsyncIterator[AuditRecordModel]:
        """Query audit records with filters.

        Yields records one at a time for memory-efficient processing.
        If limit is None, yields all matching records.
        """
        ...

    async def get_record(self, record_id: str) -> AuditRecordModel | None:
        """Get a specific record by ID."""
        ...

    async def verify_integrity(
        self, start_record_id: str, end_record_id: str
    ) -> IntegrityResultModel:
        """Verify integrity between two records."""
        ...

    # Retention management
    async def apply_retention_policies(self) -> dict[str, int]:
        """Apply retention policies. Returns count of records deleted per schema."""
        ...

    async def close(self) -> None:
        """Close backend and release resources."""
        ...
