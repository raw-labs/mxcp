"""Utility functions for audit operations."""

import json
import re
from datetime import datetime, timedelta
from typing import Any

from mxcp.sdk.audit import AuditRecord


def parse_time_since(since_str: str) -> datetime:
    """Parse a time string like '10m', '2h', '1d' into a datetime.

    Args:
        since_str: Time string in format like '10s', '5m', '2h', '1d'

    Returns:
        datetime object representing the calculated past time

    Raises:
        ValueError: If the time format is invalid

    Examples:
        >>> parse_time_since('10m')  # 10 minutes ago
        >>> parse_time_since('2h')   # 2 hours ago
        >>> parse_time_since('1d')   # 1 day ago
    """
    match = re.match(r"^(\d+)([smhd])$", since_str.lower())
    if not match:
        raise ValueError(f"Invalid time format: {since_str}. Use format like '10m', '2h', '1d'")

    amount, unit = match.groups()
    amount = int(amount)

    now = datetime.now()
    if unit == "s":
        return now - timedelta(seconds=amount)
    elif unit == "m":
        return now - timedelta(minutes=amount)
    elif unit == "h":
        return now - timedelta(hours=amount)
    elif unit == "d":
        return now - timedelta(days=amount)
    else:
        raise ValueError(f"Unknown time unit: {unit}")


def format_audit_record(record: AuditRecord, json_format: bool = False) -> str:
    """Format an audit record for display.

    Args:
        record: The audit record to format
        json_format: Whether to output in JSON format

    Returns:
        Formatted string representation of the record
    """
    if json_format:
        # Convert to dict and return JSON

        record_dict = {
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
            "business_context": record.business_context,
            "schema_name": record.schema_name,
            "schema_version": record.schema_version,
        }
        return json.dumps(record_dict, indent=2)
    else:
        # Human-readable format
        status_emoji = "✅" if record.operation_status == "success" else "❌"
        duration = f"{record.duration_ms}ms" if record.duration_ms else "N/A"

        return (
            f"{status_emoji} {record.timestamp.strftime('%Y-%m-%d %H:%M:%S')} "
            f"[{record.operation_type}] {record.operation_name} "
            f"({duration}) - {record.user_id or 'unknown'}"
        )


def map_legacy_query_params(**kwargs: Any) -> dict[str, Any]:
    """Map legacy CLI parameters to new AuditLogger query parameters.

    This function provides backward compatibility for the old CLI interface.

    Args:
        tool: Legacy tool name filter
        resource: Legacy resource filter
        prompt: Legacy prompt filter
        event_type: Legacy event type filter
        policy: Legacy policy filter (now properly supported!)
        status: Legacy status filter
        since: Legacy time filter
        limit: Result limit

    Returns:
        Dict of parameters compatible with AuditLogger.query_records()
    """
    # Extract known parameters
    tool = kwargs.get("tool")
    resource = kwargs.get("resource")
    prompt = kwargs.get("prompt")
    event_type = kwargs.get("event_type")
    policy = kwargs.get("policy")
    status = kwargs.get("status")
    since = kwargs.get("since")
    limit = kwargs.get("limit", 100)

    query_params = {"limit": limit}

    # Map event_type to operation_types
    if event_type:
        query_params["operation_types"] = [event_type]

    # Map tool/resource/prompt to operation_names
    operation_names = []
    if tool:
        operation_names.append(tool)
    if resource:
        operation_names.append(resource)
    if prompt:
        operation_names.append(prompt)
    if operation_names:
        query_params["operation_names"] = operation_names

    # Map since to start_time
    if since:
        query_params["start_time"] = parse_time_since(since).isoformat()

    # Map status - now properly supported in new API!
    if status:
        if status == "success":
            query_params["operation_status"] = ["success"]
        elif status == "error":
            query_params["operation_status"] = ["error"]

    # Map policy - now properly supported in new API!
    if policy and policy != "n/a":
        query_params["policy_decisions"] = [policy]

    return query_params
