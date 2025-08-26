"""Test for integer parameter conversion bug.

This test specifically reproduces the bug described in the bug report where
JSON float values like 0.0 are not converted to integers before being passed
to Python functions.
"""

import pytest
from mxcp.sdk.executor import ExecutionEngine, ExecutionContext
from mxcp.sdk.executor.plugins.python import PythonExecutor


class TestIntegerConversionBug:
    """Test cases for integer parameter conversion bug."""

    @pytest.mark.asyncio
    async def test_direct_sdk_executor_integer_conversion(self):
        """Test integer conversion directly through SDK executor."""
        
        # Create a Python executor
        python_executor = PythonExecutor()
        
        # Create execution engine
        engine = ExecutionEngine()
        engine.register_executor(python_executor)
        
        # Python function that expects integer
        source_code = '''
def test_function(top_n: int) -> dict:
    """Test function that expects an integer."""
    if not isinstance(top_n, int):
        return {
            "error": f"Expected int, got {type(top_n)}: {top_n}",
            "type_received": str(type(top_n)),
            "test_passed": False
        }
    return {
        "top_n": top_n,
        "type_received": str(type(top_n)),
        "test_passed": True
    }

return test_function(top_n)
'''
        
        # Input schema that specifies integer type
        input_schema = [
            {
                "name": "top_n",
                "type": "integer",
                "description": "Number of items",
                "minimum": 0,
                "default": 0
            }
        ]
        
        # Test with float value 0.0 - this should be converted to int
        context = ExecutionContext()
        params = {"top_n": 0.0}  # JSON would send this as float
        
        try:
            result = await engine.execute(
                language="python",
                source_code=source_code,
                params=params,
                context=context,
                input_schema=input_schema
            )
            
            # Check if conversion worked
            assert result["test_passed"] is True, f"Integer conversion failed: {result.get('error', 'Unknown error')}"
            assert result["type_received"] == "<class 'int'>"
            assert result["top_n"] == 0
            
        finally:
            engine.shutdown()

    @pytest.mark.asyncio
    async def test_sdk_executor_without_schema(self):
        """Test what happens when no input schema is provided."""
        
        # Create a Python executor
        python_executor = PythonExecutor()
        
        # Create execution engine
        engine = ExecutionEngine()
        engine.register_executor(python_executor)
        
        # Python function that expects integer
        source_code = '''
def test_function(top_n: int) -> dict:
    """Test function that expects an integer."""
    return {
        "top_n": top_n,
        "type_received": str(type(top_n)),
        "test_passed": isinstance(top_n, int)
    }

return test_function(top_n)
'''
        
        # Test with float value 0.0 - without schema, this should remain float
        context = ExecutionContext()
        params = {"top_n": 0.0}  # JSON would send this as float
        
        try:
            result = await engine.execute(
                language="python",
                source_code=source_code,
                params=params,
                context=context,
                input_schema=None  # No schema - no conversion
            )
            
            # Without schema, the float should remain as float
            # This would demonstrate the bug if it exists
            print(f"Result without schema: {result}")
            
            # This should fail if no conversion happens
            if not result["test_passed"]:
                print(f"Bug reproduced: {result['type_received']}")
            
        finally:
            engine.shutdown()
