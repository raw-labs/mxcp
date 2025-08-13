"""No-operation audit backend for disabled audit logging."""

from collections.abc import AsyncIterator
from datetime import datetime
from typing import Any

from .._types import AuditRecord, AuditSchema, IntegrityResult, PolicyDecision, Status


class NoOpAuditBackend:
    """No-operation audit backend that discards all audit records.

    Used when audit logging is disabled. All operations are no-ops
    that return appropriate empty/default values.
    """

    def __init__(self) -> None:
        """Initialize the no-op backend."""
        pass

    async def create_schema(self, schema: AuditSchema) -> None:
        """No-op schema creation."""
        pass

    async def get_schema(self, schema_name: str, version: int | None = None) -> AuditSchema | None:
        """No-op schema retrieval."""
        return None

    async def list_schemas(self, active_only: bool = True) -> list[AuditSchema]:
        """No-op schema listing."""
        return []

    async def deactivate_schema(self, schema_name: str, version: int | None = None) -> None:
        """No-op schema deactivation."""
        pass

    async def apply_retention_policies(self) -> dict[str, Any]:
        """No-op retention policy application."""
        return {"processed": 0, "deleted": 0}

    async def write_record(self, record: AuditRecord) -> str:
        """No-op record writing."""
        return record.record_id

    async def query_records(
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
        """No-op record querying - yields nothing."""
        return
        # This is a generator that yields nothing
        yield

    async def get_record(self, record_id: str) -> AuditRecord | None:
        """No-op record retrieval."""
        return None

    async def verify_integrity(self, start_record_id: str, end_record_id: str) -> IntegrityResult:
        """No-op integrity verification."""
        return IntegrityResult(valid=True, records_checked=0, chain_breaks=[])

    async def close(self) -> None:
        """No-op close."""
        pass

    def shutdown(self) -> None:
        """No-op shutdown."""
        pass
