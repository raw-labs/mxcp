"""Tests for Python endpoint functionality."""
import pytest
import os
import tempfile
from pathlib import Path
import shutil
from mxcp.config.user_config import load_user_config
from mxcp.config.site_config import load_site_config
from mxcp.engine.duckdb_session import DuckDBSession
from mxcp.endpoints.executor import EndpointExecutor, EndpointType
from mxcp.endpoints.loader import EndpointLoader
from mxcp.engine.python_loader import PythonEndpointLoader
from mxcp.runtime import _set_runtime_context, _clear_runtime_context, db, config, _init_hooks, _shutdown_hooks
import asyncio
import yaml


@pytest.fixture
def temp_project_dir():
    """Create a temporary project directory structure."""
    with tempfile.TemporaryDirectory() as tmpdir:
        project_dir = Path(tmpdir)
        
        # Create directory structure
        (project_dir / "tools").mkdir()
        (project_dir / "resources").mkdir()
        (project_dir / "prompts").mkdir()
        (project_dir / "python").mkdir()
        (project_dir / "sql").mkdir()
        
        # Create mxcp-site.yml
        site_config = {
            "mxcp": 1,
            "project": "test-project",
            "profile": "test",
            "profiles": {
                "test": {
                    "duckdb": {
                        "path": str(project_dir / "test.duckdb")
                    }
                }
            },
            "paths": {
                "tools": "tools",
                "resources": "resources",
                "prompts": "prompts",
                "sql": "sql"
            },
            "extensions": ["json"]
        }
        
        with open(project_dir / "mxcp-site.yml", "w") as f:
            yaml.dump(site_config, f)
        
        # Change to project directory
        original_dir = os.getcwd()
        os.chdir(project_dir)
        
        yield project_dir
        
        # Restore original directory
        os.chdir(original_dir)


@pytest.fixture
def test_configs(temp_project_dir):
    """Create test configurations."""
    # Create user config file
    user_config_data = {
        "mxcp": 1,
        "projects": {
            "test-project": {
                "profiles": {
                    "test": {
                        "secrets": [
                            {
                                "name": "api_key",
                                "type": "value",
                                "parameters": {
                                    "value": "test-api-key-123"
                                }
                            }
                        ],
                        "plugin": {"config": {}}
                    }
                }
            }
        }
    }
    
    # Write user config to file
    config_path = temp_project_dir / "mxcp-config.yml"
    with open(config_path, "w") as f:
        yaml.dump(user_config_data, f)
    
    # Set environment variable to point to our config
    os.environ["MXCP_CONFIG"] = str(config_path)
    
    # Load site config first
    site_config = load_site_config()
    
    # Load user config
    user_config = load_user_config(site_config)
    
    yield user_config, site_config
    
    # Clean up environment variable
    if "MXCP_CONFIG" in os.environ:
        del os.environ["MXCP_CONFIG"]


@pytest.fixture
def test_session(test_configs):
    """Create a test DuckDB session."""
    user_config, site_config = test_configs
    session = DuckDBSession(user_config, site_config, profile="test")
    
    # Create test table
    session.conn.execute("""
        CREATE TABLE test_data (
            id INTEGER,
            name VARCHAR,
            value DOUBLE
        )
    """)
    session.conn.execute("""
        INSERT INTO test_data VALUES 
        (1, 'Alice', 100.5),
        (2, 'Bob', 200.7),
        (3, 'Charlie', 300.9)
    """)
    
    yield session
    
    session.close()


def test_python_loader(temp_project_dir):
    """Test PythonEndpointLoader functionality."""
    # Create a test Python file
    python_file = temp_project_dir / "python" / "test_module.py"
    python_file.write_text("""
def hello(name: str) -> dict:
    return {"message": f"Hello, {name}!"}

def add_numbers(a: int, b: int) -> dict:
    return {"result": a + b}
""")
    
    # Test loader
    loader = PythonEndpointLoader(temp_project_dir)
    
    # Load module
    module = loader.load_python_module(python_file)
    assert module is not None
    
    # Get functions
    hello_func = loader.get_function(module, "hello")
    assert hello_func("World") == {"message": "Hello, World!"}
    
    add_func = loader.get_function(module, "add_numbers")
    assert add_func(5, 3) == {"result": 8}
    
    # Test error cases
    with pytest.raises(AttributeError):
        loader.get_function(module, "non_existent")


def test_python_endpoint_with_db(temp_project_dir, test_configs, test_session):
    """Test Python endpoint with database access."""
    user_config, site_config = test_configs
    
    # Create Python endpoint file
    python_file = temp_project_dir / "python" / "data_tools.py"
    python_file.write_text("""
from mxcp.runtime import db

def get_data(min_value: float) -> list:
    return db.execute(
        "SELECT * FROM test_data WHERE value >= $min_value ORDER BY id",
        {"min_value": min_value}
    )

def count_records() -> dict:
    result = db.execute("SELECT COUNT(*) as count FROM test_data")
    return {"count": result[0]["count"]}
""")
    
    # Create tool definition
    tool_yaml = temp_project_dir / "tools" / "get_data.yml"
    tool_yaml.write_text("""
mxcp: 1
tool:
  name: get_data
  description: Get data above threshold
  language: python
  source:
    file: ../python/data_tools.py
  parameters:
    - name: min_value
      type: number
      description: Minimum value threshold
  return:
    type: array
""")
    
    # Set runtime context
    _set_runtime_context(test_session, user_config, site_config, {})
    
    try:
        # Execute endpoint
        executor = EndpointExecutor(
            EndpointType.TOOL,
            "get_data",
            user_config,
            site_config,
            test_session
        )
        
        # Run async execution
        async def run_test():
            result = await executor.execute({"min_value": 200})
            return result
        
        result = asyncio.run(run_test())
        
        # Check results
        assert len(result) == 2
        assert result[0]["name"] == "Bob"
        assert result[1]["name"] == "Charlie"
        
    finally:
        _clear_runtime_context()


def test_python_endpoint_with_secrets(temp_project_dir, test_configs, test_session):
    """Test Python endpoint accessing secrets."""
    user_config, site_config = test_configs
    
    # Create Python endpoint file
    python_file = temp_project_dir / "python" / "secret_test.py"
    python_file.write_text("""
from mxcp.runtime import config

def get_secret_info() -> dict:
    api_key = config.get_secret("api_key")
    missing = config.get_secret("missing_key")
    setting = config.get_setting("project")
    
    return {
        "has_api_key": api_key is not None,
        "api_key_starts_with": api_key[:5] if api_key else None,
        "missing_key": missing,
        "project": setting
    }
""")
    
    # Create tool definition
    tool_yaml = temp_project_dir / "tools" / "get_secret_info.yml"
    tool_yaml.write_text("""
mxcp: 1
tool:
  name: get_secret_info
  description: Test secret access
  language: python
  source:
    file: ../python/secret_test.py
  parameters: []
  return:
    type: object
""")
    
    # Set runtime context
    _set_runtime_context(test_session, user_config, site_config, {})
    
    try:
        # Execute endpoint
        executor = EndpointExecutor(
            EndpointType.TOOL,
            "get_secret_info",
            user_config,
            site_config,
            test_session
        )
        
        # Run async execution
        async def run_test():
            result = await executor.execute({})
            return result
        
        result = asyncio.run(run_test())
        
        # Check results
        assert result["has_api_key"] is True
        assert result["api_key_starts_with"] == "test-"
        assert result["missing_key"] is None
        assert result["project"] == "test-project"
        
    finally:
        _clear_runtime_context()


def test_lifecycle_hooks(temp_project_dir, test_configs, test_session):
    """Test lifecycle hooks functionality."""
    # Clear any existing hooks
    _init_hooks.clear()
    _shutdown_hooks.clear()
    
    # Track hook calls
    calls = []
    
    # Create Python file with hooks
    python_file = temp_project_dir / "python" / "lifecycle_test.py"
    python_file.write_text("""
from mxcp.runtime import on_init, on_shutdown

@on_init
def setup():
    global initialized
    initialized = True
    
@on_shutdown
def cleanup():
    global cleaned_up
    cleaned_up = True
    
def check_state() -> dict:
    return {
        "initialized": globals().get("initialized", False),
        "cleaned_up": globals().get("cleaned_up", False)
    }
""")
    
    # Load the module to register hooks
    loader = PythonEndpointLoader(temp_project_dir)
    module = loader.load_python_module(python_file)
    
    # Run hooks
    from mxcp.runtime import _run_init_hooks, _run_shutdown_hooks
    
    # Check initial state
    check_func = loader.get_function(module, "check_state")
    state = check_func()
    assert state["initialized"] is False
    assert state["cleaned_up"] is False
    
    # Run init hooks
    _run_init_hooks()
    state = check_func()
    assert state["initialized"] is True
    assert state["cleaned_up"] is False
    
    # Run shutdown hooks
    _run_shutdown_hooks()
    state = check_func()
    assert state["initialized"] is True
    assert state["cleaned_up"] is True
    
    # Clear hooks to avoid affecting other tests
    _init_hooks.clear()
    _shutdown_hooks.clear()


def test_async_python_endpoint(temp_project_dir, test_configs, test_session):
    """Test async Python endpoint."""
    user_config, site_config = test_configs
    
    # Create async Python endpoint
    python_file = temp_project_dir / "python" / "async_tools.py"
    python_file.write_text("""
import asyncio
from mxcp.runtime import db

async def slow_query(delay: float) -> dict:
    # Simulate async operation
    await asyncio.sleep(delay)
    
    # Access database
    result = db.execute("SELECT COUNT(*) as count FROM test_data")
    
    return {
        "delayed": delay,
        "count": result[0]["count"]
    }
""")
    
    # Create tool definition
    tool_yaml = temp_project_dir / "tools" / "slow_query.yml"
    tool_yaml.write_text("""
mxcp: 1
tool:
  name: slow_query
  description: Async query with delay
  language: python
  source:
    file: ../python/async_tools.py
  parameters:
    - name: delay
      type: number
      description: Delay in seconds
  return:
    type: object
""")
    
    # Set runtime context
    _set_runtime_context(test_session, user_config, site_config, {})
    
    try:
        # Execute endpoint
        executor = EndpointExecutor(
            EndpointType.TOOL,
            "slow_query",
            user_config,
            site_config,
            test_session
        )
        
        # Run async execution
        async def run_test():
            result = await executor.execute({"delay": 0.1})
            return result
        
        result = asyncio.run(run_test())
        
        # Check results
        assert result["delayed"] == 0.1
        assert result["count"] == 3
        
    finally:
        _clear_runtime_context()


def test_python_endpoint_error_handling(temp_project_dir, test_configs, test_session):
    """Test error handling in Python endpoints."""
    user_config, site_config = test_configs
    
    # Create Python endpoint with error
    python_file = temp_project_dir / "python" / "error_test.py"
    python_file.write_text("""
def divide_numbers(a: int, b: int) -> dict:
    if b == 0:
        raise ValueError("Cannot divide by zero")
    return {"result": a / b}
""")
    
    # Create tool definition
    tool_yaml = temp_project_dir / "tools" / "divide_numbers.yml"
    tool_yaml.write_text("""
mxcp: 1
tool:
  name: divide_numbers
  description: Divide two numbers
  language: python
  source:
    file: ../python/error_test.py
  parameters:
    - name: a
      type: integer
      description: The dividend
    - name: b
      type: integer
      description: The divisor
  return:
    type: object
""")
    
    # Execute endpoint with valid inputs
    executor = EndpointExecutor(
        EndpointType.TOOL,
        "divide_numbers",
        user_config,
        site_config,
        test_session
    )
    
    async def run_valid():
        result = await executor.execute({"a": 10, "b": 2})
        return result
    
    result = asyncio.run(run_valid())
    assert result["result"] == 5.0
    
    # Execute with error
    async def run_error():
        result = await executor.execute({"a": 10, "b": 0})
        return result
    
    with pytest.raises(ValueError, match="Cannot divide by zero"):
        asyncio.run(run_error()) 