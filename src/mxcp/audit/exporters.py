# -*- coding: utf-8 -*-
"""Backend-agnostic export utilities for audit data.

This module provides export functionality that works through the
AuditLogger API, making it independent of the underlying storage backend.
"""

import csv
import json
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, AsyncIterator, Dict, List, Optional

import duckdb

from mxcp.sdk.audit import AuditLogger, AuditRecord


class ExportFormat(Enum):
    """Supported export formats."""

    CSV = "csv"
    DUCKDB = "duckdb"
    JSON = "json"
    JSONL = "jsonl"


async def export_to_duckdb(
    audit_logger: AuditLogger, export_path: Path, filters: Optional[Dict[str, Any]] = None
) -> int:
    """Export audit logs to a DuckDB database using the AuditLogger API.

    Args:
        audit_logger: The AuditLogger instance to query records from
        export_path: Path where to create the DuckDB database
        filters: Optional query filters (same as query_records parameters)

    Returns:
        Number of records exported
    """
    conn = duckdb.connect(str(export_path))
    total_exported = 0

    try:
        # Create table on first batch
        table_created = False

        # Query parameters from filters
        query_params = _build_query_params(filters)

        async for record in audit_logger.query_records(**query_params):
            # Convert to dictionary
            record_dict = _record_to_dict(record)

            if not table_created:
                # Create table with schema from first record
                _create_duckdb_table(conn, record_dict)
                table_created = True

            # Insert record
            conn.execute(
                "INSERT INTO audit_logs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                tuple(record_dict.values()),
            )

            total_exported += 1

    finally:
        conn.close()

    return total_exported


async def export_to_csv(
    audit_logger: AuditLogger, export_path: Path, filters: Optional[Dict[str, Any]] = None
) -> int:
    """Export audit logs to CSV using the AuditLogger API.

    Args:
        audit_logger: The AuditLogger instance to query records from
        export_path: Path where to create the CSV file
        filters: Optional query filters

    Returns:
        Number of records exported
    """
    total_exported = 0

    with open(export_path, "w", newline="", encoding="utf-8") as csvfile:
        writer = None

        # Query parameters from filters
        query_params = _build_query_params(filters)

        async for record in audit_logger.query_records(**query_params):
            record_dict = _record_to_dict(record)

            # Initialize CSV writer with headers from first record
            if writer is None:
                writer = csv.DictWriter(csvfile, fieldnames=record_dict.keys())
                writer.writeheader()

            # Write record
            writer.writerow(record_dict)
            total_exported += 1

    return total_exported


async def export_to_jsonl(
    audit_logger: AuditLogger, export_path: Path, filters: Optional[Dict[str, Any]] = None
) -> int:
    """Export audit logs to JSONL format using the AuditLogger API.

    Args:
        audit_logger: The AuditLogger instance to query records from
        export_path: Path where to create the JSONL file
        filters: Optional query filters

    Returns:
        Number of records exported
    """
    total_exported = 0

    with open(export_path, "w", encoding="utf-8") as f:
        # Query parameters from filters
        query_params = _build_query_params(filters)

        async for record in audit_logger.query_records(**query_params):
            json.dump(_record_to_dict(record), f, ensure_ascii=False)
            f.write("\n")
            total_exported += 1

    return total_exported


async def export_to_json(
    audit_logger: AuditLogger, export_path: Path, filters: Optional[Dict[str, Any]] = None
) -> int:
    """Export audit logs to JSON format using the AuditLogger API.

    Args:
        audit_logger: The AuditLogger instance to query records from
        export_path: Path where to create the JSON file
        filters: Optional query filters

    Returns:
        Number of records exported
    """
    records_data = []

    # Query parameters from filters
    query_params = _build_query_params(filters)

    async for record in audit_logger.query_records(**query_params):
        records_data.append(_record_to_dict(record))

    # Write to file
    with open(export_path, "w", encoding="utf-8") as f:
        json.dump(records_data, f, indent=2, ensure_ascii=False)

    return len(records_data)


def _build_query_params(filters: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Build query parameters from filter dict.

    Maps legacy filter names to new API parameters.
    """
    if filters is None:
        filters = {}

    params: Dict[str, Any] = {}

    # Map filters to query_records parameters
    if "tool" in filters:
        params["operation_names"] = [filters["tool"]]
    if "resource" in filters:
        params["operation_names"] = params.get("operation_names", []) + [filters["resource"]]
    if "prompt" in filters:
        params["operation_names"] = params.get("operation_names", []) + [filters["prompt"]]
    if "event_type" in filters:
        params["operation_types"] = [filters["event_type"]]
    if "status" in filters:
        params["operation_status"] = [filters["status"]]
    if "policy" in filters:
        params["policy_decisions"] = [filters["policy"]]
    if "user_id" in filters:
        params["user_ids"] = [filters["user_id"]]
    if "since" in filters:
        # Assume since is already a datetime or ISO string
        if isinstance(filters["since"], str):
            params["start_time"] = datetime.fromisoformat(filters["since"])
        else:
            params["start_time"] = filters["since"]
    if "limit" in filters:
        params["limit"] = filters["limit"]

    return params


def _record_to_dict(record: AuditRecord) -> Dict[str, Any]:
    """Convert an AuditRecord to a dictionary for export."""
    return {
        "record_id": record.record_id,
        "timestamp": record.timestamp.isoformat(),
        "caller_type": record.caller_type,
        "operation_type": record.operation_type,
        "operation_name": record.operation_name,
        "duration_ms": record.duration_ms,
        "user_id": record.user_id,
        "session_id": record.session_id,
        "trace_id": record.trace_id,
        "operation_status": record.operation_status,
        "error": record.error,
        "policy_decision": record.policy_decision,
        "policy_reason": record.policy_reason,
        "business_context": record.business_context,
        "schema_name": record.schema_name,
        "schema_version": record.schema_version,
        "input_data": record.input_data,
        "output_data": record.output_data,
        "policies_evaluated": record.policies_evaluated,
        "prev_hash": record.prev_hash,
        "record_hash": record.record_hash,
        "signature": record.signature,
    }


def _create_duckdb_table(conn: duckdb.DuckDBPyConnection, sample_record: Dict[str, Any]) -> None:
    """Create DuckDB table based on a sample record."""
    # Infer column types from sample data
    columns = []
    for key, value in sample_record.items():
        if isinstance(value, str):
            col_type = "VARCHAR"
        elif isinstance(value, int):
            col_type = "INTEGER"
        elif isinstance(value, float):
            col_type = "DOUBLE"
        elif isinstance(value, bool):
            col_type = "BOOLEAN"
        elif isinstance(value, dict) or isinstance(value, list):
            col_type = "JSON"
        else:
            col_type = "VARCHAR"  # Default fallback

        columns.append(f"{key} {col_type}")

    create_stmt = f"CREATE TABLE IF NOT EXISTS audit_logs ({', '.join(columns)})"
    conn.execute(create_stmt)
