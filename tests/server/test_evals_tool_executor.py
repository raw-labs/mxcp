"""Tests for EndpointToolExecutor integration."""

from typing import Any

import pytest

from mxcp.sdk.auth import UserContext
from mxcp.sdk.executor import ExecutionContext
from mxcp.server.definitions.endpoints._types import EndpointDefinition
from mxcp.server.executor.runners.tool import EndpointToolExecutor


class MockExecutionEngine:
    """Mock execution engine for testing."""

    def __init__(self, responses: dict[str, Any] | None = None):
        self.responses = responses or {}
        self.calls = []

    async def execute(
        self, language: str, source_code: str, params: dict[str, Any], context: ExecutionContext
    ) -> Any:
        """Mock execution that records calls and returns predefined responses."""
        self.calls.append(
            {"language": language, "source_code": source_code, "params": params, "context": context}
        )

        # Return based on source code or use default
        if source_code in self.responses:
            result = self.responses[source_code]
            if isinstance(result, Exception):
                raise result
            return result

        return f"Mock result for {source_code}"


class TestEndpointToolExecutor:
    """Test cases for EndpointToolExecutor."""

    def setup_method(self):
        """Set up test fixtures."""
        self.engine = MockExecutionEngine(
            {
                "SELECT current_date()": [{"date": "2024-01-15"}],
                "return 2 + 2": 4,
                "weather.py": {"temperature": 22, "condition": "sunny"},
            }
        )

        self.endpoints: list[EndpointDefinition] = [
            {
                "mxcp": "1",
                "tool": {
                    "name": "get_date",
                    "description": "Get current date",
                    "parameters": [],
                    "source": {"code": "SELECT current_date()"},
                },
                "resource": None,
                "prompt": None,
                "metadata": None,
            },
            {
                "mxcp": "1",
                "tool": {
                    "name": "calculate",
                    "description": "Calculate expression",
                    "parameters": [{"name": "expr", "type": "string"}],
                    "source": {"code": "return 2 + 2", "language": "python"},
                },
                "resource": None,
                "prompt": None,
                "metadata": None,
            },
            {
                "mxcp": "1",
                "tool": {
                    "name": "get_weather",
                    "description": "Get weather info",
                    "parameters": [{"name": "location", "type": "string"}],
                    "source": {"file": "weather.py", "language": "python"},
                },
                "resource": None,
                "prompt": None,
                "metadata": None,
            },
            {
                "mxcp": "1",
                "tool": None,
                "resource": {
                    "uri": "data://users",
                    "description": "User data resource",
                    "parameters": [{"name": "limit", "type": "integer"}],
                    "source": {"code": "SELECT * FROM users LIMIT $limit"},
                },
                "prompt": None,
                "metadata": None,
            },
        ]

        self.executor = EndpointToolExecutor(self.engine, self.endpoints)

    def test_initialization(self):
        """Test EndpointToolExecutor initialization."""
        assert self.executor.engine == self.engine
        assert self.executor.endpoints == self.endpoints
        assert len(self.executor._tool_map) == 4
        assert "get_date" in self.executor._tool_map
        assert "data://users" in self.executor._tool_map

    @pytest.mark.asyncio
    async def test_execute_tool_with_code(self):
        """Test executing a tool with inline code."""
        user_context = UserContext(provider="test", user_id="test-user", username="testuser")

        result = await self.executor.execute_tool("get_date", {}, user_context=user_context)

        assert result == [{"date": "2024-01-15"}]

        # Verify engine was called correctly
        assert len(self.engine.calls) == 1
        call = self.engine.calls[0]
        assert call["language"] == "sql"  # Default language
        assert call["source_code"] == "SELECT current_date()"
        assert call["params"] == {}
        assert call["context"].user_context == user_context

    @pytest.mark.asyncio
    async def test_execute_tool_with_language(self):
        """Test executing a tool with explicit language."""
        result = await self.executor.execute_tool("calculate", {"expr": "2+2"})

        assert result == 4

        # Verify engine was called with correct language
        assert len(self.engine.calls) == 1
        call = self.engine.calls[0]
        assert call["language"] == "python"
        assert call["source_code"] == "return 2 + 2"
        assert call["params"] == {"expr": "2+2"}

    @pytest.mark.asyncio
    async def test_execute_tool_with_file(self):
        """Test executing a tool with file reference."""
        result = await self.executor.execute_tool("get_weather", {"location": "Paris"})

        assert result == {"temperature": 22, "condition": "sunny"}

        # Verify engine was called correctly
        assert len(self.engine.calls) == 1
        call = self.engine.calls[0]
        assert call["language"] == "python"
        assert call["source_code"] == "weather.py"
        assert call["params"] == {"location": "Paris"}

    @pytest.mark.asyncio
    async def test_execute_resource(self):
        """Test executing a resource endpoint."""
        result = await self.executor.execute_tool("data://users", {"limit": 10})

        assert result == "Mock result for SELECT * FROM users LIMIT $limit"

        # Verify engine was called correctly
        assert len(self.engine.calls) == 1
        call = self.engine.calls[0]
        assert call["language"] == "sql"  # Default for no explicit language
        assert call["source_code"] == "SELECT * FROM users LIMIT $limit"
        assert call["params"] == {"limit": 10}

    @pytest.mark.asyncio
    async def test_execute_tool_not_found(self):
        """Test error when tool is not found."""
        with pytest.raises(ValueError) as exc_info:
            await self.executor.execute_tool("nonexistent", {})

        assert "Tool 'nonexistent' not found" in str(exc_info.value)
        assert "Available tools:" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_execute_tool_execution_error(self):
        """Test error propagation from execution engine."""
        # Configure engine to raise an error
        self.engine.responses["SELECT current_date()"] = RuntimeError("Database error")

        with pytest.raises(RuntimeError) as exc_info:
            await self.executor.execute_tool("get_date", {})

        assert "Database error" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_execute_tool_no_source(self):
        """Test error when endpoint has no source."""
        endpoints_no_source: list[EndpointDefinition] = [
            {
                "mxcp": "1",
                "tool": {
                    "name": "broken_tool",
                    "description": "Tool with no source",
                    "parameters": [],
                    "source": {},  # Empty source
                },
                "resource": None,
                "prompt": None,
                "metadata": None,
            }
        ]

        executor = EndpointToolExecutor(self.engine, endpoints_no_source)

        with pytest.raises(ValueError) as exc_info:
            await executor.execute_tool("broken_tool", {})

        assert "No source found for endpoint" in str(exc_info.value)

    def test_get_language_inference(self):
        """Test language inference via endpoint execution."""
        # Create endpoints with different language sources
        test_endpoints: list[EndpointDefinition] = [
            {
                "mxcp": "1",
                "tool": {
                    "name": "python_file_tool",
                    "source": {"file": "script.py"},
                },
                "resource": None,
                "prompt": None,
                "metadata": None,
            },
            {
                "mxcp": "1",
                "tool": {
                    "name": "sql_file_tool",
                    "source": {"file": "query.sql"},
                },
                "resource": None,
                "prompt": None,
                "metadata": None,
            },
            {
                "mxcp": "1",
                "tool": {
                    "name": "explicit_override_tool",
                    "source": {"file": "script.py", "language": "sql"},
                },
                "resource": None,
                "prompt": None,
                "metadata": None,
            },
            {
                "mxcp": "1",
                "tool": {
                    "name": "default_sql_tool",
                    "source": {"code": "some code"},
                },
                "resource": None,
                "prompt": None,
                "metadata": None,
            },
        ]

        test_executor = EndpointToolExecutor(self.engine, test_endpoints)

        # Verify the tools were properly registered
        assert "python_file_tool" in test_executor._tool_map
        assert "sql_file_tool" in test_executor._tool_map
        assert "explicit_override_tool" in test_executor._tool_map
        assert "default_sql_tool" in test_executor._tool_map
