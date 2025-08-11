"""No-operation audit backend for disabled audit logging."""

from typing import List, Optional, Dict, Any, AsyncIterator
from datetime import datetime
from pathlib import Path

from ..types import AuditBackend, AuditRecord, AuditSchema, IntegrityResult, Status, PolicyDecision


class NoOpAuditBackend:
    """No-operation audit backend that discards all audit records.
    
    Used when audit logging is disabled. All operations are no-ops
    that return appropriate empty/default values.
    """
    
    def __init__(self):
        """Initialize the no-op backend."""
        pass
    
    async def create_schema(self, schema: AuditSchema) -> None:
        """No-op schema creation."""
        pass
    
    async def get_schema(self, schema_name: str, version: Optional[int] = None) -> Optional[AuditSchema]:
        """No-op schema retrieval."""
        return None
    
    async def list_schemas(self, active_only: bool = True) -> List[AuditSchema]:
        """No-op schema listing."""
        return []
    
    async def deactivate_schema(self, schema_name: str, version: Optional[int] = None) -> None:
        """No-op schema deactivation."""
        pass
    
    async def apply_retention_policies(self) -> Dict[str, Any]:
        """No-op retention policy application."""
        return {"processed": 0, "deleted": 0}
    
    async def write_record(self, record: AuditRecord) -> str:
        """No-op record writing."""
        return record.record_id
    
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
        """No-op record querying - yields nothing."""
        return
        # This is a generator that yields nothing
        yield  # type: ignore[unreachable]
    
    async def get_record(self, record_id: str) -> Optional[AuditRecord]:
        """No-op record retrieval."""
        return None
    
    async def verify_integrity(
        self,
        start_record_id: str,
        end_record_id: str
    ) -> IntegrityResult:
        """No-op integrity verification."""
        return IntegrityResult(
            valid=True,
            records_checked=0,
            chain_breaks=[]
        )
    
    async def close(self) -> None:
        """No-op close."""
        pass
    
    def shutdown(self) -> None:
        """No-op shutdown."""
        pass