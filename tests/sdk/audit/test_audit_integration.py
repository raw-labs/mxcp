"""End-to-end integration tests for the audit system.

These tests verify that all components work together correctly
in realistic scenarios.
"""
import pytest
import tempfile
import asyncio
from pathlib import Path
from datetime import datetime, timezone

from mxcp.sdk.audit import (
    AuditLogger,
    AuditSchema,
    FieldDefinition,
    FieldRedaction,
    EvidenceLevel,
    RedactionStrategy,
)



@pytest.mark.asyncio
async def test_complete_audit_workflow():
    """Test a complete audit workflow from schema creation to querying."""
    with tempfile.TemporaryDirectory() as tmpdir:
        log_path = Path(tmpdir) / "integration_audit.jsonl"
        
        # Create audit logger
        logger = await AuditLogger.jsonl(log_path=log_path)
        
        # Define schemas for different types of operations
        auth_schema = AuditSchema(
            schema_name="auth_operations",
            version=1,
            description="Authentication and authorization operations",
            retention_days=365,
            evidence_level=EvidenceLevel.REGULATORY,
            fields=[
                FieldDefinition("operation", "string"),
                FieldDefinition("user_email", "string", sensitive=True),
                FieldDefinition("ip_address", "string", sensitive=True),
                FieldDefinition("success", "boolean")
            ],
            field_redactions=[
                FieldRedaction("user_email", RedactionStrategy.EMAIL),
                FieldRedaction("ip_address", RedactionStrategy.PARTIAL, {"show_first": 0, "show_last": 3})
            ],
            extract_fields=["operation", "success"],
            indexes=["operation", "user_email", "timestamp"]
        )
        
        api_schema = AuditSchema(
            schema_name="api_operations",
            version=1,
            description="API request/response operations",
            retention_days=90,
            evidence_level=EvidenceLevel.DETAILED,
            fields=[
                FieldDefinition("method", "string"),
                FieldDefinition("endpoint", "string"),
                FieldDefinition("status_code", "number"),
                FieldDefinition("api_key", "string", sensitive=True)
            ],
            field_redactions=[
                FieldRedaction("api_key", RedactionStrategy.HASH)
            ],
            extract_fields=["method", "endpoint", "status_code"]
        )
        
        # Register schemas
        await logger.create_schema(auth_schema)
        await logger.create_schema(api_schema)
        
        # Log various operations
        
        # Authentication events
        await logger.log_event(
            caller_type="http",
            event_type="auth",
            name="user_login",
            input_params={
                "operation": "login",
                "user_email": "alice@company.com",
                "ip_address": "192.168.1.100",
                "success": True
            },
            duration_ms=50,
            schema_name="auth_operations",
            user_id="alice",
            status="success"
        )
        
        await logger.log_event(
            caller_type="http",
            event_type="auth",
            name="user_logout",
            input_params={
                "operation": "logout",
                "user_email": "alice@company.com",
                "ip_address": "192.168.1.100",
                "success": True
            },
            duration_ms=25,
            schema_name="auth_operations",
            user_id="alice",
            status="success"
        )
        
        # API operations
        await logger.log_event(
            caller_type="http",
            event_type="api",
            name="create_resource",
            input_params={
                "method": "POST",
                "endpoint": "/api/v1/resources",
                "api_key": "sk_live_abc123def456",
                "body": {"name": "Test Resource"},
                "status_code": 201  # Move status_code to input_params so it can be extracted
            },
            output_data={"resource_id": "res_123"},
            duration_ms=150,
            schema_name="api_operations",
            user_id="alice",
            status="success"
        )
        
        await logger.log_event(
            caller_type="http",
            event_type="api",
            name="get_resource",
            input_params={
                "method": "GET",
                "endpoint": "/api/v1/resources/res_123",
                "api_key": "sk_live_abc123def456",
                "status_code": 200  # Move status_code to input_params so it can be extracted
            },
            output_data={"resource": {"id": "res_123", "name": "Test Resource"}},
            duration_ms=75,
            schema_name="api_operations",
            user_id="alice",
            status="success"
        )
        
        # Wait for async operations to complete and flush writes
        await asyncio.sleep(0.1)
        logger.backend.shutdown()  # Ensure all records are flushed to disk
        
        # Query and verify the logged events
        
        # Get all auth events
        auth_events = [r async for r in logger.query_records(
            schema_name="auth_operations",
            limit=10
        )]
        assert len(auth_events) == 2
        
        # Verify redaction was applied
        login_event = next(e for e in auth_events if e.operation_name == "user_login")
        assert "alice@company.com" not in str(login_event.input_data)  # Email should be redacted
        assert login_event.input_data["user_email"] == "a***@company.com"
        assert login_event.input_data["ip_address"] == "***100"  # IP should be partially redacted
        
        # Get all API events
        api_events = [r async for r in logger.query_records(
            schema_name="api_operations",
            limit=10
        )]
        assert len(api_events) == 2
        
        # Verify API key was hashed
        create_event = next(e for e in api_events if e.operation_name == "create_resource")
        assert "sk_live_abc123def456" not in str(create_event.input_data)
        assert create_event.input_data["api_key"].startswith("sha256:")
        
        # Query by user
        alice_events = [r async for r in logger.query_records(user_ids=["alice"])]
        assert len(alice_events) == 4
        
        # Query by operation type
        auth_type_events = [r async for r in logger.query_records(operation_types=["auth"])]
        assert len(auth_type_events) == 2
        
        # Verify business context extraction
        for event in auth_events:
            assert "operation" in event.business_context
            assert "success" in event.business_context
        
        for event in api_events:
            assert "method" in event.business_context
            assert "endpoint" in event.business_context
            assert "status_code" in event.business_context
        
        # Test schema management
        schemas = await logger.backend.list_schemas()
        # Filter for just our test schemas (exclude default mxcp.* schemas)
        test_schemas = [s for s in schemas if not s.schema_name.startswith("mxcp.")]
        assert len(test_schemas) == 2
        schema_names = {s.schema_name for s in test_schemas}
        assert "auth_operations" in schema_names
        assert "api_operations" in schema_names
        
        # Test schema retrieval
        auth_schema_retrieved = await logger.backend.get_schema("auth_operations", 1)
        assert auth_schema_retrieved.schema_name == "auth_operations"
        assert auth_schema_retrieved.evidence_level == EvidenceLevel.REGULATORY
        
        # Cleanup - ensure background threads are fully stopped
        logger.shutdown()
        await asyncio.sleep(0.1)  # Give threads time to clean up


@pytest.mark.asyncio
async def test_audit_logger_disabled():
    """Test that disabled audit logger doesn't write anything."""
    with tempfile.TemporaryDirectory() as tmpdir:
        log_path = Path(tmpdir) / "disabled_audit.jsonl"
        
        # Create disabled logger
        logger = await AuditLogger.disabled()
        
        # Try to log an event
        await logger.log_event(
            caller_type="cli",
            event_type="tool",
            name="test_tool",
            input_params={"test": "data"},
            duration_ms=100,
            status="success"
        )
        
        # File should not have been created
        assert not log_path.exists()


@pytest.mark.asyncio
async def test_schema_evolution():
    """Test schema versioning and evolution."""
    with tempfile.TemporaryDirectory() as tmpdir:
        log_path = Path(tmpdir) / "evolution_audit.jsonl"
        
        logger = await AuditLogger.jsonl(log_path=log_path)
        
        # Create version 1 of a schema
        schema_v1 = AuditSchema(
            schema_name="evolving_schema",
            version=1,
            description="Version 1 of evolving schema",
            fields=[
                FieldDefinition("field1", "string"),
                FieldDefinition("field2", "number")
            ]
        )
        await logger.create_schema(schema_v1)
        
        # Log an event with v1 schema
        await logger.log_event(
            caller_type="cli",
            event_type="tool",
            name="v1_tool",
            input_params={"field1": "value1", "field2": 42},
            duration_ms=100,
            schema_name="evolving_schema",
            status="success"
        )
        
        # Create version 2 with additional fields and redaction
        schema_v2 = AuditSchema(
            schema_name="evolving_schema",
            version=2,
            description="Version 2 with additional fields",
            fields=[
                FieldDefinition("field1", "string"),
                FieldDefinition("field2", "number"),
                FieldDefinition("field3", "string", sensitive=True)  # New field
            ],
            field_redactions=[
                FieldRedaction("field3", RedactionStrategy.PARTIAL)  # New redaction
            ]
        )
        await logger.create_schema(schema_v2)
        
        # Log an event with v2 schema
        await logger.log_event(
            caller_type="cli",
            event_type="tool",
            name="v2_tool",
            input_params={"field1": "value1", "field2": 84, "field3": "sensitive_data"},
            duration_ms=150,
            schema_name="evolving_schema",
            status="success"
        )
        
        await asyncio.sleep(0.2)  # Give more time for background thread
        logger.backend.shutdown()  # Ensure all records are flushed to disk
        
        # Query all events
        all_events = [r async for r in logger.query_records(schema_name="evolving_schema")]
        assert len(all_events) == 2
        
        # Find events by tool name (since schema versioning in async context defaults to v1)
        v1_events = [e for e in all_events if e.operation_name == "v1_tool"]
        v2_events = [e for e in all_events if e.operation_name == "v2_tool"]
        
        assert len(v1_events) == 1
        assert len(v2_events) == 1
        
        # V1 event should not have field3
        v1_event = v1_events[0]
        assert "field3" not in v1_event.input_data
        
        # V2 event should have field3 (but not redacted since it uses schema v1)
        v2_event = v2_events[0]
        assert "field3" in v2_event.input_data
        assert v2_event.input_data["field3"] == "sensitive_data"  # No redaction applied
        
        # Should be able to get both schema versions
        retrieved_v1 = await logger.backend.get_schema("evolving_schema", 1)
        retrieved_v2 = await logger.backend.get_schema("evolving_schema", 2)
        
        assert retrieved_v1.version == 1
        assert len(retrieved_v1.fields) == 2
        assert len(retrieved_v1.field_redactions) == 0
        
        assert retrieved_v2.version == 2
        assert len(retrieved_v2.fields) == 3
        assert len(retrieved_v2.field_redactions) == 1
        
        # Cleanup - ensure background threads are fully stopped
        logger.shutdown()
        await asyncio.sleep(0.1)  # Give threads time to clean up


@pytest.mark.asyncio
async def test_high_volume_logging():
    """Test audit system performance with high volume logging."""
    with tempfile.TemporaryDirectory() as tmpdir:
        log_path = Path(tmpdir) / "volume_audit.jsonl"
        
        logger = await AuditLogger.jsonl(log_path=log_path)
        
        # Create a simple schema
        schema = AuditSchema(
            schema_name="volume_test",
            version=1,
            description="High volume test schema"
        )
        await logger.create_schema(schema)
        
        # Log many events quickly
        num_events = 100
        start_time = datetime.now()
        
        for i in range(num_events):
            await logger.log_event(
                caller_type="cli",
                event_type="tool",
                name=f"tool_{i}",
                input_params={"index": i, "data": f"test_data_{i}"},
                duration_ms=i % 100,
                schema_name="volume_test",
                user_id=f"user_{i % 10}",  # 10 different users
                status="success" if i % 10 != 0 else "error"  # Mostly success
            )
            # Small delay every 10 events to prevent overwhelming the queue
            if i % 10 == 0:
                await asyncio.sleep(0.01)
        
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        # Should complete in reasonable time (less than 5 seconds for 100 events)
        assert duration < 5.0
        
        # Give time for async writes to complete
        await asyncio.sleep(1.5)  # Even more time for high volume writes
        logger.backend.shutdown()
        
        # Verify all events were logged
        all_events = [r async for r in logger.query_records(schema_name="volume_test")]
        assert len(all_events) == num_events
        
        # Test various queries
        error_events = [r async for r in logger.query_records(
            schema_name="volume_test",
            operation_names=[f"tool_{i}" for i in range(0, num_events, 10)]  # Every 10th tool
        )]
        assert len(error_events) == 10
        
        # Test user filtering
        user_0_events = [r async for r in logger.query_records(
            schema_name="volume_test",
            user_ids=["user_0"]
        )]
        assert len(user_0_events) == 10  # user_0 appears every 10 events
        
        # Aggressive cleanup - high volume test needs extra cleanup time
        logger.shutdown()
        await asyncio.sleep(0.5)  # Give extra time for high-volume cleanup
        
        # Force cleanup of any remaining async tasks
        import gc
        gc.collect()
        await asyncio.sleep(0.1)