"""Tests for DuckDB executor plugin.

These tests focus on the core DuckDB execution functionality of the executor
plugin, including SQL execution, session management, plugin loading,
and error conditions.
"""

import asyncio
import tempfile
from pathlib import Path

import pytest

from mxcp.sdk.auth import UserContext
from mxcp.sdk.executor import ExecutionContext
from mxcp.sdk.executor.plugins import DuckDBExecutor
from mxcp.sdk.duckdb import (
    DatabaseConfig,
    ExtensionDefinition,
    PluginConfig,
)


@pytest.fixture
def temp_repo_dir():
    """Create a temporary repository directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_dir = Path(tmpdir)
        yield repo_dir


@pytest.fixture
def mock_user_config():
    """Create a mock user config."""
    return {
        "mxcp": 1,
        "projects": {
            "test-project": {"profiles": {"test": {"secrets": [], "plugin": {"config": {}}}}}
        },
    }


@pytest.fixture
def mock_database_config(tmp_path):
    """Create a mock database configuration."""
    db_path = tmp_path / "test.duckdb"
    return DatabaseConfig(path=str(db_path), readonly=False, extensions=[])


@pytest.fixture
def mock_plugin_config():
    """Create a mock plugin configuration."""
    return PluginConfig(plugins_path="plugins", config={})


@pytest.fixture
def mock_context():
    """Create a mock execution context for user authentication."""
    user_context = UserContext(
        user_id="test_user_123",
        username="test_user",
        provider="test",
        external_token="test_token_123",
        email="test@example.com",
    )
    return ExecutionContext(user_context=user_context)


@pytest.fixture
def duckdb_executor(mock_database_config, mock_plugin_config):
    """Create a DuckDB executor with test configuration."""
    from mxcp.sdk.duckdb import DuckDBRuntime

    runtime = DuckDBRuntime(
        database_config=mock_database_config,
        plugins=[],
        plugin_config=mock_plugin_config,
        secrets=[],
    )
    return DuckDBExecutor(runtime)


class TestDuckDBExecutorBasics:
    """Test basic DuckDB executor functionality."""

    def test_executor_initialization(self, duckdb_executor):
        """Test executor initialization."""
        assert duckdb_executor.language == "sql"
        assert duckdb_executor._runtime is not None
        assert duckdb_executor._runtime.pool_size > 0

    def test_executor_initialization_with_options(self, tmp_path):
        """Test executor initialization with various options."""
        from mxcp.sdk.duckdb import DuckDBRuntime

        # Test with different configuration
        db_path = tmp_path / "test_options.duckdb"
        database_config = DatabaseConfig(
            path=str(db_path), readonly=False, extensions=[ExtensionDefinition(name="json")]
        )
        plugin_config = PluginConfig(plugins_path="plugins", config={})

        runtime = DuckDBRuntime(
            database_config=database_config, plugins=[], plugin_config=plugin_config, secrets=[]
        )
        executor = DuckDBExecutor(runtime)

        assert executor.language == "sql"
        assert executor._runtime is not None

    def test_new_instance_pattern(self, mock_context, tmp_path):
        """Test creating new instances for config changes."""
        from mxcp.sdk.duckdb import DuckDBRuntime

        # Create initial executor
        db_path1 = tmp_path / "test1.duckdb"
        initial_config = DatabaseConfig(path=str(db_path1), readonly=False, extensions=[])
        plugin_config = PluginConfig(plugins_path="plugins", config={})
        runtime1 = DuckDBRuntime(initial_config, [], plugin_config, [])
        executor1 = DuckDBExecutor(runtime1)

        # Create new executor with different configuration (different extensions)
        db_path2 = tmp_path / "test2.duckdb"
        new_config = DatabaseConfig(
            path=str(db_path2), readonly=False, extensions=[ExtensionDefinition(name="json")]
        )
        runtime2 = DuckDBRuntime(new_config, [], plugin_config, [])
        executor2 = DuckDBExecutor(runtime2)

        # Executors should be different instances with their own runtimes
        assert executor1._runtime is not executor2._runtime

        # Clean up
        executor1.shutdown()
        executor2.shutdown()
        runtime1.shutdown()
        runtime2.shutdown()

    def test_validate_sql_source(self, duckdb_executor, mock_context):
        """Test SQL source validation."""
        # Valid SQL returns True
        result = duckdb_executor.validate_source("SELECT 1")
        assert result.is_valid
        # Invalid SQL returns False
        result = duckdb_executor.validate_source("INVALID SQL SYNTAX")
        assert not result.is_valid

        # Empty string should return False
        result = duckdb_executor.validate_source("")
        assert not result.is_valid
        result = duckdb_executor.validate_source("   ")  # Whitespace only
        assert not result.is_valid

        # None should return False
        result = duckdb_executor.validate_source(None)
        assert not result.is_valid


class TestDuckDBSQLExecution:
    """Test DuckDB SQL execution functionality."""

    @pytest.mark.asyncio
    async def test_execute_simple_query(self, duckdb_executor, mock_context):
        """Test executing a simple SQL query."""
        result = await duckdb_executor.execute("SELECT 1 as num, 'test' as str", {}, mock_context)

        assert len(result) == 1
        assert result[0]["num"] == 1
        assert result[0]["str"] == "test"

    @pytest.mark.asyncio
    async def test_execute_parameterized_query(self, duckdb_executor, mock_context):
        """Test executing parameterized queries."""
        result = await duckdb_executor.execute(
            "SELECT $num as number, $text as message", {"num": 42, "text": "hello"}, mock_context
        )

        assert len(result) == 1
        assert result[0]["number"] == 42
        assert result[0]["message"] == "hello"

    @pytest.mark.asyncio
    async def test_execute_with_different_parameter_types(self, duckdb_executor, mock_context):
        """Test executing queries with various parameter types."""
        # Create test table with various types
        await duckdb_executor.execute(
            """
            CREATE TABLE test_types (
                str_col VARCHAR,
                int_col INTEGER,
                float_col DOUBLE,
                bool_col BOOLEAN,
                date_col DATE
            )
        """,
            {},
            mock_context,
        )

        # Insert with parameters
        result = await duckdb_executor.execute(
            """
            INSERT INTO test_types VALUES ($str_val, $int_val, $float_val, $bool_val, $date_val)
            RETURNING *
        """,
            {
                "str_val": "test",
                "int_val": 42,
                "float_val": 3.14,
                "bool_val": True,
                "date_val": "2024-01-15",
            },
            mock_context,
        )

        assert len(result) == 1
        assert result[0]["str_col"] == "test"
        assert result[0]["int_col"] == 42
        assert abs(result[0]["float_col"] - 3.14) < 0.001
        assert result[0]["bool_col"] is True

    @pytest.mark.asyncio
    async def test_execute_ddl_statements(self, duckdb_executor, mock_context):
        """Test executing DDL statements."""
        # CREATE TABLE
        result = await duckdb_executor.execute(
            """
            CREATE TABLE products (
                id INTEGER PRIMARY KEY,
                name VARCHAR NOT NULL,
                price DECIMAL(10,2)
            )
        """,
            {},
            mock_context,
        )

        # Should return empty result for DDL
        assert result == []

        # INSERT data
        await duckdb_executor.execute(
            """
            INSERT INTO products VALUES (1, 'Product A', 29.99)
        """,
            {},
            mock_context,
        )

        # Query data
        result = await duckdb_executor.execute("SELECT * FROM products", {}, mock_context)
        assert len(result) == 1
        assert result[0]["id"] == 1
        assert result[0]["name"] == "Product A"
        assert abs(result[0]["price"] - 29.99) < 0.001

    @pytest.mark.asyncio
    async def test_execute_with_complex_data_types(self, duckdb_executor, mock_context):
        """Test executing queries with complex data types."""
        # Test with JSON
        result = await duckdb_executor.execute(
            """
            SELECT
                $json_data::JSON as json_col,
                $array_data as array_col,
                $struct_data as struct_col
        """,
            {
                "json_data": '{"key": "value", "number": 42}',
                "array_data": [1, 2, 3],
                "struct_data": {"nested": {"value": "test"}},
            },
            mock_context,
        )

        assert len(result) == 1
        assert result[0]["json_col"] is not None
        import numpy as np

        # DuckDB may return numpy arrays, so convert to list for comparison
        array_result = result[0]["array_col"]
        if isinstance(array_result, np.ndarray):
            array_result = array_result.tolist()
        assert array_result == [1, 2, 3]
        assert result[0]["struct_col"] == {"nested": {"value": "test"}}


class TestDuckDBErrorHandling:
    """Test DuckDB error handling scenarios."""

    @pytest.mark.asyncio
    async def test_sql_syntax_error(self, duckdb_executor, mock_context):
        """Test handling of SQL syntax errors."""
        with pytest.raises(Exception) as exc_info:
            await duckdb_executor.execute("SELECT * FROM", {}, mock_context)

        # Should contain information about the syntax error
        assert "syntax" in str(exc_info.value).lower() or "parse" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_table_not_found_error(self, duckdb_executor, mock_context):
        """Test handling of table not found errors."""
        with pytest.raises(Exception) as exc_info:
            await duckdb_executor.execute("SELECT * FROM nonexistent_table", {}, mock_context)

        # Should contain information about the missing table
        assert (
            "nonexistent_table" in str(exc_info.value) or "not found" in str(exc_info.value).lower()
        )

    @pytest.mark.asyncio
    async def test_parameter_missing_error(self, duckdb_executor, mock_context):
        """Test handling of missing parameter errors."""
        with pytest.raises(Exception):
            await duckdb_executor.execute(
                "SELECT * FROM table WHERE id = $missing_param", {}, mock_context
            )

    @pytest.mark.asyncio
    async def test_constraint_violation_error(self, duckdb_executor, mock_context):
        """Test handling of constraint violation errors."""
        # Create table with constraint
        await duckdb_executor.execute(
            """
            CREATE TABLE unique_test (
                id INTEGER PRIMARY KEY,
                name VARCHAR UNIQUE
            )
        """,
            {},
            mock_context,
        )

        # Insert first record
        await duckdb_executor.execute(
            "INSERT INTO unique_test VALUES (1, 'test')", {}, mock_context
        )

        # Try to insert duplicate - should raise constraint violation
        with pytest.raises(Exception) as exc_info:
            await duckdb_executor.execute(
                "INSERT INTO unique_test VALUES (2, 'test')", {}, mock_context
            )

        # Should contain information about the constraint violation
        assert (
            "constraint" in str(exc_info.value).lower() or "unique" in str(exc_info.value).lower()
        )

    @pytest.mark.asyncio
    async def test_type_mismatch_error(self, duckdb_executor, mock_context):
        """Test handling of type mismatch errors."""
        await duckdb_executor.execute(
            """
            CREATE TABLE type_test (
                id INTEGER,
                value INTEGER
            )
        """,
            {},
            mock_context,
        )

        # Try to insert string into integer column - should raise type error
        with pytest.raises(Exception) as exc_info:
            await duckdb_executor.execute(
                "INSERT INTO type_test VALUES (1, 'not_a_number')", {}, mock_context
            )

        # Should contain information about the type mismatch
        assert (
            "type" in str(exc_info.value).lower()
            or "cast" in str(exc_info.value).lower()
            or "conversion" in str(exc_info.value).lower()
        )


class TestDuckDBQueryResults:
    """Test DuckDB query result handling."""

    @pytest.mark.asyncio
    async def test_empty_result_set(self, duckdb_executor, mock_context):
        """Test handling of empty result sets."""
        # Create empty table
        await duckdb_executor.execute(
            """
            CREATE TABLE empty_table (id INTEGER, name VARCHAR)
        """,
            {},
            mock_context,
        )

        # Query empty table
        result = await duckdb_executor.execute("SELECT * FROM empty_table", {}, mock_context)
        assert result == []

    @pytest.mark.asyncio
    async def test_single_row_result(self, duckdb_executor, mock_context):
        """Test handling of single row results."""
        result = await duckdb_executor.execute(
            """
            SELECT
                'single' as type,
                1 as count,
                true as flag
        """,
            {},
            mock_context,
        )

        assert len(result) == 1
        assert result[0]["type"] == "single"
        assert result[0]["count"] == 1
        assert result[0]["flag"] is True

    @pytest.mark.asyncio
    async def test_multiple_row_result(self, duckdb_executor, mock_context):
        """Test handling of multiple row results."""
        result = await duckdb_executor.execute(
            """
            SELECT
                generate_series as id,
                'item_' || generate_series as name
            FROM generate_series(1, 5)
            ORDER BY id
        """,
            {},
            mock_context,
        )

        assert len(result) == 5
        for i, row in enumerate(result):
            assert row["id"] == i + 1
            assert row["name"] == f"item_{i + 1}"

    @pytest.mark.asyncio
    async def test_null_value_handling(self, duckdb_executor, mock_context):
        """Test handling of NULL values in results."""
        result = await duckdb_executor.execute(
            """
            SELECT
                'test' as not_null,
                NULL as null_value,
                CASE WHEN 1=2 THEN 'never' ELSE NULL END as conditional_null
        """,
            {},
            mock_context,
        )

        assert len(result) == 1
        assert result[0]["not_null"] == "test"
        assert result[0]["null_value"] is None
        assert result[0]["conditional_null"] is None

    @pytest.mark.asyncio
    async def test_numeric_precision_handling(self, duckdb_executor, mock_context):
        """Test handling of numeric precision in results."""
        result = await duckdb_executor.execute(
            """
            SELECT
                1 as integer,
                1.5 as float,
                1.123456789 as precise_float,
                CAST(1.99 AS DECIMAL(10,2)) as decimal_val
        """,
            {},
            mock_context,
        )

        assert len(result) == 1
        assert result[0]["integer"] == 1
        assert result[0]["float"] == 1.5
        assert abs(result[0]["precise_float"] - 1.123456789) < 0.000000001
        assert abs(result[0]["decimal_val"] - 1.99) < 0.001


class TestDuckDBRuntime:
    """Test DuckDB runtime functionality."""

    def test_runtime_isolation(self, mock_context, tmp_path):
        """Test that different executors have isolated runtimes."""
        from mxcp.sdk.duckdb import DuckDBRuntime

        db_path1 = tmp_path / "test_iso1.duckdb"
        db_path2 = tmp_path / "test_iso2.duckdb"
        database_config1 = DatabaseConfig(path=str(db_path1), readonly=False, extensions=[])
        database_config2 = DatabaseConfig(path=str(db_path2), readonly=False, extensions=[])
        plugin_config = PluginConfig(plugins_path="plugins", config={})

        runtime1 = DuckDBRuntime(
            database_config=database_config1, plugins=[], plugin_config=plugin_config, secrets=[]
        )
        runtime2 = DuckDBRuntime(
            database_config=database_config2, plugins=[], plugin_config=plugin_config, secrets=[]
        )
        executor1 = DuckDBExecutor(runtime1)
        executor2 = DuckDBExecutor(runtime2)

        # Runtimes should be different objects
        assert executor1._runtime is not executor2._runtime

        executor1.shutdown()
        executor2.shutdown()
        runtime1.shutdown()
        runtime2.shutdown()

    def test_memory_database_persistence(self, duckdb_executor, mock_context):
        """Test that in-memory database persists data across queries."""
        # Create table
        asyncio.run(
            duckdb_executor.execute("CREATE TABLE persist_test (id INTEGER)", {}, mock_context)
        )

        # Insert data
        asyncio.run(
            duckdb_executor.execute("INSERT INTO persist_test VALUES (1), (2)", {}, mock_context)
        )

        # Should be able to query the table created earlier
        result = asyncio.run(
            duckdb_executor.execute("SELECT * FROM persist_test ORDER BY id", {}, mock_context)
        )
        assert len(result) == 2
        assert result[0]["id"] == 1
        assert result[1]["id"] == 2

    def test_memory_database_default(self, duckdb_executor, mock_context):
        """Test that memory database is properly configured."""
        # Should be able to create and use tables
        asyncio.run(
            duckdb_executor.execute(
                """
            CREATE TABLE memory_test (
                id INTEGER PRIMARY KEY,
                data VARCHAR
            )
        """,
                {},
                mock_context,
            )
        )

        # Insert data
        asyncio.run(
            duckdb_executor.execute(
                """
            INSERT INTO memory_test VALUES (1, 'test_data')
        """,
                {},
                mock_context,
            )
        )

        # Query data
        result = asyncio.run(duckdb_executor.execute("SELECT * FROM memory_test", {}, mock_context))
        assert len(result) == 1
        assert result[0]["id"] == 1
        assert result[0]["data"] == "test_data"


class TestDuckDBExtensionsAndPlugins:
    """Test DuckDB extensions and plugins functionality."""

    def test_json_extension_available(self, duckdb_executor, mock_context):
        """Test that JSON extension functionality is available."""
        # Test JSON functionality
        result = asyncio.run(
            duckdb_executor.execute(
                """
            SELECT '{"key": "value"}'::JSON as json_data
        """,
                {},
                mock_context,
            )
        )

        assert len(result) == 1
        assert result[0]["json_data"] is not None

    def test_available_plugins_logged(self, duckdb_executor, mock_context):
        """Test that available plugins are logged during startup."""
        # Should not raise error during plugin logging

        # Verify runtime was created successfully
        assert duckdb_executor._runtime is not None
        assert duckdb_executor._runtime.pool_size > 0
