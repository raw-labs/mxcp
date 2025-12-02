"""Tests for EndpointToolExecutor integration."""

from pathlib import Path
from typing import Any

import pytest

from mxcp.sdk.auth import UserContextModel
from mxcp.sdk.executor import ExecutionContext
from mxcp.server.definitions.endpoints.models import EndpointDefinitionModel, SourceDefinitionModel
from mxcp.server.executor.runners.tool import EndpointToolExecutor, EndpointWithPath


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
        self._monkeypatch = pytest.MonkeyPatch()
        self._monkeypatch.setattr(
            "mxcp.server.executor.runners.tool.find_repo_root", lambda: Path.cwd()
        )

        self.endpoints = [
            EndpointWithPath(
                EndpointDefinitionModel.model_validate(
                    {
                        "mxcp": 1,
                        "tool": {
                            "name": "get_date",
                            "description": "Get current date",
                            "parameters": [],
                            "source": {"code": "SELECT current_date()"},
                        },
                    }
                ),
                Path("endpoints/get_date.yml"),
            ),
            EndpointWithPath(
                EndpointDefinitionModel.model_validate(
                    {
                        "mxcp": 1,
                        "tool": {
                            "name": "calculate",
                            "description": "Calculate expression",
                            "parameters": [{"name": "expr", "type": "string"}],
                            "source": {"code": "return 2 + 2", "language": "python"},
                        },
                    }
                ),
                Path("endpoints/calculate.yml"),
            ),
            EndpointWithPath(
                EndpointDefinitionModel.model_validate(
                    {
                        "mxcp": 1,
                        "tool": {
                            "name": "get_weather",
                            "description": "Get weather info",
                            "parameters": [{"name": "location", "type": "string"}],
                            "source": {"code": "weather.py", "language": "python"},
                        },
                    }
                ),
                Path("endpoints/get_weather.yml"),
            ),
            EndpointWithPath(
                EndpointDefinitionModel.model_validate(
                    {
                        "mxcp": 1,
                        "resource": {
                            "uri": "data://users",
                            "description": "User data resource",
                            "parameters": [{"name": "limit", "type": "integer"}],
                            "source": {"code": "SELECT * FROM users LIMIT $limit"},
                        },
                    }
                ),
                Path("endpoints/users.yml"),
            ),
        ]

        self.executor = EndpointToolExecutor(self.engine, self.endpoints)

    def teardown_method(self):
        self._monkeypatch.undo()

    def test_initialization(self):
        """Test EndpointToolExecutor initialization."""
        assert self.executor.engine == self.engine
        assert len(self.executor.endpoints) == len(self.endpoints)
        assert len(self.executor._tool_map) == 4
        assert "get_date" in self.executor._tool_map
        assert "data://users" in self.executor._tool_map

    @pytest.mark.asyncio
    async def test_execute_tool_with_code(self):
        """Test executing a tool with inline code."""
        user_context = UserContextModel(provider="test", user_id="test-user", username="testuser")

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
        tmp_file = Path("weather.py")
        tmp_file.write_text("weather.py")
        result = await self.executor.execute_tool("get_weather", {"location": "Paris"})

        assert result == {"temperature": 22, "condition": "sunny"}

        # Verify engine was called correctly
        assert len(self.engine.calls) == 1
        call = self.engine.calls[0]
        assert call["language"] == "python"
        assert call["source_code"] == "weather.py"
        assert call["params"] == {"location": "Paris"}
        if tmp_file.exists():
            tmp_file.unlink()

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
        endpoint = EndpointDefinitionModel.model_validate(
            {
                "mxcp": 1,
                "tool": {
                    "name": "broken_tool",
                    "description": "Tool with no source",
                    "parameters": [],
                    "source": {"code": "SELECT 1"},
                },
            }
        )
        # Force the source to be invalid to simulate missing configuration
        assert endpoint.tool is not None
        object.__setattr__(
            endpoint.tool,
            "source",
            SourceDefinitionModel.model_construct(code=None, file=None),
        )
        endpoints_no_source = [EndpointWithPath(endpoint, Path("endpoints/broken.yml"))]
        executor = EndpointToolExecutor(self.engine, endpoints_no_source)

        with pytest.raises(ValueError) as exc_info:
            await executor.execute_tool("broken_tool", {})

        assert "No source found for endpoint" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_execute_tool_loads_file_content(self, tmp_path, monkeypatch):
        """Ensure file-based sources are read and executed with their content."""
        sql_dir = tmp_path / "sql"
        sql_dir.mkdir()
        sql_file = sql_dir / "hello.sql"
        sql_file.write_text("select 1 as val;")

        # Provide mxcp-site.yml so find_repo_root() resolves to tmp_path
        (tmp_path / "mxcp-site.yml").write_text("mxcp: 1\nproject: test\nprofile: default\n")
        monkeypatch.chdir(tmp_path)

        endpoint = EndpointWithPath(
            EndpointDefinitionModel.model_validate(
                {"mxcp": 1, "tool": {"name": "hello_tool", "source": {"file": "sql/hello.sql"}}}
            ),
            Path("endpoints/hello.yml"),
        )

        engine = MockExecutionEngine({"select 1 as val;": {"val": 1}})
        executor = EndpointToolExecutor(engine, [endpoint])

        result = await executor.execute_tool("hello_tool", {})

        assert result == {"val": 1}
        assert engine.calls[0]["source_code"] == "select 1 as val;"

    @pytest.mark.asyncio
    async def test_execute_tool_loads_relative_parent_path(self, tmp_path, monkeypatch):
        """Relative paths with '..' should resolve correctly."""
        (tmp_path / "mxcp-site.yml").write_text("mxcp: 1\nproject: test\nprofile: default\n")
        sql_dir = tmp_path.parent / "shared-sql"
        sql_dir.mkdir(exist_ok=True)
        sql_file = sql_dir / "hi.sql"
        sql_file.write_text("select 2 as val;")

        # endpoint references ../shared-sql/hi.sql relative to repo root
        endpoint = EndpointWithPath(
            EndpointDefinitionModel.model_validate(
                {"mxcp": 1, "tool": {"name": "hi_tool", "source": {"file": "../shared-sql/hi.sql"}}}
            ),
            Path("endpoints/hi.yml"),
        )

        engine = MockExecutionEngine({"select 2 as val;": {"val": 2}})
        monkeypatch.chdir(tmp_path)
        executor = EndpointToolExecutor(engine, [endpoint])

        result = await executor.execute_tool("hi_tool", {})

        assert result == {"val": 2}

    @pytest.mark.asyncio
    async def test_python_file_executes_by_path(self, tmp_path, monkeypatch):
        """Python sources should be passed as file paths to the engine."""
        (tmp_path / "mxcp-site.yml").write_text("mxcp: 1\nproject: test\nprofile: default\n")
        py_dir = tmp_path / "python"
        py_dir.mkdir()
        script = py_dir / "hello.py"
        script.write_text("def python_tool():\n" "    return {'message': 'hi'}\n")

        endpoint = EndpointWithPath(
            EndpointDefinitionModel.model_validate(
                {
                    "mxcp": 1,
                    "tool": {
                        "name": "python_tool",
                        "source": {"file": "python/hello.py", "language": "python"},
                    },
                }
            ),
            Path("endpoints/python.yml"),
        )

        monkeypatch.chdir(tmp_path)
        engine = MockExecutionEngine()
        executor = EndpointToolExecutor(engine, [endpoint])

        result = await executor.execute_tool("python_tool", {})

        assert result == "Mock result for " + engine.calls[0]["source_code"]
        assert engine.calls[0]["language"] == "python"
        source_code = engine.calls[0]["source_code"]
        file_part, sep, function_name = source_code.partition(":")
        assert sep == ":"
        assert function_name == "python_tool"
        assert Path(file_part).resolve() == script.resolve()
