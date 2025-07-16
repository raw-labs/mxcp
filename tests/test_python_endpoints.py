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
from mxcp.endpoints.sdk_executor import execute_endpoint_with_engine
from mxcp.config.execution_engine import create_execution_engine
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
def execution_engine(test_configs):
    """Create execution engine for tests and set up test data."""
    user_config, site_config = test_configs
    engine = create_execution_engine(user_config, site_config)
    
    # Get the DuckDB executor from the engine
    duckdb_executor = None
    for executor in engine._executors.values():
        if hasattr(executor, 'language') and executor.language == "sql":
            duckdb_executor = executor
            break
    
    if duckdb_executor:
        # Get the DuckDB session and connection
        from mxcp.sdk.executor.plugins import DuckDBExecutor
        if isinstance(duckdb_executor, DuckDBExecutor):
            session = duckdb_executor.session
            conn = session.conn
            
            # Create test table if connection exists
            if conn:
                conn.execute("""
                    CREATE TABLE test_data (
                        id INTEGER,
                        name VARCHAR,
                        value DOUBLE
                    )
                """)
                conn.execute("""
                    INSERT INTO test_data VALUES 
                    (1, 'Alice', 100.5),
                    (2, 'Bob', 200.7),
                    (3, 'Charlie', 300.9)
                """)
    
    yield engine
    
    # Clean up - the engine shutdown should handle this
    engine.shutdown()


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


@pytest.mark.asyncio
async def test_python_endpoint_with_db(temp_project_dir, test_configs, execution_engine):
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
    
    result = await execute_endpoint_with_engine(
        endpoint_type="tool",
        name="get_data",
        params={"min_value": 200},
        user_config=user_config,
        site_config=site_config,
        execution_engine=execution_engine
    )
    
    # Check results
    assert len(result) == 2
    assert result[0]["name"] == "Bob"
    assert result[1]["name"] == "Charlie"


@pytest.mark.asyncio
async def test_python_endpoint_with_secrets(temp_project_dir, test_configs, execution_engine):
    """Test Python endpoint accessing secrets."""
    user_config, site_config = test_configs
    
    # Create Python endpoint file
    python_file = temp_project_dir / "python" / "secret_test.py"
    python_file.write_text("""
from mxcp.runtime import config

def get_secret_info() -> dict:
    # get_secret now returns the parameters dict
    api_key_params = config.get_secret("api_key")
    missing = config.get_secret("missing_key")
    setting = config.get_setting("project")
    
    # Extract value from value-type secret
    api_key = api_key_params["value"] if api_key_params else None
    
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
    
    result = await execute_endpoint_with_engine(
        endpoint_type="tool",
        name="get_secret_info",
        params={},
        user_config=user_config,
        site_config=site_config,
        execution_engine=execution_engine
    )
    
    # Check results
    assert result["has_api_key"] is True
    assert result["api_key_starts_with"] == "test-"
    assert result["missing_key"] is None
    assert result["project"] == "test-project"


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


@pytest.mark.asyncio
async def test_async_python_endpoint(temp_project_dir, test_configs, execution_engine):
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
    
    result = await execute_endpoint_with_engine(
        endpoint_type="tool",
        name="slow_query",
        params={"delay": 0.1},
        user_config=user_config,
        site_config=site_config,
        execution_engine=execution_engine
    )
    
    # Check results
    assert result["delayed"] == 0.1
    assert result["count"] == 3


def test_async_context_propagation(temp_project_dir, test_configs, test_session):
    """Test that context variables propagate correctly in async Python endpoints after fix."""
    user_config, site_config = test_configs
    
    # Create async Python endpoint that uses context variables
    python_file = temp_project_dir / "python" / "async_context_test.py"
    python_file.write_text("""
import asyncio
from mxcp.runtime import db, config

async def test_context_access() -> dict:
    \"\"\"Test context variable access in async function.\"\"\"
    # Try to access database (requires context)
    try:
        db_result = db.execute("SELECT COUNT(*) as count FROM test_data")
        db_access_works = True
        row_count = db_result[0]["count"]
    except Exception as e:
        db_access_works = False
        row_count = None
        error = str(e)
    
    # Try to access config (requires context)
    try:
        project = config.get_setting("project")
        secret = config.get_secret("api_key")
        config_access_works = True
        secret_value = secret["value"] if secret else None
    except Exception as e:
        config_access_works = False
        project = None
        secret_value = None
    
    # Test nested async calls
    nested_result = await _nested_async()
    
    return {
        "db_access_works": db_access_works,
        "row_count": row_count,
        "config_access_works": config_access_works,
        "project": project,
        "secret_value": secret_value,
        "nested_result": nested_result
    }

async def _nested_async() -> dict:
    \"\"\"Nested async function to test context propagation.\"\"\"
    await asyncio.sleep(0.01)  # Simulate async work
    
    try:
        # Context should still be available in nested async calls
        result = db.execute("SELECT name FROM test_data WHERE id = 1")
        return {
            "nested_works": True,
            "name": result[0]["name"] if result else None
        }
    except Exception as e:
        return {
            "nested_works": False,
            "error": str(e)
        }
""")
    
    # Create tool definition
    tool_yaml = temp_project_dir / "tools" / "test_context_access.yml"
    tool_yaml.write_text("""
mxcp: 1
tool:
  name: test_context_access
  description: Test context access in async endpoint
  language: python
  source:
    file: ../python/async_context_test.py
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
            "test_context_access",
            user_config,
            site_config,
            test_session
        )
        
        # Run async execution
        async def run_test():
            result = await executor.execute({})
            return result
        
        result = asyncio.run(run_test())
        
        # Verify context was properly available
        assert result["db_access_works"] is True, "Database access should work in async function"
        assert result["row_count"] == 3, "Should be able to query database"
        assert result["config_access_works"] is True, "Config access should work in async function"
        assert result["project"] == "test-project", "Should be able to read project name"
        assert result["secret_value"] == "test-api-key-123", "Should be able to read secret"
        
        # Verify nested async also had context
        assert result["nested_result"]["nested_works"] is True, "Nested async should have context"
        assert result["nested_result"]["name"] == "Alice", "Nested async should be able to query DB"
        
    finally:
        _clear_runtime_context()


def test_python_endpoint_with_non_duckdb_secret_type(temp_project_dir):
    """Test Python endpoint accessing secrets with non-DuckDB types (e.g., 'custom', 'python')."""
    # Create custom user config with non-DuckDB secret type
    user_config_data = {
        "mxcp": 1,
        "projects": {
            "test-project": {
                "profiles": {
                    "test": {
                        "secrets": [
                            {
                                "name": "custom_api",
                                "type": "custom",  # Non-DuckDB type
                                "parameters": {
                                    "api_key": "custom-api-key-456",
                                    "endpoint": "https://api.example.com",
                                    "headers": {
                                        "X-Custom": "header-value"
                                    }
                                }
                            },
                            {
                                "name": "python_only",
                                "type": "python",  # Hypothetical Python-only type
                                "parameters": {
                                    "value": "python-secret-789",
                                    "config": {
                                        "nested": "value"
                                    }
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
    
    try:
        # Load configs
        site_config = load_site_config()
        user_config = load_user_config(site_config)
        
        # Update site config to reference our secrets
        site_config["secrets"] = ["custom_api", "python_only"]
        
        # Create Python endpoint file
        python_file = temp_project_dir / "python" / "custom_secrets.py"
        python_file.write_text("""
from mxcp.runtime import config

def test_custom_secrets() -> dict:
    # Test getting custom type secret
    custom_params = config.get_secret("custom_api")
    python_params = config.get_secret("python_only")
    
    return {
        "custom_api_key": custom_params["api_key"] if custom_params else None,
        "custom_endpoint": custom_params.get("endpoint") if custom_params else None,
        "custom_headers": custom_params.get("headers") if custom_params else None,
        "python_value": python_params["value"] if python_params else None,
        "python_config": python_params.get("config") if python_params else None,
        "both_secrets_found": custom_params is not None and python_params is not None
    }
""")
        
        # Create tool definition
        tool_yaml = temp_project_dir / "tools" / "test_custom_secrets.yml"
        tool_yaml.write_text("""
mxcp: 1
tool:
  name: test_custom_secrets
  description: Test non-DuckDB secret types
  language: python
  source:
    file: ../python/custom_secrets.py
  parameters: []
  return:
    type: object
""")
        
        # Create test DuckDB session
        with DuckDBSession(user_config, site_config) as test_session:
            # Set runtime context
            _set_runtime_context(test_session, user_config, site_config, {})
            
            try:
                # Execute endpoint
                executor = EndpointExecutor(
                    EndpointType.TOOL,
                    "test_custom_secrets",
                    user_config,
                    site_config,
                    test_session
                )
                
                # Run async execution
                async def run_test():
                    result = await executor.execute({})
                    return result
                
                result = asyncio.run(run_test())
                
                # Check results - secrets should be accessible even with non-DuckDB types
                assert result["custom_api_key"] == "custom-api-key-456"
                assert result["custom_endpoint"] == "https://api.example.com"
                assert result["custom_headers"]["X-Custom"] == "header-value"
                assert result["python_value"] == "python-secret-789"
                assert result["python_config"]["nested"] == "value"
                assert result["both_secrets_found"] is True
                
                # Verify no DuckDB errors by checking that session is still valid
                # Non-DuckDB secret types should be silently skipped
                assert test_session.conn is not None
                
            finally:
                _clear_runtime_context()
                
    finally:
        # Clean up environment variable
        if "MXCP_CONFIG" in os.environ:
            del os.environ["MXCP_CONFIG"]





@pytest.mark.asyncio
async def test_python_endpoint_error_handling(temp_project_dir, test_configs, execution_engine):
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
    result = await execute_endpoint_with_engine(
        endpoint_type="tool",
        name="divide_numbers",
        params={"a": 10, "b": 2},
        user_config=user_config,
        site_config=site_config,
        execution_engine=execution_engine
    )
    assert result["result"] == 5.0
    
    # Execute with error
    with pytest.raises(ValueError, match="Cannot divide by zero"):
        await execute_endpoint_with_engine(
            endpoint_type="tool",
            name="divide_numbers",
            params={"a": 10, "b": 0},
            user_config=user_config,
            site_config=site_config,
            execution_engine=execution_engine
        )


def test_python_endpoint_all_types(temp_project_dir, test_configs, test_session):
    """Test Python endpoints with all supported parameter and return types."""
    user_config, site_config = test_configs
    
    # Create Python endpoint file with all types
    python_file = temp_project_dir / "python" / "type_test.py"
    python_file.write_text("""
from datetime import datetime, date, time, timedelta
from mxcp.runtime import db
import json

def test_all_param_types(
    str_param: str,
    int_param: int,
    float_param: float,
    bool_param: bool,
    array_param: list,
    obj_param: dict,
    date_param: str,
    email_param: str,
    enum_param: str,
    optional_param: str = "default"
) -> dict:
    \"\"\"Test all parameter types.\"\"\"
    return {
        "str_param": f"Received: {str_param}",
        "int_param": int_param * 2,
        "float_param": float_param * 1.5,
        "bool_param": not bool_param,
        "array_param": array_param + ["added"],
        "obj_param": {**obj_param, "added": True},
        "date_param": date_param,
        "email_param": email_param.upper(),
        "enum_param": enum_param,
        "optional_param": optional_param,
        "timestamp": datetime.now(),
        "date_only": date.today(),
        "time_only": time(14, 30, 0),
        "nested": {
            "timestamp": datetime.now(),
            "array_with_dates": [
                {"date": date.today(), "value": 1},
                {"date": date.today(), "value": 2}
            ]
        }
    }

def test_array_return() -> list:
    \"\"\"Test array return type with timestamps.\"\"\"
    return [
        {"id": 1, "created": datetime.now(), "name": "First"},
        {"id": 2, "created": datetime.now() - timedelta(days=1), "name": "Second"},
        {"id": 3, "created": datetime.now() - timedelta(days=2), "name": "Third"}
    ]

def test_scalar_string() -> str:
    \"\"\"Test scalar string return.\"\"\"
    return "Hello, World!"

def test_scalar_number() -> float:
    \"\"\"Test scalar number return.\"\"\"
    return 42.5

def test_scalar_boolean() -> bool:
    \"\"\"Test scalar boolean return.\"\"\"
    return True

def test_scalar_date() -> datetime:
    \"\"\"Test scalar date return.\"\"\"
    return datetime.now()

def test_constraints(
    str_min_max: str,
    int_min_max: int,
    array_min_max: list,
    str_pattern: str
) -> dict:
    \"\"\"Test parameter constraints.\"\"\"
    return {
        "str_length": len(str_min_max),
        "int_value": int_min_max,
        "array_length": len(array_min_max),
        "pattern_matched": str_pattern
    }

def test_sql_with_dates() -> list:
    \"\"\"Test SQL execution returning timestamps.\"\"\"
    # Create a temporary table with timestamps
    db.execute(\"\"\"
        CREATE TEMPORARY TABLE IF NOT EXISTS test_dates (
            id INTEGER,
            created_at TIMESTAMP,
            updated_at DATE
        )
    \"\"\")
    
    # Insert test data
    db.execute(\"\"\"
        INSERT INTO test_dates VALUES 
        (1, CURRENT_TIMESTAMP, CURRENT_DATE),
        (2, CURRENT_TIMESTAMP - INTERVAL '1 day', CURRENT_DATE - INTERVAL '1 day')
    \"\"\")
    
    # Query and return results
    return db.execute("SELECT * FROM test_dates ORDER BY id")
""")
    
    # Create tool definition for all parameter types
    tool_yaml = temp_project_dir / "tools" / "test_all_param_types.yml"
    tool_yaml.write_text("""
mxcp: 1
tool:
  name: test_all_param_types
  description: Test all parameter types
  language: python
  source:
    file: ../python/type_test.py
  parameters:
    - name: str_param
      type: string
      description: Basic string parameter
    - name: int_param
      type: integer
      description: Integer parameter
    - name: float_param
      type: number
      description: Float parameter
    - name: bool_param
      type: boolean
      description: Boolean parameter
    - name: array_param
      type: array
      description: Array parameter
      items:
        type: string
    - name: obj_param
      type: object
      description: Object parameter
      properties:
        key1:
          type: string
        key2:
          type: integer
    - name: date_param
      type: string
      format: date
      description: Date parameter
    - name: email_param
      type: string
      format: email
      description: Email parameter
    - name: enum_param
      type: string
      enum: ["option1", "option2", "option3"]
      description: Enum parameter
    - name: optional_param
      type: string
      description: Optional parameter with default
      default: "default"
  return:
    type: object
""")
    
    # Create tool for array return
    array_yaml = temp_project_dir / "tools" / "test_array_return.yml"
    array_yaml.write_text("""
mxcp: 1
tool:
  name: test_array_return
  description: Test array return type
  language: python
  source:
    file: ../python/type_test.py
  parameters: []
  return:
    type: array
""")
    
    # Create tools for scalar returns
    scalar_tools = [
        ("test_scalar_string", "string"),
        ("test_scalar_number", "number"),
        ("test_scalar_boolean", "boolean"),
        ("test_scalar_date", "string", "date-time")
    ]
    
    for tool_name, return_type, *format_args in scalar_tools:
        scalar_yaml = temp_project_dir / "tools" / f"{tool_name}.yml"
        yaml_content = f"""
mxcp: 1
tool:
  name: {tool_name}
  description: Test {return_type} scalar return
  language: python
  source:
    file: ../python/type_test.py
  parameters: []
  return:
    type: {return_type}"""
        if format_args:
            yaml_content += f"\n    format: {format_args[0]}"
        scalar_yaml.write_text(yaml_content)
    
    # Create tool for constraints
    constraints_yaml = temp_project_dir / "tools" / "test_constraints.yml"
    constraints_yaml.write_text("""
mxcp: 1
tool:
  name: test_constraints
  description: Test parameter constraints
  language: python
  source:
    file: ../python/type_test.py
  parameters:
    - name: str_min_max
      type: string
      minLength: 3
      maxLength: 10
      description: String with length constraints
    - name: int_min_max
      type: integer
      minimum: 0
      maximum: 100
      description: Integer with range constraints
    - name: array_min_max
      type: array
      minItems: 2
      maxItems: 5
      description: Array with size constraints
      items:
        type: string
    - name: str_pattern
      type: string
      pattern: "^[A-Z][a-z]+$"
      description: String matching pattern
  return:
    type: object
""")
    
    # Create tool for SQL with dates
    sql_dates_yaml = temp_project_dir / "tools" / "test_sql_with_dates.yml"
    sql_dates_yaml.write_text("""
mxcp: 1
tool:
  name: test_sql_with_dates
  description: Test SQL execution with timestamps
  language: python
  source:
    file: ../python/type_test.py
  parameters: []
  return:
    type: array
""")
    
    # Set runtime context
    _set_runtime_context(test_session, user_config, site_config, {})
    
    try:
        # Test 1: All parameter types
        executor = EndpointExecutor(
            EndpointType.TOOL,
            "test_all_param_types",
            user_config,
            site_config,
            test_session
        )
        
        async def test_all_params():
            result = await executor.execute({
                "str_param": "hello",
                "int_param": 42,
                "float_param": 3.14,
                "bool_param": True,
                "array_param": ["item1", "item2"],
                "obj_param": {"key1": "value1", "key2": 123},
                "date_param": "2024-01-15",
                "email_param": "test@example.com",
                "enum_param": "option2"
                # optional_param not provided, should use default
            })
            return result
        
        result = asyncio.run(test_all_params())
        assert result["str_param"] == "Received: hello"
        assert result["int_param"] == 84
        assert abs(result["float_param"] - 4.71) < 0.01  # Use approximate comparison for floats
        assert result["bool_param"] is False
        assert result["array_param"] == ["item1", "item2", "added"]
        assert result["obj_param"] == {"key1": "value1", "key2": 123, "added": True}
        assert result["email_param"] == "TEST@EXAMPLE.COM"
        assert result["enum_param"] == "option2"
        assert result["optional_param"] == "default"
        # Check timestamp serialization
        assert isinstance(result["timestamp"], str)
        assert isinstance(result["date_only"], str)
        assert isinstance(result["time_only"], str)
        assert isinstance(result["nested"]["timestamp"], str)
        assert isinstance(result["nested"]["array_with_dates"][0]["date"], str)
        
        # Test invalid email format
        async def test_invalid_email():
            await executor.execute({
                "str_param": "hello",
                "int_param": 42,
                "float_param": 3.14,
                "bool_param": True,
                "array_param": ["item1", "item2"],
                "obj_param": {"key1": "value1", "key2": 123},
                "date_param": "2024-01-15",
                "email_param": "invalid-email",  # Missing @ and domain
                "enum_param": "option2"
            })
        
        with pytest.raises(ValueError, match="Invalid email format"):
            asyncio.run(test_invalid_email())
        
        # Test invalid enum value
        async def test_invalid_enum():
            await executor.execute({
                "str_param": "hello",
                "int_param": 42,
                "float_param": 3.14,
                "bool_param": True,
                "array_param": ["item1", "item2"],
                "obj_param": {"key1": "value1", "key2": 123},
                "date_param": "2024-01-15",
                "email_param": "test@example.com",
                "enum_param": "invalid_option"  # Not in allowed enum values
            })
        
        with pytest.raises(ValueError, match="Must be one of"):
            asyncio.run(test_invalid_enum())
        
        # Test 2: Array return with timestamps
        executor2 = EndpointExecutor(
            EndpointType.TOOL,
            "test_array_return",
            user_config,
            site_config,
            test_session
        )
        
        async def test_array():
            result = await executor2.execute({})
            return result
        
        result = asyncio.run(test_array())
        assert len(result) == 3
        assert all(isinstance(item["created"], str) for item in result)
        assert result[0]["name"] == "First"
        
        # Test 3: Scalar returns
        scalar_tests = [
            ("test_scalar_string", "Hello, World!"),
            ("test_scalar_number", 42.5),
            ("test_scalar_boolean", True),
            ("test_scalar_date", str)  # Check it's a string
        ]
        
        for tool_name, expected in scalar_tests:
            executor = EndpointExecutor(
                EndpointType.TOOL,
                tool_name,
                user_config,
                site_config,
                test_session
            )
            
            async def test_scalar():
                result = await executor.execute({})
                return result
            
            result = asyncio.run(test_scalar())
            if expected == str:
                assert isinstance(result, str)  # For datetime
            else:
                assert result == expected
        
        # Test 4: Constraints validation
        executor4 = EndpointExecutor(
            EndpointType.TOOL,
            "test_constraints",
            user_config,
            site_config,
            test_session
        )
        
        # Valid constraints
        async def test_valid_constraints():
            result = await executor4.execute({
                "str_min_max": "hello",
                "int_min_max": 50,
                "array_min_max": ["a", "b", "c"],
                "str_pattern": "Hello"
            })
            return result
        
        result = asyncio.run(test_valid_constraints())
        assert result["str_length"] == 5
        assert result["int_value"] == 50
        
        # Test constraint violations
        async def test_string_too_short():
            await executor4.execute({
                "str_min_max": "hi",  # Too short
                "int_min_max": 50,
                "array_min_max": ["a", "b"],
                "str_pattern": "Hello"
            })
        
        with pytest.raises(ValueError, match="at least 3 characters"):
            asyncio.run(test_string_too_short())
        
        async def test_int_out_of_range():
            await executor4.execute({
                "str_min_max": "hello",
                "int_min_max": 150,  # Too large
                "array_min_max": ["a", "b"],
                "str_pattern": "Hello"
            })
        
        with pytest.raises(ValueError, match="<= 100"):
            asyncio.run(test_int_out_of_range())
        
        # Test pattern validation failure
        async def test_pattern_mismatch():
            await executor4.execute({
                "str_min_max": "hello",
                "int_min_max": 50,
                "array_min_max": ["a", "b"],
                "str_pattern": "hello"  # Should start with capital letter
            })
        
        # Pattern validation is currently not implemented in TypeConverter
        # This would need to be added to fully support JSON Schema pattern validation
        
        # Test array size constraints
        async def test_array_too_small():
            await executor4.execute({
                "str_min_max": "hello",
                "int_min_max": 50,
                "array_min_max": ["a"],  # Too few items (min 2)
                "str_pattern": "Hello"
            })
        
        with pytest.raises(ValueError, match="at least 2 items"):
            asyncio.run(test_array_too_small())
        
        async def test_array_too_large():
            await executor4.execute({
                "str_min_max": "hello",
                "int_min_max": 50,
                "array_min_max": ["a", "b", "c", "d", "e", "f"],  # Too many items (max 5)
                "str_pattern": "Hello"
            })
        
        with pytest.raises(ValueError, match="at most 5 items"):
            asyncio.run(test_array_too_large())
        
        # Test 5: SQL with timestamps
        executor5 = EndpointExecutor(
            EndpointType.TOOL,
            "test_sql_with_dates",
            user_config,
            site_config,
            test_session
        )
        
        async def test_sql_dates():
            result = await executor5.execute({})
            return result
        
        result = asyncio.run(test_sql_dates())
        assert len(result) == 2
        # Check all timestamps are serialized as strings
        for row in result:
            assert isinstance(row["created_at"], str)
            assert isinstance(row["updated_at"], str)
        
    finally:
        _clear_runtime_context()


def test_python_parameter_mismatches(temp_project_dir, test_configs, test_session):
    """Test parameter mismatches between YAML definition and Python function signature."""
    user_config, site_config = test_configs
    
    # Create Python file with various function signatures
    python_file = temp_project_dir / "python" / "param_mismatch_test.py"
    python_file.write_text("""
def missing_args(a: int, b: int) -> dict:
    \"\"\"Function that expects two arguments\"\"\"
    return {"result": a + b}

def missing_args_python(a: int, b: int) -> dict:
    \"\"\"Function that expects two arguments\"\"\"
    return {"result": a + b}

def extra_args(a: int) -> dict:
    \"\"\"Function that expects only one argument\"\"\"
    return {"result": a * 2}

def optional_params(a: int, b: int = 10, c: str = "default") -> dict:
    \"\"\"Function with optional parameters\"\"\"
    return {
        "a": a,
        "b": b,
        "c": c,
        "sum": a + b
    }

def optional_params_proper(a: int, b: int = 10, c: str = "default") -> dict:
    \"\"\"Function with optional parameters\"\"\"
    return {
        "a": a,
        "b": b,
        "c": c,
        "sum": a + b
    }

def kwargs_function(a: int, **kwargs) -> dict:
    \"\"\"Function that accepts **kwargs\"\"\"
    return {
        "a": a,
        "extra_keys": list(kwargs.keys()),
        "extra_values": kwargs
    }

def positional_only(a: int, b: int, /) -> dict:
    \"\"\"Function with positional-only parameters\"\"\"
    return {"result": a - b}
""")
    
    # Test 1: Missing required arguments
    # YAML defines no parameters, but function expects 2
    tool_yaml = temp_project_dir / "tools" / "missing_args.yml"
    tool_yaml.write_text("""
mxcp: 1
tool:
  name: missing_args
  description: Test missing arguments
  language: python
  source:
    file: ../python/param_mismatch_test.py
  parameters: []
  return:
    type: object
""")
    
    executor = EndpointExecutor(
        EndpointType.TOOL,
        "missing_args",
        user_config,
        site_config,
        test_session
    )
    
    # Set runtime context
    _set_runtime_context(test_session, user_config, site_config, {})
    
    try:
        # This should raise TypeError because function expects 'a' and 'b'
        async def test_missing():
            result = await executor.execute({})
            return result
        
        with pytest.raises(TypeError, match="missing.*required.*argument"):
            asyncio.run(test_missing())
    finally:
        _clear_runtime_context()
    
    # Test 2: Too many arguments
    # YAML defines parameters that function doesn't accept
    tool_yaml2 = temp_project_dir / "tools" / "extra_args.yml"
    tool_yaml2.write_text("""
mxcp: 1
tool:
  name: extra_args
  description: Test extra arguments
  language: python
  source:
    file: ../python/param_mismatch_test.py
  parameters:
    - name: a
      type: integer
      description: First number
    - name: b
      type: integer
      description: Second number (function doesn't expect this)
    - name: c
      type: string
      description: Extra parameter
  return:
    type: object
""")
    
    executor2 = EndpointExecutor(
        EndpointType.TOOL,
        "extra_args",
        user_config,
        site_config,
        test_session
    )
    
    # Set runtime context
    _set_runtime_context(test_session, user_config, site_config, {})
    
    try:
        # This should raise TypeError because function doesn't accept 'b' and 'c'
        async def test_extra():
            result = await executor2.execute({"a": 5, "b": 10, "c": "extra"})
            return result
        
        with pytest.raises(TypeError, match="unexpected keyword argument"):
            asyncio.run(test_extra())
    finally:
        _clear_runtime_context()
    
    # Test 3: Optional parameters - not passing them
    tool_yaml3 = temp_project_dir / "tools" / "optional_params.yml"
    tool_yaml3.write_text("""
mxcp: 1
tool:
  name: optional_params
  description: Test optional parameters
  language: python
  source:
    file: ../python/param_mismatch_test.py
  parameters:
    - name: a
      type: integer
      description: Required parameter
  return:
    type: object
""")
    
    executor3 = EndpointExecutor(
        EndpointType.TOOL,
        "optional_params",
        user_config,
        site_config,
        test_session
    )
    
    # Set runtime context
    _set_runtime_context(test_session, user_config, site_config, {})
    
    try:
        # This should work - 'b' and 'c' have defaults
        async def test_optional_not_passed():
            result = await executor3.execute({"a": 5})
            return result
        
        result = asyncio.run(test_optional_not_passed())
        assert result["a"] == 5
        assert result["b"] == 10  # default value
        assert result["c"] == "default"  # default value
        assert result["sum"] == 15
    finally:
        _clear_runtime_context()
    
    # Test 4: YAML validator prevents unknown parameters
    # This test shows that unknown parameters are caught at validation time
    tool_yaml4 = temp_project_dir / "tools" / "validate_params.yml"
    tool_yaml4.write_text("""
mxcp: 1
tool:
  name: extra_args
  description: Test YAML validation
  language: python
  source:
    file: ../python/param_mismatch_test.py
  parameters:
    - name: a
      type: integer
      description: Only parameter defined in YAML
  return:
    type: object
""")
    
    executor4 = EndpointExecutor(
        EndpointType.TOOL,
        "extra_args",
        user_config,
        site_config,
        test_session
    )
    
    # The executor validates against YAML first, so unknown params are rejected
    async def test_unknown_params():
        result = await executor4.execute({"a": 5, "b": 10})
        return result
    
    with pytest.raises(ValueError, match="Unknown parameter: b"):
        asyncio.run(test_unknown_params())
    
    # Test 5: Python function with missing required params (YAML defines param but doesn't pass it)
    tool_yaml5 = temp_project_dir / "tools" / "missing_args_python.yml"
    tool_yaml5.write_text("""
mxcp: 1
tool:
  name: missing_args_python
  description: Test missing function arguments
  language: python
  source:
    file: ../python/param_mismatch_test.py
  parameters:
    - name: a
      type: integer
      description: Only one param defined, but function needs two
  return:
    type: object
""")
    
    executor5 = EndpointExecutor(
        EndpointType.TOOL,
        "missing_args_python",
        user_config,
        site_config,
        test_session
    )
    
    # Set runtime context
    _set_runtime_context(test_session, user_config, site_config, {})
    
    try:
        # This should raise TypeError at function call time
        async def test_missing_func_param():
            result = await executor5.execute({"a": 5})
            return result
        
        with pytest.raises(TypeError, match="missing.*required.*argument.*'b'"):
            asyncio.run(test_missing_func_param())
    finally:
        _clear_runtime_context()
    
    # Test 5b: Optional parameters properly defined in YAML
    tool_yaml5b = temp_project_dir / "tools" / "optional_params_proper.yml"
    tool_yaml5b.write_text("""
mxcp: 1
tool:
  name: optional_params_proper
  description: Test optional parameters with proper YAML definition
  language: python
  source:
    file: ../python/param_mismatch_test.py
  parameters:
    - name: a
      type: integer
      description: Required parameter
    - name: b
      type: integer
      description: Optional parameter
      default: 10
    - name: c
      type: string
      description: Optional string parameter
      default: "default"
  return:
    type: object
""")
    
    executor5b = EndpointExecutor(
        EndpointType.TOOL,
        "optional_params_proper",
        user_config,
        site_config,
        test_session
    )
    
    # Set runtime context
    _set_runtime_context(test_session, user_config, site_config, {})
    
    try:
        # Test with only required param - should use defaults from YAML
        async def test_yaml_defaults():
            result = await executor5b.execute({"a": 7})
            return result
        
        result = asyncio.run(test_yaml_defaults())
        assert result["a"] == 7
        assert result["b"] == 10  # YAML default
        assert result["c"] == "default"  # YAML default
        
        # Test overriding defaults
        async def test_override_defaults():
            result = await executor5b.execute({"a": 3, "b": 15, "c": "override"})
            return result
        
        result = asyncio.run(test_override_defaults())
        assert result["a"] == 3
        assert result["b"] == 15
        assert result["c"] == "override"
        assert result["sum"] == 18
    finally:
        _clear_runtime_context()
    
    # Test 6: Function with **kwargs accepts extra arguments
    tool_yaml6 = temp_project_dir / "tools" / "kwargs_function.yml"
    tool_yaml6.write_text("""
mxcp: 1
tool:
  name: kwargs_function
  description: Test function with **kwargs
  language: python
  source:
    file: ../python/param_mismatch_test.py
  parameters:
    - name: a
      type: integer
      description: Required parameter
    - name: extra1
      type: string
      description: Extra parameter 1
    - name: extra2
      type: integer
      description: Extra parameter 2
  return:
    type: object
""")
    
    executor6 = EndpointExecutor(
        EndpointType.TOOL,
        "kwargs_function",
        user_config,
        site_config,
        test_session
    )
    
    # Set runtime context
    _set_runtime_context(test_session, user_config, site_config, {})
    
    try:
        # This should work - function accepts **kwargs
        async def test_kwargs():
            result = await executor6.execute({"a": 5, "extra1": "hello", "extra2": 42})
            return result
        
        result = asyncio.run(test_kwargs())
        assert result["a"] == 5
        assert set(result["extra_keys"]) == {"extra1", "extra2"}
        assert result["extra_values"]["extra1"] == "hello"
        assert result["extra_values"]["extra2"] == 42
    finally:
        _clear_runtime_context()
    
    # Test 7: Positional-only parameters (Python 3.8+)
    tool_yaml7 = temp_project_dir / "tools" / "positional_only.yml"
    tool_yaml7.write_text("""
mxcp: 1
tool:
  name: positional_only
  description: Test positional-only parameters
  language: python
  source:
    file: ../python/param_mismatch_test.py
  parameters:
    - name: a
      type: integer
      description: First number
    - name: b
      type: integer
      description: Second number
  return:
    type: object
""")
    
    executor7 = EndpointExecutor(
        EndpointType.TOOL,
        "positional_only",
        user_config,
        site_config,
        test_session
    )
    
    # Set runtime context
    _set_runtime_context(test_session, user_config, site_config, {})
    
    try:
        # This should fail because we're passing keyword arguments to positional-only params
        async def test_positional():
            result = await executor7.execute({"a": 10, "b": 3})
            return result
        
        with pytest.raises(TypeError, match="positional-only"):
            asyncio.run(test_positional())
    finally:
        _clear_runtime_context() 