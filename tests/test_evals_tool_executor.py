"""Tests for EndpointToolExecutor integration."""

from typing import Any, Dict, Optional
from unittest.mock import AsyncMock, Mock

import pytest

from mxcp.evals._types import ResourceEndpoint, ToolEndpoint
from mxcp.evals.tool_executor import EndpointToolExecutor
from mxcp.sdk.auth import UserContext
from mxcp.sdk.executor import ExecutionContext, ExecutionEngine


class MockExecutionEngine:
    """Mock execution engine for testing."""

    def __init__(self, responses: Optional[Dict[str, Any]] = None):
        self.responses = responses or {}
        self.calls = []

    async def execute(
        self, language: str, source_code: str, params: Dict[str, Any], context: ExecutionContext
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

        self.endpoints = [
            ToolEndpoint(
                name="get_date",
                description="Get current date",
                parameters=[],
                source={"code": "SELECT current_date()"},
            ),
            ToolEndpoint(
                name="calculate",
                description="Calculate expression",
                parameters=[{"name": "expr", "type": "string"}],
                source={"code": "return 2 + 2", "language": "python"},
            ),
            ToolEndpoint(
                name="get_weather",
                description="Get weather info",
                parameters=[{"name": "location", "type": "string"}],
                source={"file": "weather.py", "language": "python"},
            ),
            ResourceEndpoint(
                uri="data://users",
                description="User data resource",
                parameters=[{"name": "limit", "type": "integer"}],
                source={"code": "SELECT * FROM users LIMIT $limit"},
            ),
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
        endpoints_no_source = [
            ToolEndpoint(
                name="broken_tool",
                description="Tool with no source",
                parameters=[],
                source={},  # Empty source
            )
        ]

        executor = EndpointToolExecutor(self.engine, endpoints_no_source)

        with pytest.raises(ValueError) as exc_info:
            await executor.execute_tool("broken_tool", {})

        assert "No source found for endpoint" in str(exc_info.value)

    def test_get_language_inference(self):
        """Test language inference from file extensions."""
        # Test Python file
        endpoint = ToolEndpoint(name="test", source={"file": "script.py"})
        language = self.executor._get_language(endpoint, "script.py")
        assert language == "python"

        # Test SQL file
        endpoint = ToolEndpoint(name="test", source={"file": "query.sql"})
        language = self.executor._get_language(endpoint, "query.sql")
        assert language == "sql"

        # Test explicit language override
        endpoint = ToolEndpoint(name="test", source={"file": "script.py", "language": "sql"})
        language = self.executor._get_language(endpoint, "script.py")
        assert language == "sql"

        # Test default to SQL
        endpoint = ToolEndpoint(name="test", source={"code": "some code"})
        language = self.executor._get_language(endpoint, "some code")
        assert language == "sql"
