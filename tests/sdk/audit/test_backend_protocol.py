"""Test AuditBackend protocol compliance.

These tests should pass for any backend implementation and can be used
to verify new backends like PostgreSQL when implemented.
"""

import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from mxcp.sdk.audit import (
    AuditRecordModel,
    AuditSchemaModel,
    EvidenceLevel,
)
from mxcp.sdk.audit.backends import JSONLAuditWriter


# This fixture can be parameterized to test multiple backends
@pytest.fixture
async def backend():
    """Create a backend instance for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        log_path = Path(tmpdir) / "audit.jsonl"
        backend = JSONLAuditWriter(log_path)
        yield backend
        await backend.close()


@pytest.mark.asyncio
async def test_backend_schema_management(backend):
    """Test that backend properly implements schema management."""

    # Initially no schemas
    schemas = await backend.list_schemas()
    assert len(schemas) == 0

    # Create a schema
    schema = AuditSchemaModel(
        schema_name="protocol_test",
        version=1,
        description="Test protocol compliance",
        retention_days=90,
        evidence_level=EvidenceLevel.DETAILED,
    )

    await backend.create_schema(schema)

    # Should now have one schema
    schemas = await backend.list_schemas()
    assert len(schemas) == 1
    assert schemas[0].schema_name == "protocol_test"

    # Should be able to retrieve the schema
    retrieved = await backend.get_schema("protocol_test", 1)
    assert retrieved is not None
    assert retrieved.schema_name == "protocol_test"
    assert retrieved.version == 1
    assert retrieved.description == "Test protocol compliance"
    assert retrieved.retention_days == 90
    assert retrieved.evidence_level == EvidenceLevel.DETAILED

    # Should be able to get latest version without specifying version
    latest = await backend.get_schema("protocol_test")
    assert latest is not None
    assert latest.version == 1


@pytest.mark.asyncio
async def test_backend_record_writing(backend):
    """Test that backend properly writes audit records."""

    # Create schema first
    schema = AuditSchemaModel(schema_name="write_test", version=1, description="Test record writing")
    await backend.create_schema(schema)

    # Write a record
    record = AuditRecordModel(
        schema_name="write_test",
        operation_type="tool",
        operation_name="test_tool",
        caller_type="cli",
        input_data={"param": "value"},
        output_data={"result": "success"},
        duration_ms=150,
        user_id="user123",
        session_id="session456",
        operation_status="success",
    )

    record_id = await backend.write_record(record)

    # Should return a valid record ID
    assert record_id is not None
    assert isinstance(record_id, str)
    assert len(record_id) > 0


@pytest.mark.asyncio
async def test_backend_record_querying(backend):
    """Test that backend properly implements record querying."""

    # Create schema
    schema = AuditSchemaModel(schema_name="query_test", version=1, description="Test record querying")
    await backend.create_schema(schema)

    # Write multiple records
    records_data = [
        {"name": "tool_a", "type": "tool", "user": "alice", "status": "success"},
        {"name": "tool_b", "type": "tool", "user": "bob", "status": "success"},
        {"name": "resource_a", "type": "resource", "user": "alice", "status": "success"},
        {"name": "tool_c", "type": "tool", "user": "alice", "status": "error"},
    ]

    record_ids = []
    for data in records_data:
        record = AuditRecordModel(
            schema_name="query_test",
            operation_type=data["type"],
            operation_name=data["name"],
            caller_type="cli",
            input_data={"user": data["user"]},
            duration_ms=100,
            user_id=data["user"],
            operation_status=data["status"],
        )
        record_id = await backend.write_record(record)
        record_ids.append(record_id)

    # Ensure writes are committed
    await backend.close()

    # Query all records
    all_records = [r async for r in backend.query_records()]
    assert len(all_records) == 4

    # Query by operation type
    tool_records = [r async for r in backend.query_records(operation_types=["tool"])]
    assert len(tool_records) == 3

    # Query by operation names
    specific_records = [
        r async for r in backend.query_records(operation_names=["tool_a", "tool_b"])
    ]
    assert len(specific_records) == 2

    # Query by user
    alice_records = [r async for r in backend.query_records(user_ids=["alice"])]
    assert len(alice_records) == 3

    # Query with limit
    limited_records = [r async for r in backend.query_records(limit=2)]
    assert len(limited_records) == 2

    # Query with offset
    offset_records = [r async for r in backend.query_records(limit=2, offset=2)]
    assert len(offset_records) == 2

    # Combined filters
    alice_tools = [
        r async for r in backend.query_records(operation_types=["tool"], user_ids=["alice"])
    ]
    assert len(alice_tools) == 2


@pytest.mark.asyncio
async def test_backend_record_retrieval(backend):
    """Test that backend can retrieve individual records."""

    # Create schema
    schema = AuditSchemaModel(
        schema_name="retrieval_test", version=1, description="Test record retrieval"
    )
    await backend.create_schema(schema)

    # Write a record
    original_record = AuditRecordModel(
        schema_name="retrieval_test",
        operation_type="tool",
        operation_name="test_tool",
        caller_type="cli",
        input_data={"key": "value"},
        output_data={"result": "success"},
        duration_ms=200,
        user_id="user123",
        operation_status="success",
    )

    record_id = await backend.write_record(original_record)

    # Ensure write is committed
    await backend.close()

    # Retrieve the record
    retrieved_record = await backend.get_record(record_id)

    assert retrieved_record is not None
    assert retrieved_record.record_id == record_id
    assert retrieved_record.schema_name == "retrieval_test"
    assert retrieved_record.operation_type == "tool"
    assert retrieved_record.operation_name == "test_tool"
    assert retrieved_record.caller_type == "cli"
    assert retrieved_record.input_data == {"key": "value"}
    assert retrieved_record.output_data == {"result": "success"}
    assert retrieved_record.duration_ms == 200
    assert retrieved_record.user_id == "user123"
    assert retrieved_record.operation_status == "success"

    # Non-existent record should return None
    non_existent = await backend.get_record("non-existent-id")
    assert non_existent is None


@pytest.mark.asyncio
async def test_backend_schema_deactivation(backend):
    """Test that backend properly handles schema deactivation."""

    # Create schema
    schema = AuditSchemaModel(
        schema_name="deactivation_test", version=1, description="Test schema deactivation"
    )
    await backend.create_schema(schema)

    # Should appear in active schemas
    active_schemas = await backend.list_schemas(active_only=True)
    assert len(active_schemas) == 1
    assert active_schemas[0].schema_name == "deactivation_test"
    assert active_schemas[0].active is True

    # Deactivate the schema
    await backend.deactivate_schema("deactivation_test", 1)

    # Should not appear in active schemas
    active_schemas = await backend.list_schemas(active_only=True)
    assert len(active_schemas) == 0

    # But should appear in all schemas
    all_schemas = await backend.list_schemas(active_only=False)
    assert len(all_schemas) == 1
    assert all_schemas[0].schema_name == "deactivation_test"
    assert all_schemas[0].active is False


@pytest.mark.asyncio
async def test_backend_time_filtering(backend):
    """Test that backend supports time-based filtering."""

    # Create schema
    schema = AuditSchemaModel(schema_name="time_test", version=1, description="Test time filtering")
    await backend.create_schema(schema)

    # Create records with different timestamps
    base_time = datetime.now(timezone.utc)
    times = [
        base_time - timedelta(hours=2),
        base_time - timedelta(hours=1),
        base_time,
        base_time + timedelta(hours=1),
    ]

    record_ids = []
    for i, timestamp in enumerate(times):
        record = AuditRecordModel(
            schema_name="time_test",
            operation_type="tool",
            operation_name=f"tool_{i}",
            caller_type="cli",
            input_data={"index": i},
            duration_ms=100,
            operation_status="success",
        )
        # Manually set timestamp
        record.timestamp = timestamp
        record_id = await backend.write_record(record)
        record_ids.append(record_id)

    # Ensure writes are committed
    await backend.close()

    # Query with time filters
    start_time = base_time - timedelta(minutes=30)
    end_time = base_time + timedelta(minutes=30)

    filtered_records = [
        r async for r in backend.query_records(start_time=start_time, end_time=end_time)
    ]

    # Should only get the record at base_time (within 30 min window)
    assert len(filtered_records) == 1

    # Query with only start time (should get records at base_time and base_time + 1 hour)
    recent_records = [r async for r in backend.query_records(start_time=start_time)]
    assert len(recent_records) == 2


@pytest.mark.asyncio
async def test_backend_integrity_verification(backend):
    """Test that backend implements integrity verification."""

    # Create schema
    schema = AuditSchemaModel(
        schema_name="integrity_test", version=1, description="Test integrity verification"
    )
    await backend.create_schema(schema)

    # Write some records
    record_ids = []
    for i in range(3):
        record = AuditRecordModel(
            schema_name="integrity_test",
            operation_type="tool",
            operation_name=f"tool_{i}",
            caller_type="cli",
            input_data={"index": i},
            duration_ms=100,
            operation_status="success",
        )
        record_id = await backend.write_record(record)
        record_ids.append(record_id)

    # Ensure writes are committed
    await backend.close()

    # Verify integrity between records
    integrity_result = await backend.verify_integrity(record_ids[0], record_ids[2])

    # Should return an IntegrityResult
    assert integrity_result is not None
    assert hasattr(integrity_result, "valid")
    assert hasattr(integrity_result, "records_checked")
    assert hasattr(integrity_result, "chain_breaks")

    # For a simple backend like JSONL, integrity should be valid
    # Only start and end records are checked (2 records)
    assert integrity_result.valid is True
    assert integrity_result.records_checked == 2
    assert len(integrity_result.chain_breaks) == 0


@pytest.mark.asyncio
async def test_backend_retention_policies(backend):
    """Test that backend implements retention policy application."""

    # Create schema with short retention
    schema = AuditSchemaModel(
        schema_name="retention_test",
        version=1,
        description="Test retention policies",
        retention_days=1,
    )
    await backend.create_schema(schema)

    # Write records with different ages
    old_record = AuditRecordModel(
        schema_name="retention_test",
        operation_type="tool",
        operation_name="old_tool",
        caller_type="cli",
        input_data={"age": "old"},
        duration_ms=100,
        operation_status="success",
    )
    # Make it older than retention period
    old_record.timestamp = datetime.now(timezone.utc) - timedelta(days=2)

    new_record = AuditRecordModel(
        schema_name="retention_test",
        operation_type="tool",
        operation_name="new_tool",
        caller_type="cli",
        input_data={"age": "new"},
        duration_ms=100,
        operation_status="success",
    )

    await backend.write_record(old_record)
    await backend.write_record(new_record)

    # Ensure writes are committed
    await backend.close()

    # Apply retention policies
    deleted_counts = await backend.apply_retention_policies()

    # Should return a dictionary with counts
    assert isinstance(deleted_counts, dict)
    assert "retention_test:v1" in deleted_counts
    assert deleted_counts["retention_test:v1"] >= 1  # Should have deleted the old record

    # Verify old record is gone but new record remains
    remaining_records = [r async for r in backend.query_records()]
    assert len(remaining_records) == 1
    assert remaining_records[0].operation_name == "new_tool"


@pytest.mark.asyncio
async def test_backend_schema_versioning(backend):
    """Test that backend handles schema versioning correctly."""

    # Create version 1
    schema_v1 = AuditSchemaModel(
        schema_name="versioned_schema", version=1, description="Version 1 of schema"
    )
    await backend.create_schema(schema_v1)

    # Create version 2
    schema_v2 = AuditSchemaModel(
        schema_name="versioned_schema",
        version=2,
        description="Version 2 of schema",
        retention_days=180,  # Different from v1
    )
    await backend.create_schema(schema_v2)

    # Should have both versions
    all_schemas = await backend.list_schemas()
    versioned_schemas = [s for s in all_schemas if s.schema_name == "versioned_schema"]
    assert len(versioned_schemas) == 2

    # Should be able to retrieve specific versions
    v1 = await backend.get_schema("versioned_schema", 1)
    v2 = await backend.get_schema("versioned_schema", 2)

    assert v1.version == 1
    assert v1.description == "Version 1 of schema"
    assert v1.retention_days is None  # Default

    assert v2.version == 2
    assert v2.description == "Version 2 of schema"
    assert v2.retention_days == 180

    # Getting without version should return latest
    latest = await backend.get_schema("versioned_schema")
    assert latest.version == 2
