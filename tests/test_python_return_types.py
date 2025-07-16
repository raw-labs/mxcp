"""Tests for Python endpoint return types."""
import pytest
import os
import tempfile
from pathlib import Path
import yaml
import asyncio
from datetime import datetime, date, time
from mxcp.config.user_config import load_user_config
from mxcp.config.site_config import load_site_config
from mxcp.endpoints.sdk_executor import execute_endpoint_with_engine
from mxcp.config.execution_engine import create_execution_engine
from mxcp.endpoints.executor import EndpointExecutor, EndpointType
from mxcp.runtime import _set_runtime_context, _clear_runtime_context


@pytest.fixture
def temp_project_dir():
    """Create a temporary project directory structure."""
    with tempfile.TemporaryDirectory() as tmpdir:
        project_dir = Path(tmpdir)
        
        # Create directory structure
        (project_dir / "tools").mkdir()
        (project_dir / "resources").mkdir()
        (project_dir / "python").mkdir()
        
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
                "python": "python"
            }
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
    """Create execution engine for tests."""
    user_config, site_config = test_configs
    return create_execution_engine(user_config, site_config)


class TestScalarReturnTypes:
    """Test scalar return types (string, number, integer, boolean, datetime)."""
    
    @pytest.mark.asyncio
    async def test_string_return(self, temp_project_dir, test_configs, execution_engine):
        """Test returning a simple string."""
        user_config, site_config = test_configs
        
        # Create Python endpoint
        python_file = temp_project_dir / "python" / "scalar_returns.py"
        python_file.write_text("""
def get_greeting(name: str) -> str:
    return f"Hello, {name}!"
""")
        
        # Create tool definition
        tool_yaml = temp_project_dir / "tools" / "get_greeting.yml"
        tool_yaml.write_text("""
mxcp: 1
tool:
  name: get_greeting
  description: Get a greeting
  language: python
  source:
    file: ../python/scalar_returns.py
  parameters:
    - name: name
      type: string
      description: The name to greet
  return:
    type: string
""")
        
        result = await execute_endpoint_with_engine(
            endpoint_type="tool",
            name="get_greeting",
            params={"name": "World"},
            site_config=site_config,
            execution_engine=execution_engine
        )
        
        assert result == "Hello, World!"
        assert isinstance(result, str)
    
    @pytest.mark.asyncio
    async def test_number_return(self, temp_project_dir, test_configs, execution_engine):
        """Test returning a number (float)."""
        user_config, site_config = test_configs
        
        # Create Python endpoint
        python_file = temp_project_dir / "python" / "number_returns.py"
        python_file.write_text("""
def calculate_pi() -> float:
    return 3.14159
""")
        
        # Create tool definition
        tool_yaml = temp_project_dir / "tools" / "calculate_pi.yml"
        tool_yaml.write_text("""
mxcp: 1
tool:
  name: calculate_pi
  description: Get pi
  language: python
  source:
    file: ../python/number_returns.py
  parameters: []
  return:
    type: number
""")
        
        result = await execute_endpoint_with_engine(
            endpoint_type="tool",
            name="calculate_pi",
            params={},
            site_config=site_config,
            execution_engine=execution_engine
        )
        
        assert result == 3.14159
        assert isinstance(result, float)
    
    @pytest.mark.asyncio
    async def test_integer_return(self, temp_project_dir, test_configs, execution_engine):
        """Test returning an integer."""
        user_config, site_config = test_configs
        
        # Create Python endpoint
        python_file = temp_project_dir / "python" / "integer_returns.py"
        python_file.write_text("""
def count_items() -> int:
    return 42
""")
        
        # Create tool definition
        tool_yaml = temp_project_dir / "tools" / "count_items.yml"
        tool_yaml.write_text("""
mxcp: 1
tool:
  name: count_items
  description: Count items
  language: python
  source:
    file: ../python/integer_returns.py
  parameters: []
  return:
    type: integer
""")
        
        result = await execute_endpoint_with_engine(
            endpoint_type="tool",
            name="count_items",
            params={},
            site_config=site_config,
            execution_engine=execution_engine
        )
        
        assert result == 42
        assert isinstance(result, int)
    
    @pytest.mark.asyncio
    async def test_boolean_return(self, temp_project_dir, test_configs, execution_engine):
        """Test returning a boolean."""
        user_config, site_config = test_configs
        
        # Create Python endpoint
        python_file = temp_project_dir / "python" / "boolean_returns.py"
        python_file.write_text("""
def is_valid() -> bool:
    return True
""")
        
        # Create tool definition
        tool_yaml = temp_project_dir / "tools" / "is_valid.yml"
        tool_yaml.write_text("""
mxcp: 1
tool:
  name: is_valid
  description: Check validity
  language: python
  source:
    file: ../python/boolean_returns.py
  parameters: []
  return:
    type: boolean
""")
        
        result = await execute_endpoint_with_engine(
            endpoint_type="tool",
            name="is_valid",
            params={},
            site_config=site_config,
            execution_engine=execution_engine
        )
        
        assert result is True
        assert isinstance(result, bool)
    
    @pytest.mark.asyncio
    async def test_datetime_return(self, temp_project_dir, test_configs, execution_engine):
        """Test returning datetime values."""
        user_config, site_config = test_configs
        
        # Create Python endpoint
        python_file = temp_project_dir / "python" / "datetime_returns.py"
        python_file.write_text("""
from datetime import datetime, date, time

def get_current_datetime() -> datetime:
    return datetime(2024, 1, 15, 14, 30, 45)

def get_current_date() -> date:
    return date(2024, 1, 15)

def get_current_time() -> time:
    return time(14, 30, 45)
""")
        
        # Test datetime
        tool_yaml = temp_project_dir / "tools" / "get_current_datetime.yml"
        tool_yaml.write_text("""
mxcp: 1
tool:
  name: get_current_datetime
  description: Get datetime
  language: python
  source:
    file: ../python/datetime_returns.py
  parameters: []
  return:
    type: string
    format: date-time
""")
        
        result = await execute_endpoint_with_engine(
            endpoint_type="tool",
            name="get_current_datetime",
            params={},
            site_config=site_config,
            execution_engine=execution_engine
        )
        
        # Should be serialized to ISO format
        assert result == "2024-01-15T14:30:45"
        assert isinstance(result, str)


class TestArrayReturnTypes:
    """Test array return types - currently only supports list of dicts."""
    
    @pytest.mark.asyncio
    async def test_array_of_dicts_works(self, temp_project_dir, test_configs, execution_engine):
        """Test that returning list of dicts works (current behavior)."""
        user_config, site_config = test_configs
        
        # Create Python endpoint
        python_file = temp_project_dir / "python" / "array_returns.py"
        python_file.write_text("""
def get_users() -> list:
    return [
        {"id": 1, "name": "Alice"},
        {"id": 2, "name": "Bob"}
    ]
""")
        
        # Create tool definition
        tool_yaml = temp_project_dir / "tools" / "get_users.yml"
        tool_yaml.write_text("""
mxcp: 1
tool:
  name: get_users
  description: Get users
  language: python
  source:
    file: ../python/array_returns.py
  parameters: []
  return:
    type: array
    items:
      type: object
      properties:
        id:
          type: integer
        name:
          type: string
""")
        
        result = await execute_endpoint_with_engine(
            endpoint_type="tool",
            name="get_users",
            params={},
            site_config=site_config,
            execution_engine=execution_engine
        )
        
        assert result == [
            {"id": 1, "name": "Alice"},
            {"id": 2, "name": "Bob"}
        ]
    
    def test_array_of_numbers(self, temp_project_dir, test_configs, test_session):
        """Test returning list of numbers."""
        user_config, site_config = test_configs
        
        # Create Python endpoint
        python_file = temp_project_dir / "python" / "array_primitives.py"
        python_file.write_text("""
def get_numbers() -> list:
    return [1, 2, 3, 4, 5]
""")
        
        # Create tool definition
        tool_yaml = temp_project_dir / "tools" / "get_numbers.yml"
        tool_yaml.write_text("""
mxcp: 1
tool:
  name: get_numbers
  description: Get numbers
  language: python
  source:
    file: ../python/array_primitives.py
  parameters: []
  return:
    type: array
    items:
      type: integer
""")
        
        _set_runtime_context(test_session, user_config, site_config, {})
        
        try:
            executor = EndpointExecutor(
                EndpointType.TOOL,
                "get_numbers",
                user_config,
                site_config,
                test_session
            )
            
            async def run_test():
                result = await executor.execute({})
                return result
            
            result = asyncio.run(run_test())
            assert result == [1, 2, 3, 4, 5]
            assert isinstance(result, list)
            assert all(isinstance(item, int) for item in result)
            
        finally:
            _clear_runtime_context()
    
    def test_array_of_strings(self, temp_project_dir, test_configs, test_session):
        """Test returning list of strings."""
        user_config, site_config = test_configs
        
        # Create Python endpoint
        python_file = temp_project_dir / "python" / "array_strings.py"
        python_file.write_text("""
def get_tags() -> list:
    return ["python", "testing", "mxcp"]
""")
        
        # Create tool definition
        tool_yaml = temp_project_dir / "tools" / "get_tags.yml"
        tool_yaml.write_text("""
mxcp: 1
tool:
  name: get_tags
  description: Get tags
  language: python
  source:
    file: ../python/array_strings.py
  parameters: []
  return:
    type: array
    items:
      type: string
""")
        
        _set_runtime_context(test_session, user_config, site_config, {})
        
        try:
            executor = EndpointExecutor(
                EndpointType.TOOL,
                "get_tags",
                user_config,
                site_config,
                test_session
            )
            
            async def run_test():
                result = await executor.execute({})
                return result
            
            result = asyncio.run(run_test())
            assert result == ["python", "testing", "mxcp"]
            assert isinstance(result, list)
            assert all(isinstance(item, str) for item in result)
            
        finally:
            _clear_runtime_context()
    
    def test_array_of_booleans(self, temp_project_dir, test_configs, test_session):
        """Test returning list of booleans."""
        user_config, site_config = test_configs
        
        # Create Python endpoint
        python_file = temp_project_dir / "python" / "array_booleans.py"
        python_file.write_text("""
def get_flags() -> list:
    return [True, False, True, True, False]
""")
        
        # Create tool definition
        tool_yaml = temp_project_dir / "tools" / "get_flags.yml"
        tool_yaml.write_text("""
mxcp: 1
tool:
  name: get_flags
  description: Get flags
  language: python
  source:
    file: ../python/array_booleans.py
  parameters: []
  return:
    type: array
    items:
      type: boolean
""")
        
        _set_runtime_context(test_session, user_config, site_config, {})
        
        try:
            executor = EndpointExecutor(
                EndpointType.TOOL,
                "get_flags",
                user_config,
                site_config,
                test_session
            )
            
            async def run_test():
                result = await executor.execute({})
                return result
            
            result = asyncio.run(run_test())
            assert result == [True, False, True, True, False]
            assert isinstance(result, list)
            assert all(isinstance(item, bool) for item in result)
            
        finally:
            _clear_runtime_context()
    
    def test_nested_arrays(self, temp_project_dir, test_configs, test_session):
        """Test returning nested arrays."""
        user_config, site_config = test_configs
        
        # Create Python endpoint
        python_file = temp_project_dir / "python" / "nested_arrays.py"
        python_file.write_text("""
def get_matrix() -> list:
    return [[1, 2, 3], [4, 5, 6], [7, 8, 9]]
""")
        
        # Create tool definition
        tool_yaml = temp_project_dir / "tools" / "get_matrix.yml"
        tool_yaml.write_text("""
mxcp: 1
tool:
  name: get_matrix
  description: Get matrix
  language: python
  source:
    file: ../python/nested_arrays.py
  parameters: []
  return:
    type: array
    items:
      type: array
      items:
        type: integer
""")
        
        _set_runtime_context(test_session, user_config, site_config, {})
        
        try:
            executor = EndpointExecutor(
                EndpointType.TOOL,
                "get_matrix",
                user_config,
                site_config,
                test_session
            )
            
            async def run_test():
                result = await executor.execute({})
                return result
            
            result = asyncio.run(run_test())
            assert result == [[1, 2, 3], [4, 5, 6], [7, 8, 9]]
            assert isinstance(result, list)
            assert all(isinstance(item, list) for item in result)
            
        finally:
            _clear_runtime_context()


class TestObjectReturnTypes:
    """Test object return types."""
    
    def test_simple_object(self, temp_project_dir, test_configs, test_session):
        """Test returning a simple object/dict."""
        user_config, site_config = test_configs
        
        # Create Python endpoint
        python_file = temp_project_dir / "python" / "object_returns.py"
        python_file.write_text("""
def get_user_info() -> dict:
    return {
        "id": 123,
        "name": "Alice",
        "active": True,
        "score": 95.5
    }
""")
        
        # Create tool definition
        tool_yaml = temp_project_dir / "tools" / "get_user_info.yml"
        tool_yaml.write_text("""
mxcp: 1
tool:
  name: get_user_info
  description: Get user info
  language: python
  source:
    file: ../python/object_returns.py
  parameters: []
  return:
    type: object
    properties:
      id:
        type: integer
      name:
        type: string
      active:
        type: boolean
      score:
        type: number
""")
        
        _set_runtime_context(test_session, user_config, site_config, {})
        
        try:
            executor = EndpointExecutor(
                EndpointType.TOOL,
                "get_user_info",
                user_config,
                site_config,
                test_session
            )
            
            async def run_test():
                result = await executor.execute({})
                return result
            
            result = asyncio.run(run_test())
            assert result == {
                "id": 123,
                "name": "Alice",
                "active": True,
                "score": 95.5
            }
            
        finally:
            _clear_runtime_context()
    
    def test_nested_object(self, temp_project_dir, test_configs, test_session):
        """Test returning nested objects."""
        user_config, site_config = test_configs
        
        # Create Python endpoint
        python_file = temp_project_dir / "python" / "nested_objects.py"
        python_file.write_text("""
def get_company_info() -> dict:
    return {
        "name": "Acme Corp",
        "address": {
            "street": "123 Main St",
            "city": "Anytown",
            "zip": "12345"
        },
        "employees": 100
    }
""")
        
        # Create tool definition
        tool_yaml = temp_project_dir / "tools" / "get_company_info.yml"
        tool_yaml.write_text("""
mxcp: 1
tool:
  name: get_company_info
  description: Get company info
  language: python
  source:
    file: ../python/nested_objects.py
  parameters: []
  return:
    type: object
    properties:
      name:
        type: string
      address:
        type: object
        properties:
          street:
            type: string
          city:
            type: string
          zip:
            type: string
      employees:
        type: integer
""")
        
        _set_runtime_context(test_session, user_config, site_config, {})
        
        try:
            executor = EndpointExecutor(
                EndpointType.TOOL,
                "get_company_info",
                user_config,
                site_config,
                test_session
            )
            
            async def run_test():
                result = await executor.execute({})
                return result
            
            result = asyncio.run(run_test())
            assert result == {
                "name": "Acme Corp",
                "address": {
                    "street": "123 Main St",
                    "city": "Anytown",
                    "zip": "12345"
                },
                "employees": 100
            }
            
        finally:
            _clear_runtime_context()


class TestEdgeCases:
    """Test edge cases and error conditions."""
    
    def test_none_return_scalar(self, temp_project_dir, test_configs, test_session):
        """Test returning None for scalar types."""
        user_config, site_config = test_configs
        
        # Create Python endpoint
        python_file = temp_project_dir / "python" / "none_returns.py"
        python_file.write_text("""
def get_nothing() -> None:
    return None
""")
        
        # Create tool definition
        tool_yaml = temp_project_dir / "tools" / "get_nothing.yml"
        tool_yaml.write_text("""
mxcp: 1
tool:
  name: get_nothing
  description: Get nothing
  language: python
  source:
    file: ../python/none_returns.py
  parameters: []
  return:
    type: string
""")
        
        _set_runtime_context(test_session, user_config, site_config, {})
        
        try:
            executor = EndpointExecutor(
                EndpointType.TOOL,
                "get_nothing",
                user_config,
                site_config,
                test_session
            )
            
            async def run_test():
                result = await executor.execute({})
                return result
            
            result = asyncio.run(run_test())
            assert result is None
            
        finally:
            _clear_runtime_context()
    
    def test_empty_list_for_array(self, temp_project_dir, test_configs, test_session):
        """Test returning empty list for array type."""
        user_config, site_config = test_configs
        
        # Create Python endpoint
        python_file = temp_project_dir / "python" / "empty_returns.py"
        python_file.write_text("""
def get_empty_list() -> list:
    return []
""")
        
        # Create tool definition
        tool_yaml = temp_project_dir / "tools" / "get_empty_list.yml"
        tool_yaml.write_text("""
mxcp: 1
tool:
  name: get_empty_list
  description: Get empty list
  language: python
  source:
    file: ../python/empty_returns.py
  parameters: []
  return:
    type: array
    items:
      type: object
""")
        
        _set_runtime_context(test_session, user_config, site_config, {})
        
        try:
            executor = EndpointExecutor(
                EndpointType.TOOL,
                "get_empty_list",
                user_config,
                site_config,
                test_session
            )
            
            async def run_test():
                result = await executor.execute({})
                return result
            
            result = asyncio.run(run_test())
            assert result == []
            
        finally:
            _clear_runtime_context()
    
    def test_wrong_type_for_array(self, temp_project_dir, test_configs, test_session):
        """Test returning wrong type when array is expected."""
        user_config, site_config = test_configs
        
        # Create Python endpoint
        python_file = temp_project_dir / "python" / "wrong_types.py"
        python_file.write_text("""
def get_not_a_list() -> str:
    return "this is not a list"
""")
        
        # Create tool definition
        tool_yaml = temp_project_dir / "tools" / "get_not_a_list.yml"
        tool_yaml.write_text("""
mxcp: 1
tool:
  name: get_not_a_list
  description: Get not a list
  language: python
  source:
    file: ../python/wrong_types.py
  parameters: []
  return:
    type: array
""")
        
        _set_runtime_context(test_session, user_config, site_config, {})
        
        try:
            executor = EndpointExecutor(
                EndpointType.TOOL,
                "get_not_a_list",
                user_config,
                site_config,
                test_session
            )
            
            async def run_test():
                result = await executor.execute({})
                return result
            
            with pytest.raises(ValueError) as exc_info:
                asyncio.run(run_test())
            
            assert "Expected array, got str" in str(exc_info.value)
            
        finally:
            _clear_runtime_context()
    
    def test_wrong_type_for_object(self, temp_project_dir, test_configs, test_session):
        """Test returning wrong type when object is expected."""
        user_config, site_config = test_configs
        
        # Create Python endpoint
        python_file = temp_project_dir / "python" / "wrong_object_types.py"
        python_file.write_text("""
def get_not_an_object() -> list:
    return [1, 2, 3]
""")
        
        # Create tool definition
        tool_yaml = temp_project_dir / "tools" / "get_not_an_object.yml"
        tool_yaml.write_text("""
mxcp: 1
tool:
  name: get_not_an_object
  description: Get not an object
  language: python
  source:
    file: ../python/wrong_object_types.py
  parameters: []
  return:
    type: object
""")
        
        _set_runtime_context(test_session, user_config, site_config, {})
        
        try:
            executor = EndpointExecutor(
                EndpointType.TOOL,
                "get_not_an_object",
                user_config,
                site_config,
                test_session
            )
            
            async def run_test():
                result = await executor.execute({})
                return result
            
            with pytest.raises(ValueError) as exc_info:
                asyncio.run(run_test())
            
            assert "Expected object, got list" in str(exc_info.value)
            
        finally:
            _clear_runtime_context()


class TestMixedContentArrays:
    """Test arrays with mixed content (currently fails)."""
    
    def test_mixed_primitives_in_array(self, temp_project_dir, test_configs, test_session):
        """Test array with mixed primitive types."""
        user_config, site_config = test_configs
        
        # Create Python endpoint
        python_file = temp_project_dir / "python" / "mixed_arrays.py"
        python_file.write_text("""
def get_mixed_data() -> list:
    return [1, "two", 3.0, True, None]
""")
        
        # Create tool definition
        tool_yaml = temp_project_dir / "tools" / "get_mixed_data.yml"
        tool_yaml.write_text("""
mxcp: 1
tool:
  name: get_mixed_data
  description: Get mixed data
  language: python
  source:
    file: ../python/mixed_arrays.py
  parameters: []
  return:
    type: array
""")
        
        _set_runtime_context(test_session, user_config, site_config, {})
        
        try:
            executor = EndpointExecutor(
                EndpointType.TOOL,
                "get_mixed_data",
                user_config,
                site_config,
                test_session
            )
            
            async def run_test():
                result = await executor.execute({})
                return result
            
            result = asyncio.run(run_test())
            assert result == [1, "two", 3.0, True, None]
            assert isinstance(result, list)
            # Check mixed types
            assert isinstance(result[0], int)
            assert isinstance(result[1], str)
            assert isinstance(result[2], float)
            assert isinstance(result[3], bool)
            assert result[4] is None
            
        finally:
            _clear_runtime_context()


class TestValidationFailures:
    """Test validation failures when Python returns data that doesn't match the schema.
    
    Note: TypeConverter is designed to be lenient and will coerce types when possible.
    For example, numbers will be converted to strings, booleans to strings, etc.
    These tests focus on cases where coercion is not possible or where strict
    validation rules (like constraints) are violated.
    """
    
    def test_array_items_wrong_format(self, temp_project_dir, test_configs, test_session):
        """Test array items don't match format constraints."""
        user_config, site_config = test_configs
        
        # Create Python endpoint that returns invalid emails
        python_file = temp_project_dir / "python" / "wrong_array_items.py"
        python_file.write_text("""
def get_invalid_emails() -> list:
    return ["not-an-email", "also-not-email", "definitely@not@email"]
""")
        
        # But declare it as array of emails
        tool_yaml = temp_project_dir / "tools" / "get_invalid_emails.yml"
        tool_yaml.write_text("""
mxcp: 1
tool:
  name: get_invalid_emails
  description: Get invalid emails
  language: python
  source:
    file: ../python/wrong_array_items.py
  parameters: []
  return:
    type: array
    items:
      type: string
      format: email
""")
        
        _set_runtime_context(test_session, user_config, site_config, {})
        
        try:
            executor = EndpointExecutor(
                EndpointType.TOOL,
                "get_invalid_emails",
                user_config,
                site_config,
                test_session
            )
            
            async def run_test():
                result = await executor.execute({})
                return result
            
            # Should fail validation on email format
            with pytest.raises(Exception) as exc_info:
                asyncio.run(run_test())
            
            assert "Invalid email format" in str(exc_info.value)
            
        finally:
            _clear_runtime_context()
    
    def test_object_missing_required_property(self, temp_project_dir, test_configs, test_session):
        """Test object missing required properties."""
        user_config, site_config = test_configs
        
        # Create Python endpoint that returns incomplete object
        python_file = temp_project_dir / "python" / "incomplete_object.py"
        python_file.write_text("""
def get_incomplete_user() -> dict:
    return {
        "id": 123,
        "name": "Alice"
        # Missing required email!
    }
""")
        
        # Declare schema with required email
        tool_yaml = temp_project_dir / "tools" / "get_incomplete_user.yml"
        tool_yaml.write_text("""
mxcp: 1
tool:
  name: get_incomplete_user
  description: Get incomplete user
  language: python
  source:
    file: ../python/incomplete_object.py
  parameters: []
  return:
    type: object
    properties:
      id:
        type: integer
      name:
        type: string
      email:
        type: string
    required: ["id", "name", "email"]
""")
        
        _set_runtime_context(test_session, user_config, site_config, {})
        
        try:
            executor = EndpointExecutor(
                EndpointType.TOOL,
                "get_incomplete_user",
                user_config,
                site_config,
                test_session
            )
            
            async def run_test():
                result = await executor.execute({})
                return result
            
            # Should fail validation
            with pytest.raises(Exception) as exc_info:
                asyncio.run(run_test())
            
            assert "Missing required properties" in str(exc_info.value) or "email" in str(exc_info.value)
            
        finally:
            _clear_runtime_context()
    
    def test_object_property_wrong_type(self, temp_project_dir, test_configs, test_session):
        """Test object property has wrong type."""
        user_config, site_config = test_configs
        
        # Create Python endpoint with wrong property type
        python_file = temp_project_dir / "python" / "wrong_property_type.py"
        python_file.write_text("""
def get_user_wrong_age() -> dict:
    return {
        "id": 123,
        "name": "Alice",
        "age": "thirty"  # String instead of number!
    }
""")
        
        # Declare schema expecting number for age
        tool_yaml = temp_project_dir / "tools" / "get_user_wrong_age.yml"
        tool_yaml.write_text("""
mxcp: 1
tool:
  name: get_user_wrong_age
  description: Get user with wrong age type
  language: python
  source:
    file: ../python/wrong_property_type.py
  parameters: []
  return:
    type: object
    properties:
      id:
        type: integer
      name:
        type: string
      age:
        type: number
""")
        
        _set_runtime_context(test_session, user_config, site_config, {})
        
        try:
            executor = EndpointExecutor(
                EndpointType.TOOL,
                "get_user_wrong_age",
                user_config,
                site_config,
                test_session
            )
            
            async def run_test():
                result = await executor.execute({})
                return result
            
            # Should fail validation
            with pytest.raises(Exception) as exc_info:
                asyncio.run(run_test())
            
            assert "Expected number" in str(exc_info.value) or "SchemaError" in str(exc_info.typename)
            
        finally:
            _clear_runtime_context()
    
    def test_string_too_long(self, temp_project_dir, test_configs, test_session):
        """Test string exceeds maxLength constraint."""
        user_config, site_config = test_configs
        
        # Create Python endpoint with long string
        python_file = temp_project_dir / "python" / "long_string.py"
        python_file.write_text("""
def get_long_name() -> str:
    return "This is a very long name that exceeds the maximum allowed length"
""")
        
        # Declare schema with maxLength constraint
        tool_yaml = temp_project_dir / "tools" / "get_long_name.yml"
        tool_yaml.write_text("""
mxcp: 1
tool:
  name: get_long_name
  description: Get long name
  language: python
  source:
    file: ../python/long_string.py
  parameters: []
  return:
    type: string
    maxLength: 10
""")
        
        _set_runtime_context(test_session, user_config, site_config, {})
        
        try:
            executor = EndpointExecutor(
                EndpointType.TOOL,
                "get_long_name",
                user_config,
                site_config,
                test_session
            )
            
            async def run_test():
                result = await executor.execute({})
                return result
            
            # Should fail validation
            with pytest.raises(Exception) as exc_info:
                asyncio.run(run_test())
            
            assert "must be at most 10 characters" in str(exc_info.value) or "maxLength" in str(exc_info.value)
            
        finally:
            _clear_runtime_context()
    
    def test_number_out_of_range(self, temp_project_dir, test_configs, test_session):
        """Test number outside min/max constraints."""
        user_config, site_config = test_configs
        
        # Create Python endpoint returning large number
        python_file = temp_project_dir / "python" / "big_number.py"
        python_file.write_text("""
def get_score() -> int:
    return 150  # Too high!
""")
        
        # Declare schema with maximum constraint
        tool_yaml = temp_project_dir / "tools" / "get_score.yml"
        tool_yaml.write_text("""
mxcp: 1
tool:
  name: get_score
  description: Get score
  language: python
  source:
    file: ../python/big_number.py
  parameters: []
  return:
    type: integer
    minimum: 0
    maximum: 100
""")
        
        _set_runtime_context(test_session, user_config, site_config, {})
        
        try:
            executor = EndpointExecutor(
                EndpointType.TOOL,
                "get_score",
                user_config,
                site_config,
                test_session
            )
            
            async def run_test():
                result = await executor.execute({})
                return result
            
            # Should fail validation
            with pytest.raises(Exception) as exc_info:
                asyncio.run(run_test())
            
            assert "must be <= 100" in str(exc_info.value) or "maximum" in str(exc_info.value)
            
        finally:
            _clear_runtime_context()
    
    def test_array_too_few_items(self, temp_project_dir, test_configs, test_session):
        """Test array has fewer items than minItems."""
        user_config, site_config = test_configs
        
        # Create Python endpoint with small array
        python_file = temp_project_dir / "python" / "small_array.py"
        python_file.write_text("""
def get_small_list() -> list:
    return [1, 2]  # Only 2 items
""")
        
        # Declare schema requiring at least 5 items
        tool_yaml = temp_project_dir / "tools" / "get_small_list.yml"
        tool_yaml.write_text("""
mxcp: 1
tool:
  name: get_small_list
  description: Get small list
  language: python
  source:
    file: ../python/small_array.py
  parameters: []
  return:
    type: array
    minItems: 5
    items:
      type: integer
""")
        
        _set_runtime_context(test_session, user_config, site_config, {})
        
        try:
            executor = EndpointExecutor(
                EndpointType.TOOL,
                "get_small_list",
                user_config,
                site_config,
                test_session
            )
            
            async def run_test():
                result = await executor.execute({})
                return result
            
            # Should fail validation
            with pytest.raises(Exception) as exc_info:
                asyncio.run(run_test())
            
            assert "must have at least 5 items" in str(exc_info.value) or "minItems" in str(exc_info.value)
            
        finally:
            _clear_runtime_context()
    
    def test_string_wrong_format(self, temp_project_dir, test_configs, test_session):
        """Test string doesn't match format constraint."""
        user_config, site_config = test_configs
        
        # Create Python endpoint with invalid email
        python_file = temp_project_dir / "python" / "bad_email.py"
        python_file.write_text("""
def get_email() -> str:
    return "not-an-email"  # Invalid email format
""")
        
        # Declare schema expecting email format
        tool_yaml = temp_project_dir / "tools" / "get_email.yml"
        tool_yaml.write_text("""
mxcp: 1
tool:
  name: get_email
  description: Get email
  language: python
  source:
    file: ../python/bad_email.py
  parameters: []
  return:
    type: string
    format: email
""")
        
        _set_runtime_context(test_session, user_config, site_config, {})
        
        try:
            executor = EndpointExecutor(
                EndpointType.TOOL,
                "get_email",
                user_config,
                site_config,
                test_session
            )
            
            async def run_test():
                result = await executor.execute({})
                return result
            
            # Should fail validation
            with pytest.raises(Exception) as exc_info:
                asyncio.run(run_test())
            
            assert "Invalid email format" in str(exc_info.value) or "format" in str(exc_info.value)
            
        finally:
            _clear_runtime_context() 