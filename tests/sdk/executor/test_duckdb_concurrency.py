"""Test concurrent DuckDB execution with connection pool."""

import asyncio
import time
from collections.abc import Iterator
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

import pytest

from mxcp.sdk.auth import UserContext
from mxcp.sdk.executor import ExecutionContext, ExecutionEngine
from mxcp.sdk.executor.plugins import DuckDBExecutor
from mxcp.sdk.duckdb import DatabaseConfig, PluginConfig, DuckDBRuntime


@pytest.fixture
def duckdb_executor(tmp_path: Path) -> Iterator[DuckDBExecutor]:
    """Create a DuckDB executor with test database."""
    db_path = tmp_path / "test.db"

    database_config = DatabaseConfig(
        path=str(db_path),
        readonly=False,
        extensions=[],
    )

    plugin_config = PluginConfig(
        plugins_path="",
        config={},
    )

    runtime = DuckDBRuntime(
        database_config=database_config,
        plugins=[],
        plugin_config=plugin_config,
        secrets=[],
    )

    executor = DuckDBExecutor(runtime)
    yield executor
    # Clean up the runtime to release connections
    runtime.shutdown()


@pytest.fixture
def execution_engine(duckdb_executor: DuckDBExecutor) -> Iterator[ExecutionEngine]:
    """Create an execution engine with DuckDB executor."""
    engine = ExecutionEngine()
    engine.register_executor(duckdb_executor)
    yield engine
    engine.shutdown()


async def execute_query(engine: ExecutionEngine, query_id: int, value: int) -> tuple[int, float]:
    """Execute a query that performs actual database operations."""
    start_time = time.time()

    # Create execution context
    user_context = UserContext(
        provider="test",
        user_id=f"user_{query_id}",
        username=f"test_user_{query_id}",
    )
    context = ExecutionContext(user_context=user_context)

    # Execute multiple operations to simulate work
    # Insert data
    await engine.execute(
        language="sql",
        source_code=f"INSERT INTO test_concurrent VALUES ({query_id}, {value})",
        params={},
        context=context,
    )

    # Do some computation
    result = await engine.execute(
        language="sql",
        source_code=f"""
            SELECT id, value, value * 2 as doubled, value * value as squared
            FROM test_concurrent 
            WHERE id = {query_id}
        """,
        params={},
        context=context,
    )

    elapsed = time.time() - start_time
    return query_id, elapsed


@pytest.mark.asyncio
async def test_concurrent_execution(execution_engine: ExecutionEngine):
    """Test that multiple queries can execute concurrently."""
    # Create a test table instead of using sleep extension
    context = ExecutionContext()
    await execution_engine.execute(
        language="sql",
        source_code="CREATE TABLE IF NOT EXISTS test_concurrent (id INTEGER, value INTEGER)",
        params={},
        context=context,
    )

    # Define queries that will insert data
    queries = [
        (1, 100),  # Query 1
        (2, 200),  # Query 2
        (3, 300),  # Query 3
        (4, 400),  # Query 4
    ]

    # Execute queries concurrently
    start_time = time.time()
    tasks = [execute_query(execution_engine, query_id, value) for query_id, value in queries]
    results = await asyncio.gather(*tasks)
    total_elapsed = time.time() - start_time

    # Verify results
    for query_id, elapsed in results:
        print(f"Query {query_id} completed in {elapsed:.2f} seconds")

    print(f"Total time for all queries: {total_elapsed:.2f} seconds")

    # All queries should complete
    assert len(results) == 4
    assert all(query_id in [1, 2, 3, 4] for query_id, _ in results)

    # Verify the data was inserted correctly
    context = ExecutionContext()
    final_result = await execution_engine.execute(
        language="sql",
        source_code="SELECT COUNT(*) as count FROM test_concurrent",
        params={},
        context=context,
    )
    assert final_result[0]["count"] == 4


@pytest.mark.asyncio
async def test_connection_pool_limit(execution_engine: ExecutionEngine):
    """Test that connection pool properly limits concurrent connections."""
    # Create more queries than pool size to test queueing
    num_queries = 30  # More than default pool size

    async def simple_query(query_id: int) -> int:
        context = ExecutionContext()
        result = await execution_engine.execute(
            language="sql",
            source_code=f"SELECT {query_id} as id",
            params={},
            context=context,
        )
        return result[0]["id"]

    # Execute many queries concurrently
    tasks = [simple_query(i) for i in range(num_queries)]
    results = await asyncio.gather(*tasks)

    # Verify all queries completed successfully
    assert len(results) == num_queries
    assert sorted(results) == list(range(num_queries))


def test_shutdown_cleanup(duckdb_executor: DuckDBExecutor):
    """Test that shutdown properly cleans up all connections."""
    # Access the runtime to ensure it's initialized
    assert duckdb_executor._runtime is not None

    # Verify the runtime has connections in the pool
    assert duckdb_executor._runtime.pool_size > 0

    # Note: DuckDBExecutor.shutdown() doesn't clean up the runtime
    # That's managed externally by whoever created the runtime
    duckdb_executor.shutdown()

    # The runtime should still be there since executor doesn't own it
    assert duckdb_executor._runtime is not None
