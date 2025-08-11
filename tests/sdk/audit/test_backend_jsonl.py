"""Test JSONL backend implementation specifics."""
import json
import pytest
import tempfile
from pathlib import Path
from datetime import datetime, timezone

from mxcp.sdk.audit import (
    AuditRecord,
    AuditSchema,
    FieldDefinition,
    FieldRedaction,
    EvidenceLevel,
    RedactionStrategy,
)
from mxcp.sdk.audit.backends import JSONLAuditWriter


@pytest.mark.asyncio
async def test_jsonl_file_creation():
    """Test that JSONL backend creates files correctly."""
    with tempfile.TemporaryDirectory() as tmpdir:
        log_path = Path(tmpdir) / "audit.jsonl"
        schema_path = Path(tmpdir) / "audit_schemas.jsonl"
        
        backend = JSONLAuditWriter(log_path)
        
        # Log file is created on init, schema file should not exist yet
        assert log_path.exists()
        assert not schema_path.exists()
        
        # Create a schema - this should create the schema file
        schema = AuditSchema(
            schema_name="test_schema",
            version=1,
            description="Test schema"
        )
        await backend.create_schema(schema)
        
        # Schema file should now exist
        assert schema_path.exists()
        
        # Write a record - this should create the log file
        record = AuditRecord(
            schema_name="test_schema",
            operation_type="tool",
            operation_name="test_tool",
            caller_type="cli",
            input_data={"test": "data"},
            duration_ms=100,
            operation_status="success"
        )
        
        await backend.write_record(record)
        backend.shutdown()  # Force flush
        
        # Log file should now exist
        assert log_path.exists()


@pytest.mark.asyncio
async def test_jsonl_schema_persistence():
    """Test that schemas are properly persisted to JSONL."""
    with tempfile.TemporaryDirectory() as tmpdir:
        log_path = Path(tmpdir) / "audit.jsonl"
        schema_path = Path(tmpdir) / "audit_schemas.jsonl"
        
        # Create backend and schema
        backend = JSONLAuditWriter(log_path)
        
        schema = AuditSchema(
            schema_name="persist_test",
            version=1,
            description="Persistence test schema",
            retention_days=180,
            evidence_level=EvidenceLevel.DETAILED,
            fields=[
                FieldDefinition("field1", "string", sensitive=True),
                FieldDefinition("field2", "number")
            ],
            field_redactions=[
                FieldRedaction("field1", RedactionStrategy.PARTIAL)
            ],
            extract_fields=["field2"],
            indexes=["field1", "field2"]
        )
        
        await backend.create_schema(schema)
        await backend.close()
        
        # Create new backend instance - should load existing schemas
        backend2 = JSONLAuditWriter(log_path)
        retrieved_schema = await backend2.get_schema("persist_test", 1)
        
        assert retrieved_schema is not None
        assert retrieved_schema.schema_name == "persist_test"
        assert retrieved_schema.version == 1
        assert retrieved_schema.description == "Persistence test schema"
        assert retrieved_schema.retention_days == 180
        assert retrieved_schema.evidence_level == EvidenceLevel.DETAILED
        assert len(retrieved_schema.fields) == 2
        assert len(retrieved_schema.field_redactions) == 1
        assert retrieved_schema.extract_fields == ["field2"]
        assert retrieved_schema.indexes == ["field1", "field2"]


@pytest.mark.asyncio
async def test_jsonl_record_format():
    """Test that records are written in correct JSONL format."""
    with tempfile.TemporaryDirectory() as tmpdir:
        log_path = Path(tmpdir) / "audit.jsonl"
        
        backend = JSONLAuditWriter(log_path)
        
        # Create schema and record
        schema = AuditSchema(
            schema_name="format_test",
            version=1,
            description="Format test"
        )
        await backend.create_schema(schema)
        
        record = AuditRecord(
            schema_name="format_test",
            operation_type="tool",
            operation_name="format_tool",
            caller_type="cli",
            input_data={"key": "value", "number": 42},
            output_data={"result": "success"},
            duration_ms=150,
            user_id="user123",
            session_id="session456",
            operation_status="success"
        )
        
        record_id = await backend.write_record(record)
        backend.shutdown()
        
        # Read the JSONL file and verify format
        with open(log_path, 'r') as f:
            line = f.readline().strip()
            data = json.loads(line)
        
        assert data["record_id"] == record_id
        assert data["schema_name"] == "format_test"
        assert data["schema_version"] == 1
        assert data["operation_type"] == "tool"
        assert data["operation_name"] == "format_tool"
        assert data["caller_type"] == "cli"
        assert data["input_data"] == {"key": "value", "number": 42}
        assert data["output_data"] == {"result": "success"}
        assert data["duration_ms"] == 150
        assert data["user_id"] == "user123"
        assert data["session_id"] == "session456"
        assert data["operation_status"] == "success"
        assert "timestamp" in data
        assert "input_data" in data
        assert "output_data" in data


@pytest.mark.asyncio
async def test_jsonl_schema_redaction_serialization():
    """Test that redaction strategies are properly serialized/deserialized."""
    with tempfile.TemporaryDirectory() as tmpdir:
        log_path = Path(tmpdir) / "audit.jsonl"
        
        backend = JSONLAuditWriter(log_path)
        
        # Create schema with various redaction strategies
        schema = AuditSchema(
            schema_name="redaction_test",
            version=1,
            description="Test redaction serialization",
            field_redactions=[
                FieldRedaction("email", RedactionStrategy.EMAIL),
                FieldRedaction("ssn", RedactionStrategy.PARTIAL, {"show_last": 4}),
                FieldRedaction("secret", RedactionStrategy.HASH),
                FieldRedaction("description", RedactionStrategy.TRUNCATE, {"length": 20}),
                FieldRedaction("sensitive", RedactionStrategy.FULL),
            ]
        )
        
        await backend.create_schema(schema)
        await backend.close()
        
        # Create new backend and retrieve schema
        backend2 = JSONLAuditWriter(log_path)
        retrieved = await backend2.get_schema("redaction_test", 1)
        
        assert len(retrieved.field_redactions) == 5
        
        # Check each redaction strategy was preserved
        redactions_by_field = {r.field_path: r for r in retrieved.field_redactions}
        
        assert redactions_by_field["email"].strategy == RedactionStrategy.EMAIL
        assert redactions_by_field["ssn"].strategy == RedactionStrategy.PARTIAL
        assert redactions_by_field["ssn"].options == {"show_last": 4}
        assert redactions_by_field["secret"].strategy == RedactionStrategy.HASH
        assert redactions_by_field["description"].strategy == RedactionStrategy.TRUNCATE
        assert redactions_by_field["description"].options == {"length": 20}
        assert redactions_by_field["sensitive"].strategy == RedactionStrategy.FULL


@pytest.mark.asyncio
async def test_jsonl_concurrent_writes():
    """Test JSONL backend handles concurrent writes safely."""
    with tempfile.TemporaryDirectory() as tmpdir:
        log_path = Path(tmpdir) / "audit.jsonl"
        
        backend = JSONLAuditWriter(log_path)
        
        # Create schema
        schema = AuditSchema(
            schema_name="concurrent_test",
            version=1,
            description="Test concurrent writes"
        )
        await backend.create_schema(schema)
        
        # Write multiple records concurrently
        import asyncio
        
        async def write_record(i):
            record = AuditRecord(
                schema_name="concurrent_test",
                operation_type="tool",
                operation_name=f"tool_{i}",
                caller_type="cli",
                input_data={"index": i},
                duration_ms=i * 10,
                operation_status="success"
            )
            return await backend.write_record(record)
        
        # Write 10 records concurrently
        tasks = [write_record(i) for i in range(10)]
        record_ids = await asyncio.gather(*tasks)
        
        backend.shutdown()
        
        # Verify all records were written
        assert len(record_ids) == 10
        assert len(set(record_ids)) == 10  # All IDs should be unique
        
        # Verify file contains all records
        with open(log_path, 'r') as f:
            lines = f.readlines()
        
        assert len(lines) == 10
        
        # Verify each line is valid JSON
        for line in lines:
            data = json.loads(line.strip())
            assert "operation_name" in data
            assert data["operation_name"].startswith("tool_")


@pytest.mark.asyncio
async def test_jsonl_query_filtering():
    """Test JSONL backend query filtering capabilities."""
    with tempfile.TemporaryDirectory() as tmpdir:
        log_path = Path(tmpdir) / "audit.jsonl"
        
        backend = JSONLAuditWriter(log_path)
        
        # Create schema
        schema = AuditSchema(
            schema_name="query_test",
            version=1,
            description="Test query filtering"
        )
        await backend.create_schema(schema)
        
        # Write records with different characteristics
        records_data = [
            {"name": "tool_a", "type": "tool", "user": "alice"},
            {"name": "tool_b", "type": "tool", "user": "bob"},
            {"name": "resource_a", "type": "resource", "user": "alice"},
            {"name": "tool_c", "type": "tool", "user": "charlie"},
        ]
        
        for data in records_data:
            record = AuditRecord(
                schema_name="query_test",
                operation_type=data["type"],
                operation_name=data["name"],
                caller_type="cli",
                input_data={"user": data["user"]},
                duration_ms=100,
                operation_status="success",
                user_id=data["user"]
            )
            await backend.write_record(record)
        
        backend.shutdown()
        
        # Test various query filters
        
        # Filter by operation type
        tool_records = await backend.query_records(operation_types=["tool"])
        assert len(tool_records) == 3
        
        # Filter by operation names
        specific_tools = await backend.query_records(operation_names=["tool_a", "tool_b"])
        assert len(specific_tools) == 2
        
        # Filter by user
        alice_records = await backend.query_records(user_ids=["alice"])
        assert len(alice_records) == 2
        
        # Combine filters
        alice_tools = await backend.query_records(
            operation_types=["tool"], 
            user_ids=["alice"]
        )
        assert len(alice_tools) == 1
        assert alice_tools[0].operation_name == "tool_a"


@pytest.mark.asyncio
async def test_jsonl_schema_deactivation():
    """Test schema deactivation in JSONL backend."""
    with tempfile.TemporaryDirectory() as tmpdir:
        log_path = Path(tmpdir) / "audit.jsonl"
        
        backend = JSONLAuditWriter(log_path)
        
        # Create active schema
        schema = AuditSchema(
            schema_name="deactivate_test",
            version=1,
            description="Test deactivation"
        )
        await backend.create_schema(schema)
        
        # Verify it's active
        active_schemas = await backend.list_schemas(active_only=True)
        assert len(active_schemas) == 1
        assert active_schemas[0].schema_name == "deactivate_test"
        
        # Deactivate the schema
        await backend.deactivate_schema("deactivate_test", 1)
        
        # Should not appear in active list
        active_schemas = await backend.list_schemas(active_only=True)
        assert len(active_schemas) == 0
        
        # But should appear in all schemas list
        all_schemas = await backend.list_schemas(active_only=False)
        assert len(all_schemas) == 1
        assert all_schemas[0].schema_name == "deactivate_test"
        assert all_schemas[0].active is False


@pytest.mark.asyncio
async def test_jsonl_retention_policy():
    """Test retention policy application in JSONL backend."""
    with tempfile.TemporaryDirectory() as tmpdir:
        log_path = Path(tmpdir) / "audit.jsonl"
        
        backend = JSONLAuditWriter(log_path)
        
        # Create schema with short retention
        schema = AuditSchema(
            schema_name="retention_test",
            version=1,
            description="Test retention policy",
            retention_days=1  # Very short for testing
        )
        await backend.create_schema(schema)
        
        # Write a record
        record = AuditRecord(
            schema_name="retention_test",
            operation_type="tool",
            operation_name="test_tool",
            caller_type="cli",
            input_data={"test": "data"},
            duration_ms=100,
            operation_status="success"
        )
        
        # Manually set timestamp to be old
        from datetime import timedelta
        old_timestamp = datetime.now(timezone.utc) - timedelta(days=2)
        record.timestamp = old_timestamp
        
        await backend.write_record(record)
        backend.shutdown()
        
        # Apply retention policies
        deleted_counts = await backend.apply_retention_policies()
        
        # Should have deleted 1 record
        assert deleted_counts["retention_test:v1"] == 1
        
        # Verify record is gone
        remaining_records = await backend.query_records()
        assert len(remaining_records) == 0