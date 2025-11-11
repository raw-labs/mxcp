"""
Audit log query endpoints.

Provides endpoints for querying and analyzing audit logs.
"""

import logging
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query

from ..models import AuditQueryResponse, AuditRecordResponse, AuditStatsResponse
from ..service import AdminService

logger = logging.getLogger(__name__)


def create_audit_router(admin_service: AdminService) -> APIRouter:
    """
    Create audit router with admin service dependency.

    Args:
        admin_service: The admin service wrapping RAWMCP

    Returns:
        Configured APIRouter
    """
    router = APIRouter(prefix="/audit", tags=["audit"])

    @router.get("/query", response_model=AuditQueryResponse, summary="Query audit logs")
    async def query_audit_logs(
        schema_name: str | None = Query(None, description="Filter by schema name"),
        start_time: datetime | None = Query(None, description="Start time (ISO 8601)"),
        end_time: datetime | None = Query(None, description="End time (ISO 8601)"),
        operation_type: str | None = Query(None, description="Filter by operation type"),
        operation_name: str | None = Query(None, description="Filter by operation name"),
        operation_status: str | None = Query(None, description="Filter by status (success, error)"),
        user_id: str | None = Query(None, description="Filter by user ID"),
        trace_id: str | None = Query(None, description="Filter by trace ID"),
        limit: int = Query(100, ge=1, le=1000, description="Maximum number of records to return"),
        offset: int = Query(0, ge=0, description="Number of records to skip"),
    ) -> AuditQueryResponse:
        """
        Query audit logs with filters.

        Returns audit records matching the specified filters. Results are paginated
        and ordered by timestamp (newest first).

        This endpoint is useful for:
        - Investigating specific operations
        - Analyzing user activity
        - Debugging errors
        - Compliance reporting
        """
        if not admin_service.is_audit_enabled():
            return AuditQueryResponse(records=[], count=0)

        try:
            records = []
            
            # Convert single values to lists for the query API
            operation_types = [operation_type] if operation_type else None
            operation_names = [operation_name] if operation_name else None
            operation_statuses = [operation_status] if operation_status else None
            user_ids = [user_id] if user_id else None
            trace_ids = [trace_id] if trace_id else None

            # Query audit records via admin service
            async for record in admin_service.query_audit_records(
                schema_name=schema_name,
                start_time=start_time,
                end_time=end_time,
                operation_types=operation_types,
                operation_names=operation_names,
                operation_status=operation_statuses,
                user_ids=user_ids,
                trace_ids=trace_ids,
                limit=limit,
                offset=offset,
            ):
                # Convert AuditRecord to response model
                records.append(
                    AuditRecordResponse(
                        record_id=record.record_id,
                        timestamp=record.timestamp.isoformat(),
                        schema_name=record.schema_name,
                        schema_version=record.schema_version,
                        operation_type=record.operation_type,
                        operation_name=record.operation_name,
                        operation_status=record.operation_status,
                        duration_ms=record.duration_ms,
                        caller_type=record.caller_type,
                        user_id=record.user_id,
                        session_id=record.session_id,
                        trace_id=record.trace_id,
                        policy_decision=record.policy_decision,
                        error_message=record.error,
                    )
                )

            return AuditQueryResponse(records=records, count=len(records))

        except Exception as e:
            logger.error(f"[admin] Audit query failed: {e}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail=f"Failed to query audit logs: {e}",
            ) from e

    @router.get("/stats", response_model=AuditStatsResponse, summary="Get audit log statistics")
    async def get_audit_stats(
        start_time: datetime | None = Query(None, description="Start time (ISO 8601)"),
        end_time: datetime | None = Query(None, description="End time (ISO 8601)"),
    ) -> AuditStatsResponse:
        """
        Get aggregate statistics for audit logs.

        Returns summary statistics including:
        - Total record count
        - Counts by operation type
        - Counts by status
        - Counts by policy decision
        - Time range of records

        This endpoint is useful for:
        - Dashboard displays
        - Monitoring overall activity
        - Identifying trends
        """
        if not admin_service.is_audit_enabled():
            return AuditStatsResponse(
                total_records=0,
                by_type={},
                by_status={},
                by_policy={},
                earliest_timestamp=None,
                latest_timestamp=None,
            )

        try:
            # Query all records in time range (no limit)
            records = []
            async for record in admin_service.query_audit_records(
                start_time=start_time,
                end_time=end_time,
            ):
                records.append(record)

            # Calculate statistics
            by_type: dict[str, int] = {}
            by_status: dict[str, int] = {}
            by_policy: dict[str, int] = {}
            earliest: datetime | None = None
            latest: datetime | None = None

            for record in records:
                # Count by type
                by_type[record.operation_type] = by_type.get(record.operation_type, 0) + 1

                # Count by status
                by_status[record.operation_status] = by_status.get(record.operation_status, 0) + 1

                # Count by policy decision
                if record.policy_decision:
                    by_policy[record.policy_decision] = by_policy.get(record.policy_decision, 0) + 1

                # Track time range
                if earliest is None or record.timestamp < earliest:
                    earliest = record.timestamp
                if latest is None or record.timestamp > latest:
                    latest = record.timestamp

            return AuditStatsResponse(
                total_records=len(records),
                by_type=by_type,
                by_status=by_status,
                by_policy=by_policy,
                earliest_timestamp=earliest.isoformat() if earliest else None,
                latest_timestamp=latest.isoformat() if latest else None,
            )

        except Exception as e:
            logger.error(f"[admin] Audit stats query failed: {e}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail=f"Failed to get audit statistics: {e}",
            ) from e

    return router

