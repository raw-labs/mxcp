"""Test JSONL backend implementation specifics."""

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

from mxcp.sdk.audit import (
    AuditRecordModel,
    AuditSchemaModel,
    EvidenceLevel,
    FieldDefinitionModel,
    FieldRedactionModel,
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

        # Base path should NOT be created as a file
        # Instead, a segment file should exist
        assert not log_path.exists() or log_path.stat().st_size == 0
        assert backend._current_segment.exists()
        assert not schema_path.exists()

        # Create a schema - this should create the schema file
        schema = AuditSchemaModel(schema_name="test_schema", version=1, description="Test schema")
        await backend.create_schema(schema)

        # Schema file should now exist
        assert schema_path.exists()

        # Write a record - this should create the log file
        record = AuditRecordModel(
            schema_name="test_schema",
            operation_type="tool",
            operation_name="test_tool",
            caller_type="cli",
            input_data={"test": "data"},
            duration_ms=100,
            operation_status="success",
        )

        await backend.write_record(record)
        await backend.close()  # Force flush

        # Segment file should exist
        assert backend._current_segment.exists()


@pytest.mark.asyncio
async def test_jsonl_schema_persistence():
    """Test that schemas are properly persisted to JSONL."""
    with tempfile.TemporaryDirectory() as tmpdir:
        log_path = Path(tmpdir) / "audit.jsonl"
        Path(tmpdir) / "audit_schemas.jsonl"

        # Create backend and schema
        backend = JSONLAuditWriter(log_path)

        schema = AuditSchemaModel(
            schema_name="persist_test",
            version=1,
            description="Persistence test schema",
            retention_days=180,
            evidence_level=EvidenceLevel.DETAILED,
            fields=[
                FieldDefinitionModel(name="field1", type="string", sensitive=True),
                FieldDefinitionModel(name="field2", type="number"),
            ],
            field_redactions=[
                FieldRedactionModel(field_path="field1", strategy=RedactionStrategy.PARTIAL)
            ],
            extract_fields=["field2"],
            indexes=["field1", "field2"],
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

        await backend2.close()


@pytest.mark.asyncio
async def test_jsonl_record_format():
    """Test that records are written in correct JSONL format."""
    with tempfile.TemporaryDirectory() as tmpdir:
        log_path = Path(tmpdir) / "audit.jsonl"

        backend = JSONLAuditWriter(log_path)

        # Create schema and record
        schema = AuditSchemaModel(schema_name="format_test", version=1, description="Format test")
        await backend.create_schema(schema)

        record = AuditRecordModel(
            schema_name="format_test",
            operation_type="tool",
            operation_name="format_tool",
            caller_type="cli",
            input_data={"key": "value", "number": 42},
            output_data={"result": "success"},
            duration_ms=150,
            user_id="user123",
            session_id="session456",
            operation_status="success",
        )

        record_id = await backend.write_record(record)
        await backend.close()

        # Read the JSONL file and verify format
        with open(backend._current_segment) as f:
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
        schema = AuditSchemaModel(
            schema_name="redaction_test",
            version=1,
            description="Test redaction serialization",
            field_redactions=[
                FieldRedactionModel(field_path="email", strategy=RedactionStrategy.EMAIL),
                FieldRedactionModel(
                    field_path="ssn", strategy=RedactionStrategy.PARTIAL, options={"show_last": 4}
                ),
                FieldRedactionModel(field_path="secret", strategy=RedactionStrategy.HASH),
                FieldRedactionModel(
                    field_path="description",
                    strategy=RedactionStrategy.TRUNCATE,
                    options={"length": 20},
                ),
                FieldRedactionModel(field_path="sensitive", strategy=RedactionStrategy.FULL),
            ],
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

        await backend2.close()


@pytest.mark.asyncio
async def test_jsonl_concurrent_writes():
    """Test JSONL backend handles concurrent writes safely."""
    with tempfile.TemporaryDirectory() as tmpdir:
        log_path = Path(tmpdir) / "audit.jsonl"

        backend = JSONLAuditWriter(log_path)

        # Create schema
        schema = AuditSchemaModel(
            schema_name="concurrent_test", version=1, description="Test concurrent writes"
        )
        await backend.create_schema(schema)

        # Write multiple records concurrently
        import asyncio

        async def write_record(i):
            record = AuditRecordModel(
                schema_name="concurrent_test",
                operation_type="tool",
                operation_name=f"tool_{i}",
                caller_type="cli",
                input_data={"index": i},
                duration_ms=i * 10,
                operation_status="success",
            )
            return await backend.write_record(record)

        # Write 10 records concurrently
        tasks = [write_record(i) for i in range(10)]
        record_ids = await asyncio.gather(*tasks)

        await backend.close()

        # Verify all records were written
        assert len(record_ids) == 10
        assert len(set(record_ids)) == 10  # All IDs should be unique

        # Verify file contains all records
        lines = []
        for f in backend._list_segment_files():
            with open(f) as fh:
                lines.extend(fh.readlines())

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
        try:
            # Create schema
            schema = AuditSchemaModel(
                schema_name="query_test", version=1, description="Test query filtering"
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
                record = AuditRecordModel(
                    schema_name="query_test",
                    operation_type=data["type"],
                    operation_name=data["name"],
                    caller_type="cli",
                    input_data={"user": data["user"]},
                    duration_ms=100,
                    operation_status="success",
                    user_id=data["user"],
                )
                await backend.write_record(record)

            # Ensure events are flushed before querying
            await backend.flush()

            # Test various query filters

            # Filter by operation type
            tool_records = [r async for r in backend.query_records(operation_types=["tool"])]
            assert len(tool_records) == 3

            # Filter by operation names
            specific_tools = [
                r async for r in backend.query_records(operation_names=["tool_a", "tool_b"])
            ]
            assert len(specific_tools) == 2

            # Filter by user
            alice_records = [r async for r in backend.query_records(user_ids=["alice"])]
            assert len(alice_records) == 2

            # Combine filters
            alice_tools = [
                r async for r in backend.query_records(operation_types=["tool"], user_ids=["alice"])
            ]
            assert len(alice_tools) == 1
            assert alice_tools[0].operation_name == "tool_a"
        finally:
            await backend.close()


@pytest.mark.asyncio
async def test_jsonl_schema_deactivation():
    """Test schema deactivation in JSONL backend."""
    with tempfile.TemporaryDirectory() as tmpdir:
        log_path = Path(tmpdir) / "audit.jsonl"

        backend = JSONLAuditWriter(log_path)
        try:
            # Create active schema
            schema = AuditSchemaModel(
                schema_name="deactivate_test", version=1, description="Test deactivation"
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
        finally:
            await backend.close()


@pytest.mark.asyncio
async def test_startup_creates_segment_not_base_path():
    """Startup creates a timestamped segment, not the base path."""
    with tempfile.TemporaryDirectory() as tmpdir:
        log_path = Path(tmpdir) / "audit.jsonl"
        backend = JSONLAuditWriter(log_path)
        try:
            assert not log_path.exists()
            assert backend._current_segment.exists()
            assert backend._current_segment.name.startswith("audit-")
            assert backend._current_segment.suffix == ".jsonl"
        finally:
            await backend.close()


@pytest.mark.asyncio
async def test_list_segment_files_excludes_empty():
    """_list_segment_files() excludes empty (0-byte) files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        log_path = Path(tmpdir) / "audit.jsonl"
        backend = JSONLAuditWriter(log_path)
        try:
            files = backend._list_segment_files()
            assert len(files) == 0
        finally:
            await backend.close()


@pytest.mark.asyncio
async def test_list_segment_files_includes_legacy():
    """_list_segment_files() includes legacy file if non-empty."""
    with tempfile.TemporaryDirectory() as tmpdir:
        log_path = Path(tmpdir) / "audit.jsonl"
        log_path.write_text('{"record_id":"legacy"}\n')
        backend = JSONLAuditWriter(log_path)
        try:
            files = backend._list_segment_files()
            assert log_path in files
        finally:
            await backend.close()


@pytest.mark.asyncio
async def test_list_segment_files_sorted_lexicographically():
    """_list_segment_files() returns segments sorted by filename."""
    with tempfile.TemporaryDirectory() as tmpdir:
        log_path = Path(tmpdir) / "audit.jsonl"
        backend = JSONLAuditWriter(log_path)
        try:
            schema = AuditSchemaModel(schema_name="test", version=1, description="test")
            await backend.create_schema(schema)
            record = AuditRecordModel(
                schema_name="test", operation_type="tool", operation_name="t",
                caller_type="cli", input_data={}, duration_ms=1, operation_status="success",
            )
            await backend.write_record(record)
            await backend.flush()
            files = backend._list_segment_files()
            assert files == sorted(files)
        finally:
            await backend.close()


@pytest.mark.asyncio
async def test_same_second_collision():
    """Two segments created in same second get distinct names."""
    with tempfile.TemporaryDirectory() as tmpdir:
        log_path = Path(tmpdir) / "audit.jsonl"
        backend = JSONLAuditWriter(log_path)
        try:
            seg1 = backend._current_segment
            seg2 = backend._new_segment()
            assert seg1 != seg2
            assert seg2.exists()
        finally:
            await backend.close()


@pytest.mark.asyncio
async def test_rotation_on_size_threshold():
    """Writing past size threshold creates a new segment."""
    with tempfile.TemporaryDirectory() as tmpdir:
        log_path = Path(tmpdir) / "audit.jsonl"
        backend = JSONLAuditWriter(log_path, max_file_size=500)
        try:
            schema = AuditSchemaModel(schema_name="rot_test", version=1, description="test")
            await backend.create_schema(schema)

            first_segment = backend._current_segment

            for i in range(20):
                record = AuditRecordModel(
                    schema_name="rot_test", operation_type="tool",
                    operation_name=f"tool_{i}", caller_type="cli",
                    input_data={"data": "x" * 50}, duration_ms=i,
                    operation_status="success",
                )
                await backend.write_record(record)

            await backend.flush()

            assert backend._current_segment != first_segment
            files = backend._list_segment_files()
            assert len(files) >= 2
        finally:
            await backend.close()


@pytest.mark.asyncio
async def test_jsonl_retention_policy():
    """Test retention policy application in JSONL backend."""
    with tempfile.TemporaryDirectory() as tmpdir:
        log_path = Path(tmpdir) / "audit.jsonl"

        backend = JSONLAuditWriter(log_path)

        # Create schema with short retention
        schema = AuditSchemaModel(
            schema_name="retention_test",
            version=1,
            description="Test retention policy",
            retention_days=1,  # Very short for testing
        )
        await backend.create_schema(schema)

        # Write a record
        record = AuditRecordModel(
            schema_name="retention_test",
            operation_type="tool",
            operation_name="test_tool",
            caller_type="cli",
            input_data={"test": "data"},
            duration_ms=100,
            operation_status="success",
        )

        # Manually set timestamp to be old
        from datetime import timedelta

        old_timestamp = datetime.now(timezone.utc) - timedelta(days=2)
        record.timestamp = old_timestamp

        await backend.write_record(record)
        await backend.flush()

        # Move to a new segment so the old one can be evaluated by retention
        backend._new_segment()

        # Apply retention policies
        deleted_counts = await backend.apply_retention_policies()

        # Should have deleted 1 record
        assert deleted_counts["retention_test:v1"] == 1

        # Verify record is gone
        remaining_records = [r async for r in backend.query_records()]
        assert len(remaining_records) == 0

        await backend.close()


@pytest.mark.asyncio
async def test_query_spans_multiple_segments():
    """Queries return results from all segment files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        log_path = Path(tmpdir) / "audit.jsonl"
        backend = JSONLAuditWriter(log_path, max_file_size=500)
        try:
            schema = AuditSchemaModel(schema_name="multi_seg", version=1, description="test")
            await backend.create_schema(schema)

            for i in range(20):
                record = AuditRecordModel(
                    schema_name="multi_seg", operation_type="tool",
                    operation_name=f"tool_{i}", caller_type="cli",
                    input_data={"data": "x" * 50}, duration_ms=i,
                    operation_status="success",
                )
                await backend.write_record(record)

            await backend.flush()

            assert len(backend._list_segment_files()) >= 2

            all_records = [r async for r in backend.query_records()]
            assert len(all_records) == 20
        finally:
            await backend.close()


@pytest.mark.asyncio
async def test_query_with_legacy_file():
    """Queries include records from legacy file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        log_path = Path(tmpdir) / "audit.jsonl"

        legacy_record = {
            "schema_name": "legacy_test", "schema_version": 1,
            "record_id": "legacy-001",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "operation_type": "tool", "operation_name": "legacy_tool",
            "operation_status": "success", "duration_ms": 100,
            "caller_type": "cli", "input_data": {}, "output_data": None,
            "error": None, "policies_evaluated": [], "policy_decision": None,
            "policy_reason": None, "business_context": {},
            "execution_events": [], "prev_hash": None,
            "record_hash": None, "signature": None,
        }
        log_path.write_text(json.dumps(legacy_record) + "\n")

        backend = JSONLAuditWriter(log_path)
        try:
            schema = AuditSchemaModel(schema_name="legacy_test", version=1, description="test")
            await backend.create_schema(schema)

            record = AuditRecordModel(
                schema_name="legacy_test", operation_type="tool",
                operation_name="new_tool", caller_type="cli",
                input_data={}, duration_ms=50, operation_status="success",
            )
            await backend.write_record(record)
            await backend.flush()

            all_records = [r async for r in backend.query_records()]
            names = {r.operation_name for r in all_records}
            assert "legacy_tool" in names
            assert "new_tool" in names
        finally:
            await backend.close()


@pytest.mark.asyncio
async def test_get_record_across_segments():
    """get_record finds a record regardless of which segment it's in."""
    with tempfile.TemporaryDirectory() as tmpdir:
        log_path = Path(tmpdir) / "audit.jsonl"
        backend = JSONLAuditWriter(log_path, max_file_size=500)
        try:
            schema = AuditSchemaModel(schema_name="get_test", version=1, description="test")
            await backend.create_schema(schema)

            record_ids = []
            for i in range(20):
                record = AuditRecordModel(
                    schema_name="get_test", operation_type="tool",
                    operation_name=f"tool_{i}", caller_type="cli",
                    input_data={"data": "x" * 50}, duration_ms=i,
                    operation_status="success",
                )
                rid = await backend.write_record(record)
                record_ids.append(rid)

            await backend.flush()
            assert len(backend._list_segment_files()) >= 2

            first = await backend.get_record(record_ids[0])
            last = await backend.get_record(record_ids[-1])
            assert first is not None
            assert last is not None
            assert first.operation_name == "tool_0"
            assert last.operation_name == "tool_19"
        finally:
            await backend.close()


@pytest.mark.asyncio
async def test_query_empty_file_list():
    """Queries on empty file list return no results without error."""
    with tempfile.TemporaryDirectory() as tmpdir:
        log_path = Path(tmpdir) / "audit.jsonl"
        backend = JSONLAuditWriter(log_path)
        try:
            all_records = [r async for r in backend.query_records()]
            assert len(all_records) == 0
        finally:
            await backend.close()


@pytest.mark.asyncio
async def test_retention_deletes_expired_segment():
    """Segment with all expired records gets deleted."""
    with tempfile.TemporaryDirectory() as tmpdir:
        log_path = Path(tmpdir) / "audit.jsonl"
        backend = JSONLAuditWriter(log_path, max_file_size=500)
        try:
            schema = AuditSchemaModel(
                schema_name="ret_test", version=1,
                description="test", retention_days=1,
            )
            await backend.create_schema(schema)

            from datetime import timedelta
            old_time = datetime.now(timezone.utc) - timedelta(days=5)
            for i in range(10):
                record = AuditRecordModel(
                    schema_name="ret_test", operation_type="tool",
                    operation_name=f"old_{i}", caller_type="cli",
                    input_data={"data": "x" * 50}, duration_ms=i,
                    operation_status="success", timestamp=old_time,
                )
                await backend.write_record(record)

            await backend.flush()

            for i in range(10):
                record = AuditRecordModel(
                    schema_name="ret_test", operation_type="tool",
                    operation_name=f"new_{i}", caller_type="cli",
                    input_data={"data": "x" * 50}, duration_ms=i,
                    operation_status="success",
                )
                await backend.write_record(record)

            await backend.flush()

            files_before = backend._list_segment_files()
            assert len(files_before) >= 2

            counts = await backend.apply_retention_policies()

            files_after = backend._list_segment_files()
            assert len(files_after) < len(files_before)
            assert sum(counts.values()) >= 10
        finally:
            await backend.close()


@pytest.mark.asyncio
async def test_retention_keeps_fresh_segment():
    """Segment with fresh records is kept."""
    with tempfile.TemporaryDirectory() as tmpdir:
        log_path = Path(tmpdir) / "audit.jsonl"
        backend = JSONLAuditWriter(log_path)
        try:
            schema = AuditSchemaModel(
                schema_name="keep_test", version=1,
                description="test", retention_days=30,
            )
            await backend.create_schema(schema)

            record = AuditRecordModel(
                schema_name="keep_test", operation_type="tool",
                operation_name="fresh", caller_type="cli",
                input_data={}, duration_ms=1, operation_status="success",
            )
            await backend.write_record(record)
            await backend.flush()

            counts = await backend.apply_retention_policies()
            assert sum(counts.values()) == 0

            remaining = [r async for r in backend.query_records()]
            assert len(remaining) == 1
        finally:
            await backend.close()


@pytest.mark.asyncio
async def test_retention_never_deletes_current_segment():
    """Current segment is never deleted even if all records are expired."""
    with tempfile.TemporaryDirectory() as tmpdir:
        log_path = Path(tmpdir) / "audit.jsonl"
        backend = JSONLAuditWriter(log_path)
        try:
            schema = AuditSchemaModel(
                schema_name="cur_test", version=1,
                description="test", retention_days=1,
            )
            await backend.create_schema(schema)

            from datetime import timedelta
            old_time = datetime.now(timezone.utc) - timedelta(days=5)
            record = AuditRecordModel(
                schema_name="cur_test", operation_type="tool",
                operation_name="old", caller_type="cli",
                input_data={}, duration_ms=1,
                operation_status="success", timestamp=old_time,
            )
            await backend.write_record(record)
            await backend.flush()

            await backend.apply_retention_policies()

            assert backend._current_segment.exists()
        finally:
            await backend.close()


@pytest.mark.asyncio
async def test_retention_multi_schema_longest_wins():
    """Segment with multiple schemas uses the longest retention_days."""
    with tempfile.TemporaryDirectory() as tmpdir:
        log_path = Path(tmpdir) / "audit.jsonl"
        backend = JSONLAuditWriter(log_path, max_file_size=50 * 1024 * 1024)
        try:
            schema_a = AuditSchemaModel(
                schema_name="short_ret", version=1,
                description="test", retention_days=1,
            )
            schema_b = AuditSchemaModel(
                schema_name="long_ret", version=1,
                description="test", retention_days=365,
            )
            await backend.create_schema(schema_a)
            await backend.create_schema(schema_b)

            from datetime import timedelta
            old_time = datetime.now(timezone.utc) - timedelta(days=5)

            for schema_name in ["short_ret", "long_ret"]:
                record = AuditRecordModel(
                    schema_name=schema_name, operation_type="tool",
                    operation_name="test", caller_type="cli",
                    input_data={}, duration_ms=1,
                    operation_status="success", timestamp=old_time,
                )
                await backend.write_record(record)

            await backend.flush()

            backend._new_segment()

            counts = await backend.apply_retention_policies()

            assert sum(counts.values()) == 0
        finally:
            await backend.close()
