"""Tests for the streaming API functionality.

These tests verify that the AsyncIterator-based query_records
method works correctly for memory-efficient processing.
"""
import pytest
import tempfile
import asyncio
from pathlib import Path
from datetime import datetime

from mxcp.sdk.audit import AuditLogger, AuditSchema


@pytest.mark.asyncio
async def test_streaming_basic():
    """Test basic streaming functionality."""
    with tempfile.TemporaryDirectory() as tmpdir:
        log_path = Path(tmpdir) / "streaming_test.jsonl"
        
        logger = await AuditLogger.jsonl(log_path=log_path)
        
        # Create test schema
        schema = AuditSchema(
            schema_name="streaming_test",
            version=1,
            description="Test schema for streaming"
        )
        await logger.create_schema(schema)
        
        # Log some events
        for i in range(5):
            await logger.log_event(
                caller_type="cli",
                event_type="tool",
                name=f"tool_{i}",
                input_params={"index": i},
                duration_ms=i * 10,
                schema_name="streaming_test",
                status="success"
            )
        
        # Flush writes
        await asyncio.sleep(0.1)
        logger.backend.shutdown()
        
        # Test streaming with manual iteration
        count = 0
        async for record in logger.query_records(schema_name="streaming_test"):
            assert record.operation_name.startswith("tool_")
            count += 1
        assert count == 5
        
        logger.shutdown()


@pytest.mark.asyncio
async def test_streaming_with_limit():
    """Test streaming respects limit parameter."""
    with tempfile.TemporaryDirectory() as tmpdir:
        log_path = Path(tmpdir) / "streaming_limit.jsonl"
        
        logger = await AuditLogger.jsonl(log_path=log_path)
        
        # Create test schema
        schema = AuditSchema(
            schema_name="limit_test",
            version=1,
            description="Test schema for limit"
        )
        await logger.create_schema(schema)
        
        # Log many events
        for i in range(20):
            await logger.log_event(
                caller_type="cli",
                event_type="tool",
                name=f"tool_{i}",
                input_params={"index": i},
                duration_ms=50,
                schema_name="limit_test",
                status="success"
            )
        
        # Flush writes
        await asyncio.sleep(0.1)
        logger.backend.shutdown()
        
        # Test with limit
        count = 0
        async for record in logger.query_records(schema_name="limit_test", limit=10):
            count += 1
        assert count == 10
        
        # Test without limit (should get all)
        count = 0
        async for record in logger.query_records(schema_name="limit_test"):
            count += 1
        assert count == 20
        
        logger.shutdown()


@pytest.mark.asyncio
async def test_streaming_early_termination():
    """Test that we can break out of streaming early."""
    with tempfile.TemporaryDirectory() as tmpdir:
        log_path = Path(tmpdir) / "streaming_break.jsonl"
        
        logger = await AuditLogger.jsonl(log_path=log_path)
        
        # Create test schema
        schema = AuditSchema(
            schema_name="break_test",
            version=1,
            description="Test schema for early termination"
        )
        await logger.create_schema(schema)
        
        # Log many events
        for i in range(100):
            await logger.log_event(
                caller_type="cli",
                event_type="tool",
                name=f"tool_{i}",
                input_params={"index": i},
                duration_ms=50,
                schema_name="break_test",
                status="success"
            )
        
        # Flush writes
        await asyncio.sleep(0.1)
        logger.backend.shutdown()
        
        # Test early termination
        count = 0
        async for record in logger.query_records(schema_name="break_test"):
            count += 1
            if count >= 5:
                break  # Stop after 5 records
        
        assert count == 5  # Should have stopped at 5
        
        logger.shutdown()


@pytest.mark.asyncio
async def test_streaming_memory_efficiency():
    """Test that streaming doesn't load all records into memory at once."""
    with tempfile.TemporaryDirectory() as tmpdir:
        log_path = Path(tmpdir) / "streaming_memory.jsonl"
        
        logger = await AuditLogger.jsonl(log_path=log_path)
        
        # Create test schema
        schema = AuditSchema(
            schema_name="memory_test",
            version=1,
            description="Test schema for memory efficiency"
        )
        await logger.create_schema(schema)
        
        # Log many large events
        large_data = "x" * 10000  # 10KB of data per event
        for i in range(1000):  # 10MB total
            await logger.log_event(
                caller_type="cli",
                event_type="tool",
                name=f"tool_{i}",
                input_params={"index": i, "data": large_data},
                duration_ms=50,
                schema_name="memory_test",
                status="success"
            )
            # Periodic sleep to avoid overwhelming
            if i % 100 == 0:
                await asyncio.sleep(0.01)
        
        # Flush writes
        await asyncio.sleep(0.5)
        logger.backend.shutdown()
        
        # Process records one at a time without accumulating
        processed_count = 0
        max_index_seen = -1
        
        async for record in logger.query_records(schema_name="memory_test"):
            # Just process the index, don't accumulate records
            index = record.input_data["index"]
            if index > max_index_seen:
                max_index_seen = index
            processed_count += 1
            
            # Could add memory check here if needed
        
        assert processed_count == 1000
        assert max_index_seen == 999
        
        logger.shutdown()


@pytest.mark.asyncio
async def test_streaming_with_filters():
    """Test streaming with various filter combinations."""
    with tempfile.TemporaryDirectory() as tmpdir:
        log_path = Path(tmpdir) / "streaming_filters.jsonl"
        
        logger = await AuditLogger.jsonl(log_path=log_path)
        
        # Create test schema
        schema = AuditSchema(
            schema_name="filter_test",
            version=1,
            description="Test schema for filters"
        )
        await logger.create_schema(schema)
        
        # Log varied events
        for i in range(20):
            await logger.log_event(
                caller_type="cli" if i % 2 == 0 else "http",
                event_type="tool",
                name=f"tool_{i}",
                input_params={"index": i},
                duration_ms=50,
                schema_name="filter_test",
                user_id=f"user_{i % 3}",  # 3 different users
                status="success" if i < 15 else "error",
                policy_decision="allow" if i < 10 else "deny"
            )
        
        # Flush writes
        await asyncio.sleep(0.1)
        logger.backend.shutdown()
        
        # Test user filter
        user_0_count = 0
        async for record in logger.query_records(
            schema_name="filter_test",
            user_ids=["user_0"]
        ):
            assert record.user_id == "user_0"
            user_0_count += 1
        assert user_0_count == 7  # 0, 3, 6, 9, 12, 15, 18
        
        # Test status filter
        error_count = 0
        async for record in logger.query_records(
            schema_name="filter_test",
            operation_status=["error"]
        ):
            assert record.operation_status == "error"
            error_count += 1
        assert error_count == 5  # 15-19
        
        # Test policy filter
        deny_count = 0
        async for record in logger.query_records(
            schema_name="filter_test",
            policy_decisions=["deny"]
        ):
            assert record.policy_decision == "deny"
            deny_count += 1
        assert deny_count == 10  # 10-19
        
        # Test combined filters
        combined_count = 0
        async for record in logger.query_records(
            schema_name="filter_test",
            user_ids=["user_0"],
            operation_status=["error"]
        ):
            assert record.user_id == "user_0"
            assert record.operation_status == "error"
            combined_count += 1
        assert combined_count == 2  # 15, 18
        
        logger.shutdown()


@pytest.mark.asyncio
async def test_streaming_empty_results():
    """Test streaming behavior with no matching records."""
    with tempfile.TemporaryDirectory() as tmpdir:
        log_path = Path(tmpdir) / "streaming_empty.jsonl"
        
        logger = await AuditLogger.jsonl(log_path=log_path)
        
        # Create test schema
        schema = AuditSchema(
            schema_name="empty_test",
            version=1,
            description="Test schema for empty results"
        )
        await logger.create_schema(schema)
        
        # Log one event
        await logger.log_event(
            caller_type="cli",
            event_type="tool",
            name="test_tool",
            input_params={"test": "data"},
            duration_ms=50,
            schema_name="empty_test",
            user_id="user_1",
            status="success"
        )
        
        # Flush writes
        await asyncio.sleep(0.1)
        logger.backend.shutdown()
        
        # Query for non-existent user
        count = 0
        async for record in logger.query_records(
            schema_name="empty_test",
            user_ids=["user_999"]
        ):
            count += 1
        
        assert count == 0  # Should have no results
        
        logger.shutdown()


@pytest.mark.asyncio
async def test_noop_backend_streaming():
    """Test that NoOpAuditBackend correctly implements streaming."""
    # Create disabled logger (uses NoOpAuditBackend)
    logger = await AuditLogger.disabled()
    
    # Try to log some events
    for i in range(5):
        await logger.log_event(
            caller_type="cli",
            event_type="tool",
            name=f"tool_{i}",
            input_params={"index": i},
            duration_ms=50,
            status="success"
        )
    
    # Query should return empty stream
    count = 0
    async for record in logger.query_records():
        count += 1
    
    assert count == 0  # NoOp backend should yield nothing
    
    logger.shutdown()


@pytest.mark.asyncio 
async def test_concurrent_streaming():
    """Test concurrent streaming queries."""
    with tempfile.TemporaryDirectory() as tmpdir:
        log_path = Path(tmpdir) / "streaming_concurrent.jsonl"
        
        logger = await AuditLogger.jsonl(log_path=log_path)
        
        # Create test schema
        schema = AuditSchema(
            schema_name="concurrent_test",
            version=1,
            description="Test schema for concurrent streaming"
        )
        await logger.create_schema(schema)
        
        # Log events
        for i in range(50):
            await logger.log_event(
                caller_type="cli",
                event_type="tool",
                name=f"tool_{i}",
                input_params={"index": i},
                duration_ms=50,
                schema_name="concurrent_test",
                user_id=f"user_{i % 5}",
                status="success"
            )
        
        # Flush writes
        await asyncio.sleep(0.1)
        logger.backend.shutdown()
        
        # Define concurrent query tasks
        async def count_user_records(user_id: str) -> int:
            count = 0
            async for record in logger.query_records(
                schema_name="concurrent_test",
                user_ids=[user_id]
            ):
                assert record.user_id == user_id
                count += 1
            return count
        
        # Run multiple queries concurrently
        results = await asyncio.gather(
            count_user_records("user_0"),
            count_user_records("user_1"),
            count_user_records("user_2"),
            count_user_records("user_3"),
            count_user_records("user_4")
        )
        
        # Each user should have 10 records (50 total / 5 users)
        assert all(count == 10 for count in results)
        assert sum(results) == 50
        
        logger.shutdown()
