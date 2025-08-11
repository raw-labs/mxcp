# -*- coding: utf-8 -*-
"""Type definitions for the MXCP SDK audit module.

This module contains all type definitions and dataclasses used by the audit system.
"""
from typing import Dict, Any, Optional, Literal, List, Callable, Tuple, Protocol, runtime_checkable, AsyncIterator
from datetime import datetime, timezone
from dataclasses import dataclass, asdict, field
from enum import Enum
from uuid import uuid4


# Type aliases
CallerType = Literal["cli", "http", "stdio", "api", "system", "unknown"]
EventType = Literal["tool", "resource", "prompt"]  # Backward compatibility
PolicyDecision = Literal["allow", "deny", "warn", "n/a"]
Status = Literal["success", "error"]

# New type aliases
RedactionFunc = Callable[[Any, Optional[Dict[str, Any]]], Any]


@dataclass
class FieldDefinition:
    """Definition of a field in an audit schema."""
    name: str
    type: str  # "string", "number", "boolean", "object", "array"
    required: bool = True
    description: Optional[str] = None
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
    options: Optional[Dict[str, Any]] = None  # Strategy-specific options





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
    fields: List[FieldDefinition] = field(default_factory=list)
    indexes: List[str] = field(default_factory=list)  # Fields to index for querying
    
    # Policies (defined at schema level)
    retention_days: Optional[int] = None
    evidence_level: EvidenceLevel = EvidenceLevel.BASIC
    field_redactions: List[FieldRedaction] = field(default_factory=list)
    extract_fields: List[str] = field(default_factory=list)  # For business context
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
    chain_breaks: List[str] = field(default_factory=list)  # Record IDs where chain breaks
    error: Optional[str] = None


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
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    trace_id: Optional[str] = None
    
    # Data (before redaction - schema defines what gets redacted)
    input_data: Dict[str, Any] = field(default_factory=dict)
    output_data: Optional[Any] = None
    error: Optional[str] = None
    
    # Policy evaluation results (but not the policies themselves)
    policies_evaluated: List[str] = field(default_factory=list)
    policy_decision: Optional[PolicyDecision] = None
    policy_reason: Optional[str] = None
    
    # Business context (extracted based on schema's extract_fields)
    business_context: Dict[str, Any] = field(default_factory=dict)
    
    # Backend-specific (populated by backend)
    prev_hash: Optional[str] = None
    record_hash: Optional[str] = None
    signature: Optional[str] = None
    
    def get_schema_id(self) -> str:
        """Get the schema identifier for this record."""
        return f"{self.schema_name}:v{self.schema_version}"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result = asdict(self)
        # Convert datetime to ISO format
        result['timestamp'] = self.timestamp.isoformat()
        return result


# Protocol definitions for extensibility
@runtime_checkable
class AuditBackend(Protocol):
    """Protocol for audit backends with schema management."""
    
    # Schema management methods
    async def create_schema(self, schema: AuditSchema) -> None:
        """Create or update a schema definition."""
        ...
    
    async def get_schema(
        self, 
        schema_name: str, 
        version: Optional[int] = None
    ) -> Optional[AuditSchema]:
        """Get a schema definition. If version is None, get latest active version."""
        ...
    
    async def list_schemas(
        self, 
        active_only: bool = True
    ) -> List[AuditSchema]:
        """List all schemas."""
        ...
    
    async def deactivate_schema(
        self, 
        schema_name: str, 
        version: Optional[int] = None
    ) -> None:
        """Deactivate a schema (soft delete)."""
        ...
    
    # Writing methods
    async def write_record(self, record: AuditRecord) -> str:
        """Write an audit record. Policies come from the referenced schema."""
        ...
    
    # Query methods
    async def query_records(
        self,
        schema_name: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        operation_types: Optional[List[str]] = None,
        operation_names: Optional[List[str]] = None,
        operation_status: Optional[List[Status]] = None,
        policy_decisions: Optional[List[PolicyDecision]] = None,
        user_ids: Optional[List[str]] = None,
        session_ids: Optional[List[str]] = None,
        trace_ids: Optional[List[str]] = None,
        business_context_filters: Optional[Dict[str, Any]] = None,
        limit: Optional[int] = None,
        offset: int = 0
    ) -> AsyncIterator[AuditRecord]:
        """Query audit records with filters.
        
        Yields records one at a time for memory-efficient processing.
        If limit is None, yields all matching records.
        """
        ...
    
    async def get_record(self, record_id: str) -> Optional[AuditRecord]:
        """Get a specific record by ID."""
        ...
    
    async def verify_integrity(
        self,
        start_record_id: str,
        end_record_id: str
    ) -> IntegrityResult:
        """Verify integrity between two records."""
        ...
    
    # Retention management
    async def apply_retention_policies(self) -> Dict[str, int]:
        """Apply retention policies. Returns count of records deleted per schema."""
        ...
    
    async def close(self) -> None:
        """Close backend and release resources."""
        ...
    
    def shutdown(self) -> None:
        """Synchronously shutdown the backend and flush any pending operations."""
        ... 