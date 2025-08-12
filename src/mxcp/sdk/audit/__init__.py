# -*- coding: utf-8 -*-
"""MXCP SDK Audit - Schema-based audit logging system for enterprise compliance.

This module provides a comprehensive, schema-based audit logging system designed for
enterprise compliance and performance at scale.

## Key Features

1. **Schema-Based Architecture**
   - Policies defined at schema level, not per-record
   - Better performance (no per-write policy lookups)
   - Consistent policy enforcement across all records of a type
   - Easy compliance auditing

2. **Flexible Redaction System**
   - Function-based redaction with built-in strategies
   - Custom redaction function support
   - Field-specific redaction configuration
   - Nested field support

3. **Enhanced Audit Records**
   - Schema-referenced records
   - Evidence levels: BASIC, DETAILED, REGULATORY, FORENSIC
   - Business context extraction
   - Cryptographic integrity support (backend-dependent)

4. **Unified Backend Protocol**
   - Single AuditBackend protocol for all operations
   - Schema management, writing, querying, and retention
   - Extensible design for new backends

5. **Built-in Backends**
   - JSONLAuditWriter: JSONL file storage with DuckDB queries
   - PostgreSQL backend (coming soon)

## Usage Examples

### Define Audit Schemas

```python
from mxcp.sdk.audit import AuditSchema, FieldDefinition, FieldRedaction, EvidenceLevel
from mxcp.sdk.audit import RedactionStrategy

# Define schema for authentication events
auth_schema = AuditSchema(
    schema_name="auth_events",
    version=1,
    description="Authentication and authorization events",
    retention_days=365,  # Keep for 1 year
    evidence_level=EvidenceLevel.REGULATORY,
    fields=[
        FieldDefinition("event_type", "string"),
        FieldDefinition("user_email", "string", sensitive=True),
        FieldDefinition("ip_address", "string", sensitive=True),
        FieldDefinition("success", "boolean")
    ],
    field_redactions=[
        FieldRedaction("user_email", RedactionStrategy.EMAIL),
        FieldRedaction("ip_address", RedactionStrategy.PARTIAL, {"show_last": 3})
    ],
    indexes=["event_type", "timestamp", "user_email"]
)

# Define schema for API calls
api_schema = AuditSchema(
    schema_name="api_calls",
    version=1,
    description="API request/response audit",
    retention_days=90,
    evidence_level=EvidenceLevel.DETAILED,
    fields=[
        FieldDefinition("method", "string"),
        FieldDefinition("path", "string"),
        FieldDefinition("status_code", "number"),
        FieldDefinition("api_key", "string", sensitive=True)
    ],
    field_redactions=[
        FieldRedaction("api_key", RedactionStrategy.PARTIAL, {"show_first": 8, "show_last": 0})
    ],
    extract_fields=["method", "path", "status_code"]  # For business context
)
```

### Using AuditLogger

```python
from pathlib import Path
from mxcp.sdk.audit import AuditLogger

# Create logger with JSONL backend
logger = AuditLogger.jsonl(Path("audit.jsonl"))

# Or create a disabled logger (no-op backend)
# disabled_logger = AuditLogger.disabled()

# Register schemas
logger.create_schema(auth_schema)
logger.create_schema(api_schema)

# Log authentication event
await logger.log_event(
    caller_type="http",
    event_type="auth",
    name="user_login",
    input_params={
        "event_type": "login",
        "user_email": "alice@example.com",
        "ip_address": "192.168.1.100",
        "success": True
    },
    duration_ms=50,
    schema_name="auth_events",
    user_id="alice",
    status="success"
)

# Log API call
await logger.log_event(
    caller_type="http",
    event_type="api",
    name="api_request",
    input_params={
        "method": "POST",
        "path": "/api/v1/users",
        "api_key": "sk_live_abcdef123456",
        "body": {"name": "Bob"}
    },
    duration_ms=150,
    schema_name="api_calls",
    status="success",
    output_data={"status_code": 201, "user_id": "user_456"}
)
```

### Querying Audit Records

```python
# Query by schema
auth_events = await logger.query_records(
    schema_name="auth_events",
    start_time=yesterday,
    limit=100
)

# Query across schemas with filters
all_failures = await logger.query_records(
    operation_status="error",
    start_time=last_week,
    limit=50
)

# Get specific record
record = await logger.get_record("abc123-def456")

# Verify integrity
result = await logger.verify_integrity("record1", "record2")
```

### Apply Retention Policies

```python
# Apply retention policies (removes expired records)
deleted_counts = await logger.apply_retention_policies()
print(f"Deleted: {deleted_counts}")
# Output: {"auth_events:v1": 150, "api_calls:v1": 2000}
```

## Architecture Overview

The audit system follows a clean, layered architecture:

1. **AuditLogger**: High-level interface that applications use
   - Manages schema registration
   - Provides consistent API
   - Handles async/sync bridging

2. **AuditBackend Protocol**: Unified interface for backends
   - Schema management methods
   - Write and query operations
   - Retention management

3. **Backend Implementations**: Storage-specific logic
   - JSONLAuditWriter: JSONL files with DuckDB queries
   - PostgreSQL (coming soon): With hash chains and signatures

## Schema Design Rationale

Schemas provide several advantages over per-request policies:

- **Performance**: No policy lookups on every write
- **Consistency**: All records of a type follow same rules
- **Compliance**: Easy to prove policy enforcement
- **Operations**: Bulk retention and querying by schema
"""

from ._types import (  # Core types; Protocols
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
from .backends.noop import NoOpAuditBackend
from .logger import AuditLogger
from .redaction import apply_redaction
from .writer import AuditRedactor, BaseAuditWriter

__all__ = [
    # Core types
    "CallerType",
    "EventType",
    "PolicyDecision",
    "Status",
    "AuditRecord",
    "AuditSchema",
    "FieldDefinition",
    "EvidenceLevel",
    "FieldRedaction",
    "RedactionStrategy",
    "IntegrityResult",
    # Core classes
    "AuditLogger",
    "BaseAuditWriter",
    "AuditRedactor",
    # Backends
    "NoOpAuditBackend",
    # Protocols
    "AuditBackend",
    # Redaction function
    "apply_redaction",
]
