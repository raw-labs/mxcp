"""Test backend-agnostic exporters functionality."""

import asyncio
import csv
import json
import tempfile
from pathlib import Path

import pytest

from mxcp.sdk.audit import AuditLogger, AuditSchema
from mxcp.server.services.audit.exporters import export_to_csv, export_to_json, export_to_jsonl


@pytest.mark.asyncio
async def test_exporters_with_jsonl_backend():
    """Test exporters work with JSONL backend."""
    with tempfile.TemporaryDirectory() as tmpdir:
        log_path = Path(tmpdir) / "audit.jsonl"
        csv_path = Path(tmpdir) / "export.csv"
        jsonl_path = Path(tmpdir) / "export.jsonl"
        json_path = Path(tmpdir) / "export.json"

        # Create logger with JSONL backend
        logger = await AuditLogger.jsonl(log_path=log_path)

        # Create schema and log events
        schema = AuditSchema(
            schema_name="export_test", version=1, description="Test schema for export"
        )
        await logger.create_schema(schema)

        for i in range(5):
            await logger.log_event(
                caller_type="cli",
                event_type="tool",
                name=f"tool_{i}",
                input_params={"index": i, "data": f"test_{i}"},
                duration_ms=100,
                schema_name="export_test",
                user_id=f"user_{i % 2}",
                status="success",
            )

        # Flush writes
        await asyncio.sleep(0.1)
        await logger.backend.close()

        # Test CSV export
        count = await export_to_csv(logger, csv_path)
        assert count == 5
        assert csv_path.exists()

        # Verify CSV content
        with open(csv_path) as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            assert len(rows) == 5
            assert all("operation_name" in row for row in rows)

        # Test JSONL export
        count = await export_to_jsonl(logger, jsonl_path)
        assert count == 5
        assert jsonl_path.exists()

        # Verify JSONL content
        with open(jsonl_path) as f:
            lines = f.readlines()
            assert len(lines) == 5
            for line in lines:
                data = json.loads(line)
                assert "operation_name" in data

        # Test JSON export
        count = await export_to_json(logger, json_path)
        assert count == 5
        assert json_path.exists()

        # Verify JSON content
        with open(json_path) as f:
            data = json.load(f)
            assert isinstance(data, list)
            assert len(data) == 5
            assert all("operation_name" in record for record in data)

        await logger.close()


@pytest.mark.asyncio
async def test_exporters_with_noop_backend():
    """Test exporters work with NoOp backend (should export nothing)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        csv_path = Path(tmpdir) / "export.csv"
        jsonl_path = Path(tmpdir) / "export.jsonl"
        json_path = Path(tmpdir) / "export.json"

        # Create logger with NoOp backend
        logger = await AuditLogger.disabled()

        # Try to log events (will be discarded)
        for i in range(5):
            await logger.log_event(
                caller_type="cli",
                event_type="tool",
                name=f"tool_{i}",
                input_params={"index": i},
                duration_ms=100,
                schema_name="test_schema",
                status="success",
            )

        # Test CSV export - should export 0 records
        count = await export_to_csv(logger, csv_path)
        assert count == 0
        assert csv_path.exists()

        # Verify CSV is empty (except header)
        with open(csv_path) as f:
            lines = f.readlines()
            assert len(lines) == 0  # No data, not even headers since no records

        # Test JSONL export - should export 0 records
        count = await export_to_jsonl(logger, jsonl_path)
        assert count == 0

        # Test JSON export - should export empty array
        count = await export_to_json(logger, json_path)
        assert count == 0
        assert json_path.exists()

        with open(json_path) as f:
            data = json.load(f)
            assert data == []

        await logger.close()


@pytest.mark.asyncio
async def test_exporters_with_filters():
    """Test exporters correctly apply filters."""
    with tempfile.TemporaryDirectory() as tmpdir:
        log_path = Path(tmpdir) / "audit.jsonl"
        csv_path = Path(tmpdir) / "filtered.csv"

        # Create logger
        logger = await AuditLogger.jsonl(log_path=log_path)

        # Create schema and log varied events
        schema = AuditSchema(
            schema_name="filter_export_test",
            version=1,
            description="Test schema for filtered export",
        )
        await logger.create_schema(schema)

        # Log 10 events with different attributes
        for i in range(10):
            await logger.log_event(
                caller_type="cli",
                event_type="tool",
                name=f"tool_{i}",
                input_params={"index": i},
                duration_ms=100,
                schema_name="filter_export_test",
                user_id=f"user_{i % 3}",  # 3 different users
                status="success" if i < 7 else "error",
                policy_decision="allow" if i < 5 else "deny",
            )

        # Flush writes
        await asyncio.sleep(0.1)
        await logger.backend.close()

        # Export only user_0 records
        filters = {"user_id": "user_0"}
        count = await export_to_csv(logger, csv_path, filters=filters)
        assert count == 4  # Records 0, 3, 6, 9

        with open(csv_path) as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            assert len(rows) == 4
            assert all(row["user_id"] == "user_0" for row in rows)

        # Export only error records
        csv_path2 = Path(tmpdir) / "errors.csv"
        filters = {"status": "error"}
        count = await export_to_csv(logger, csv_path2, filters=filters)
        assert count == 3  # Records 7, 8, 9

        # Export with policy filter
        csv_path3 = Path(tmpdir) / "denied.csv"
        filters = {"policy": "deny"}
        count = await export_to_csv(logger, csv_path3, filters=filters)
        assert count == 5  # Records 5-9

        await logger.close()


@pytest.mark.asyncio
async def test_exporters_memory_efficiency():
    """Test exporters handle large datasets efficiently."""
    with tempfile.TemporaryDirectory() as tmpdir:
        log_path = Path(tmpdir) / "large_audit.jsonl"
        csv_path = Path(tmpdir) / "large_export.csv"

        # Create logger
        logger = await AuditLogger.jsonl(log_path=log_path)

        # Create schema
        schema = AuditSchema(
            schema_name="large_export_test", version=1, description="Test schema for large export"
        )
        await logger.create_schema(schema)

        # Log many events
        num_events = 1000
        for i in range(num_events):
            await logger.log_event(
                caller_type="cli",
                event_type="tool",
                name=f"tool_{i}",
                input_params={"index": i, "data": "x" * 100},  # Some data
                duration_ms=100,
                schema_name="large_export_test",
                status="success",
            )
            # Periodic sleep
            if i % 100 == 0:
                await asyncio.sleep(0.01)

        # Flush writes
        await asyncio.sleep(0.5)
        await logger.backend.close()

        # Export to CSV - should handle streaming efficiently
        count = await export_to_csv(logger, csv_path)
        assert count == num_events

        # Verify file was created and has expected rows
        line_count = 0
        with open(csv_path) as f:
            reader = csv.DictReader(f)
            for _row in reader:
                line_count += 1

        assert line_count == num_events

        await logger.close()
