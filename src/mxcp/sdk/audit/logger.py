"""High-level audit logger for MXCP that delegates to backends."""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Optional, List, AsyncIterator

from .types import (
    CallerType, EventType, PolicyDecision, Status, AuditRecord, 
    AuditBackend, EvidenceLevel, IntegrityResult, AuditSchema,
    FieldDefinition, FieldRedaction, RedactionStrategy
)
from .backends import JSONLAuditWriter

logger = logging.getLogger(__name__)


# Default schemas for backward compatibility
DEFAULT_SCHEMAS = {
    "mxcp.legacy": AuditSchema(
        schema_name="mxcp.legacy",
        version=1,
        description="Legacy schema for backward compatibility",
        retention_days=90,
        evidence_level=EvidenceLevel.BASIC,
        fields=[
            FieldDefinition("operation_type", "string"),
            FieldDefinition("operation_name", "string"),
            FieldDefinition("input_data", "object"),
            FieldDefinition("output_data", "object", required=False),
            FieldDefinition("error", "string", required=False)
        ],
        indexes=["operation_type", "operation_name", "timestamp"]
    ),
    "mxcp.tools": AuditSchema(
        schema_name="mxcp.tools",
        version=1,
        description="Tool execution audit events",
        retention_days=90,
        evidence_level=EvidenceLevel.DETAILED,
        fields=[
            FieldDefinition("tool_name", "string"),
            FieldDefinition("parameters", "object", sensitive=True),
            FieldDefinition("result", "object", required=False),
            FieldDefinition("error", "string", required=False)
        ],
        indexes=["tool_name", "timestamp", "user_id"],
        extract_fields=["tool_name"]
    ),
    "mxcp.auth": AuditSchema(
        schema_name="mxcp.auth",
        version=1,
        description="Authentication and authorization events",
        retention_days=365,  # Keep auth events longer
        evidence_level=EvidenceLevel.REGULATORY,
        fields=[
            FieldDefinition("auth_type", "string"),
            FieldDefinition("user_id", "string"),
            FieldDefinition("session_id", "string"),
            FieldDefinition("ip_address", "string", sensitive=True),
            FieldDefinition("user_agent", "string")
        ],
        indexes=["auth_type", "user_id", "timestamp"],
        field_redactions=[
            FieldRedaction("ip_address", RedactionStrategy.FULL)
        ]
    )
}


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
        
        # Note: Default schemas are registered on first use to avoid async in __init__
        self._schemas_registered = False
    
    async def _ensure_schemas_registered(self):
        """Ensure default schemas are registered (called on first use)."""
        if not self._schemas_registered:
            await self._register_default_schemas()
            self._schemas_registered = True
    
    @classmethod
    async def jsonl(cls, log_path: Path, enabled: bool = True) -> 'AuditLogger':
        """Create audit logger with JSONL file backend.
        
        Args:
            log_path: Path to the JSONL audit log file
            enabled: Whether audit logging should be enabled (chooses backend)
            
        Returns:
            AuditLogger instance with appropriate backend
        """
        if enabled:
            from .backends.jsonl import JSONLAuditWriter
            instance = cls(JSONLAuditWriter(log_path=log_path))
        else:
            from .backends.noop import NoOpAuditBackend
            instance = cls(NoOpAuditBackend())
        
        await instance._ensure_schemas_registered()
        return instance
    
    @classmethod 
    async def disabled(cls) -> 'AuditLogger':
        """Create audit logger with no-op backend (all operations discarded).
        
        Returns:
            AuditLogger instance that discards all audit records
        """
        from .backends.noop import NoOpAuditBackend
        instance = cls(NoOpAuditBackend())
        await instance._ensure_schemas_registered()
        return instance
    
    async def _register_default_schemas(self):
        """Register default schemas with the backend."""
        for schema in DEFAULT_SCHEMAS.values():
            try:
                # Check if schema already exists
                existing = await self.backend.get_schema(schema.schema_name, schema.version)
                if not existing:
                    await self.backend.create_schema(schema)
                    logger.info(f"Registered default schema: {schema.get_schema_id()}")
            except Exception as e:
                logger.warning(f"Failed to register schema {schema.get_schema_id()}: {e}")
    
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
        policy_decision: PolicyDecision = "n/a",
        reason: Optional[str] = None,
        status: Status = "success",
        error: Optional[str] = None,
        schema_name: Optional[str] = None,
        output_data: Optional[Any] = None,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        trace_id: Optional[str] = None
    ):
        """Log an audit event.
        
        Args:
            caller_type: Source of the call (cli, http, stdio)
            event_type: Type of event (tool, resource, prompt)
            name: Name of the entity executed
            input_params: Input parameters
            duration_ms: Execution time in milliseconds
            policy_decision: Policy decision (allow, deny, warn, n/a)
            reason: Explanation if denied or warned
            status: Execution status (success, error)
            error: Error message if status is error
            schema_name: Name of the schema to use (defaults to "mxcp.legacy")
            output_data: Optional output data
            user_id: Optional user identifier
            session_id: Optional session identifier
            trace_id: Optional trace identifier
        """
        try:
            # Ensure default schemas are registered
            await self._ensure_schemas_registered()
            
            # Determine schema to use
            if not schema_name:
                # Map event types to default schemas
                if event_type == "tool":
                    schema_name = "mxcp.tools"
                else:
                    schema_name = "mxcp.legacy"
            
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
                trace_id=trace_id
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