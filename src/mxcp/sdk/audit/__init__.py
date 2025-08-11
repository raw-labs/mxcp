# -*- coding: utf-8 -*-
"""MXCP SDK Audit - Enterprise-grade audit logging and querying.

This module provides comprehensive audit logging functionality including:
- Structured audit events for all operations
- Query interface for audit trail analysis  
- Policy decision tracking and compliance reporting
- Sensitive data redaction and security controls

## Key Components

### Core Classes
- `AuditLogger`: Main logging interface for audit events
- `AuditQuery`: Query builder for searching audit logs
- `LogEvent`: Structured audit event data

### Event Types
- `EventType`: Tool execution, resource access, prompt generation, etc.
- `Status`: Success, failure, policy_denied, etc.
- `CallerType`: User, system, api, etc.

## Quick Examples

### Basic Audit Logging
```python
from mxcp.sdk.audit import AuditLogger, EventType, Status, CallerType

# Create audit logger
logger = AuditLogger(database_path="audit.db")

# Log tool execution
await logger.log_event(
    event_type=EventType.TOOL_EXECUTION,
    caller_type=CallerType.USER,
    username="alice",
    tool_name="query_database", 
    parameters={"query": "SELECT * FROM users"},
    result={"count": 150},
    status=Status.SUCCESS,
    execution_time_ms=250
)

# Log policy decisions
await logger.log_event(
    event_type=EventType.POLICY_DECISION,
    caller_type=CallerType.SYSTEM,
    tool_name="sensitive_query",
    policy_decision="DENY",
    reason="User lacks required permissions",
    status=Status.POLICY_DENIED
)
```

### Audit Querying
```python
from mxcp.sdk.audit import AuditQuery

# Query audit logs
query = AuditQuery(database_path="audit.db")

# Find all failed operations in last 24 hours
recent_failures = await query.get_events(
    status=Status.FAILURE,
    start_time="2024-01-01T00:00:00Z",
    limit=100
)

# Security audit: policy denials by user
policy_denials = await query.get_events(
    event_type=EventType.POLICY_DECISION,
    status=Status.POLICY_DENIED,
    username="bob"
)
```
"""

from .types import (
    CallerType,
    EventType, 
    PolicyDecision,
    Status,
    LogEvent,
)
from .logger import AuditLogger
from .query import AuditQuery

__all__ = [
    # Types
    "CallerType",
    "EventType",
    "PolicyDecision", 
    "Status",
    "LogEvent",
    # Core classes
    "AuditLogger",
    "AuditQuery",
] 