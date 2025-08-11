"""Test the high-level AuditLogger interface.

These tests focus on the AuditLogger class which provides the main
interface that applications use for audit logging.
"""

import json
import tempfile
import time
from pathlib import Path

import pytest

from mxcp.sdk.audit import (
    AuditLogger,
    AuditSchema,
    FieldDefinition,
    FieldRedaction,
    RedactionStrategy,
)


@pytest.mark.asyncio
async def test_audit_logger_creates_records():
    """Test that AuditLogger creates AuditRecord internally."""

    with tempfile.TemporaryDirectory() as tmpdir:
        log_path = Path(tmpdir) / "audit.jsonl"

        # Create logger
        logger = await AuditLogger.jsonl(log_path=log_path)

        # Log an event
        await logger.log_event(
            caller_type="http",
            event_type="tool",
            name="test_tool",
            input_params={"query": "SELECT * FROM users", "limit": 10},
            duration_ms=150,
            policy_decision="allow",
            reason=None,
            status="success",
            error=None,
            schema_name="mxcp.endpoints",  # Use the default endpoint schema
        )

        # Give background thread time to write
        time.sleep(0.5)

        # Shutdown
        logger.shutdown()

        # Additional wait after shutdown
        time.sleep(0.1)

        # Verify log was written
        assert log_path.exists()

        with open(log_path, "r") as f:
            line = f.readline()
            data = json.loads(line)

            # Verify the format matches expected output (new format)
            assert data["operation_type"] == "tool"
            assert data["operation_name"] == "test_tool"
            assert data["caller_type"] == "http"
            assert data["operation_status"] == "success"
            assert data["duration_ms"] == 150
            assert data["policy_decision"] == "allow"
            assert data["input_data"] == {"query": "SELECT * FROM users", "limit": 10}


@pytest.mark.asyncio
async def test_audit_logger_disabled():
    """Test that disabled logger doesn't write anything."""

    with tempfile.TemporaryDirectory() as tmpdir:
        log_path = Path(tmpdir) / "audit.jsonl"

        # Create disabled logger
        logger = await AuditLogger.disabled()

        # Try to log an event
        await logger.log_event(
            caller_type="cli",
            event_type="tool",
            name="should_not_appear",
            input_params={"test": "data"},
            duration_ms=50,
            schema_name="test_schema",
        )

        # Shutdown
        logger.shutdown()

        # File should not exist
        assert not log_path.exists()


@pytest.mark.asyncio
async def test_audit_logger_sensitive_data_redaction():
    """Test that AuditLogger redacts sensitive data based on schema."""
    # Force a new instance

    with tempfile.TemporaryDirectory() as tmpdir:
        log_path = Path(tmpdir) / "audit.jsonl"

        logger = await AuditLogger.jsonl(log_path=log_path)

        # Create a schema with redaction rules
        auth_schema = AuditSchema(
            schema_name="test_auth",
            version=1,
            description="Test auth schema with redaction",
            fields=[
                FieldDefinition("username", "string"),
                FieldDefinition("password", "string", sensitive=True),
                FieldDefinition("config", "object"),
            ],
            field_redactions=[
                FieldRedaction("password", RedactionStrategy.FULL),
                FieldRedaction("config.api_key", RedactionStrategy.FULL),
            ],
        )

        # Register the schema
        await logger.create_schema(auth_schema)

        # Log event using the schema
        await logger.log_event(
            caller_type="http",
            event_type="tool",
            name="auth_tool",
            input_params={
                "username": "john",
                "password": "secret123",
                "config": {"api_key": "sk_live_abcdef", "endpoint": "https://api.example.com"},
            },
            duration_ms=75,
            schema_name="test_auth",
        )

        # Give time to write
        time.sleep(0.5)
        logger.shutdown()
        time.sleep(0.1)

        # Verify redaction - need to find the actual audit record
        with open(log_path, "r") as f:
            lines = f.readlines()
            # Find the audit record (not schema)
            record = None
            for line in lines:
                data = json.loads(line)
                if "operation_type" in data:
                    record = data
                    break

            assert record is not None
            assert record["input_data"]["username"] == "john"
            assert record["input_data"]["password"] == "[REDACTED]"
            assert record["input_data"]["config"]["api_key"] == "[REDACTED]"
            assert record["input_data"]["config"]["endpoint"] == "https://api.example.com"


@pytest.mark.asyncio
async def test_audit_logger_querying():
    """Test AuditLogger query functionality."""
    # Force a new instance

    with tempfile.TemporaryDirectory() as tmpdir:
        log_path = Path(tmpdir) / "audit.jsonl"

        logger = await AuditLogger.jsonl(log_path=log_path)

        # Create a test schema
        test_schema = AuditSchema(
            schema_name="logger_query_test",
            version=1,
            description="Test schema for logger querying",
        )
        await logger.create_schema(test_schema)

        # Log several events
        for i in range(5):
            await logger.log_event(
                caller_type="cli" if i % 2 == 0 else "http",
                event_type="tool",
                name=f"test_tool_{i}",
                input_params={"index": i, "test": "data"},
                duration_ms=i * 10,
                schema_name="logger_query_test",
                user_id=f"user_{i % 3}",  # 3 different users
                status="success" if i < 4 else "error",
            )

        # Give time for async writes
        import asyncio

        await asyncio.sleep(0.1)
        logger.backend.shutdown()  # Force flush

        # Query all records
        all_records = [r async for r in logger.query_records()]
        assert len(all_records) == 5

        # Query by schema
        schema_records = [r async for r in logger.query_records(schema_name="logger_query_test")]
        assert len(schema_records) == 5

        # Query by operation type
        tool_records = [r async for r in logger.query_records(operation_types=["tool"])]
        assert len(tool_records) == 5

        # Query by user
        user_0_records = [r async for r in logger.query_records(user_ids=["user_0"])]
        assert len(user_0_records) == 2  # user_0 appears at index 0 and 3

        # Query with limit
        limited_records = [r async for r in logger.query_records(limit=3)]
        assert len(limited_records) == 3

        # Query specific operations
        specific_records = [
            r async for r in logger.query_records(operation_names=["test_tool_1", "test_tool_2"])
        ]
        assert len(specific_records) == 2

        logger.shutdown()


@pytest.mark.asyncio
async def test_audit_logger_sync_queries():
    """Test AuditLogger sync query interface."""
    # Force a new instance

    with tempfile.TemporaryDirectory() as tmpdir:
        log_path = Path(tmpdir) / "sync_audit.jsonl"

        logger = await AuditLogger.jsonl(log_path=log_path)

        # Create schema and log event
        test_schema = AuditSchema(
            schema_name="sync_test", version=1, description="Sync test schema"
        )
        await logger.create_schema(test_schema)

        await logger.log_event(
            caller_type="cli",
            event_type="tool",
            name="sync_tool",
            input_params={"sync": True},
            duration_ms=50,
            schema_name="sync_test",
            status="success",
        )

        # Give time for write and force flush
        time.sleep(0.1)
        logger.backend.shutdown()

        # Query records using async interface
        records = [r async for r in logger.query_records(operation_names=["sync_tool"])]
        assert len(records) == 1
        assert records[0].operation_name == "sync_tool"

        # Get specific record
        record_id = records[0].record_id
        record = await logger.get_record(record_id)
        assert record is not None
        assert record.operation_name == "sync_tool"

        logger.shutdown()
