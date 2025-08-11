"""High-level audit logger for MXCP that delegates to backends."""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncIterator, Dict, List, Optional

from ._types import (
    AuditBackend,
    AuditRecord,
    AuditSchema,
    CallerType,
    EventType,
    EvidenceLevel,
    FieldDefinition,
    FieldRedaction,
    IntegrityResult,
    PolicyDecision,
    RedactionStrategy,
    Status,
)
from .backends import JSONLAuditWriter

logger = logging.getLogger(__name__)


class AuditLogger:
    """High-level audit logger that delegates to a backend.

    This class provides a consistent API for audit logging and querying
    while allowing different backend implementations (JSONL, PostgreSQL, etc.).
    """

    def __init__(self, backend: AuditBackend):
        """Initialize the audit logger with a specific backend.

        Args:
            backend: The audit backend to use for storage and querying
        """
        self.backend = backend

        logger.info(f"Audit logger initialized with backend: {type(self.backend).__name__}")

    @classmethod
    async def jsonl(cls, log_path: Path, enabled: bool = True) -> "AuditLogger":
        """Create audit logger with JSONL file backend.

        Args:
            log_path: Path to the JSONL audit log file
            enabled: Whether audit logging should be enabled (chooses backend)

        Returns:
            AuditLogger instance with appropriate backend
        """
        if enabled:
            from .backends.jsonl import JSONLAuditWriter

            return cls(JSONLAuditWriter(log_path=log_path))
        else:
            from .backends.noop import NoOpAuditBackend

            return cls(NoOpAuditBackend())

    @classmethod
    async def disabled(cls) -> "AuditLogger":
        """Create audit logger with no-op backend (all operations discarded).

        Returns:
            AuditLogger instance that discards all audit records
        """
        from .backends.noop import NoOpAuditBackend

        return cls(NoOpAuditBackend())

    # Schema management methods

    async def create_schema(self, schema: AuditSchema):
        """Create or update a schema."""
        return await self.backend.create_schema(schema)

    async def get_schema(self, schema_name: str, version: Optional[int] = None):
        """Get a schema definition."""
        return await self.backend.get_schema(schema_name, version)

    async def list_schemas(self, active_only: bool = True):
        """List all schemas."""
        return await self.backend.list_schemas(active_only)

    async def log_event(
        self,
        caller_type: CallerType,
        event_type: EventType,
        name: str,
        input_params: Dict[str, Any],
        duration_ms: int,
        schema_name: str,
        policy_decision: PolicyDecision = "n/a",
        reason: Optional[str] = None,
        status: Status = "success",
        error: Optional[str] = None,
        output_data: Optional[Any] = None,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        trace_id: Optional[str] = None,
    ):
        """Log an audit event.

        Args:
            caller_type: Source of the call (cli, http, stdio)
            event_type: Type of event (tool, resource, prompt)
            name: Name of the entity executed
            input_params: Input parameters
            duration_ms: Execution time in milliseconds
            schema_name: Name of the schema to use
            policy_decision: Policy decision (allow, deny, warn, n/a)
            reason: Explanation if denied or warned
            status: Execution status (success, error)
            error: Error message if status is error
            output_data: Optional output data
            user_id: Optional user identifier
            session_id: Optional session identifier
            trace_id: Optional trace identifier
        """
        try:
            # Create audit record with schema reference
            record = AuditRecord(
                schema_name=schema_name,
                schema_version=1,  # Default to version 1
                timestamp=datetime.now(timezone.utc),
                caller_type=caller_type,
                operation_type=event_type,
                operation_name=name,
                input_data=input_params,
                output_data=output_data,
                duration_ms=duration_ms,
                policy_decision=policy_decision,
                policy_reason=reason,
                operation_status=status,
                error=error,
                user_id=user_id,
                session_id=session_id,
                trace_id=trace_id,
            )

            # Delegate to backend - clean async interface
            await self.backend.write_record(record)

        except Exception as e:
            logger.error(f"Failed to log audit event: {e}")

    # Query methods - delegate to backend

    async def query_records(self, **kwargs) -> AsyncIterator[AuditRecord]:
        """Query audit records. See backend.query_records for parameters.

        Yields records one at a time for memory-efficient processing.
        """
        async for record in self.backend.query_records(**kwargs):
            yield record

    async def get_record(self, record_id: str):
        """Get a specific record by ID."""
        return await self.backend.get_record(record_id)

    async def verify_integrity(self, start_record_id: str, end_record_id: str):
        """Verify integrity between two records."""
        return await self.backend.verify_integrity(start_record_id, end_record_id)

    async def apply_retention_policies(self):
        """Apply retention policies to remove old records."""
        return await self.backend.apply_retention_policies()

    def shutdown(self):
        """Shutdown the logger and its backend."""
        logger.info("Shutting down audit logger...")

        # All backends must implement shutdown()
        self.backend.shutdown()

        logger.info("Audit logger shutdown complete")
