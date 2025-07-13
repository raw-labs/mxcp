"""Test validator using fixtures from the fixtures directory."""

import pytest
from pathlib import Path
from mxcp.validator import validate, TypeValidator, ValidationError, load_schema_from_file


class TestFixtures:
    """Test validator with fixture files."""
    
    def test_calculator_schema_from_fixture(self):
        """Test loading and using calculator schema from fixtures."""
        # Get the fixture path
        fixture_path = Path(__file__).parent.parent / "fixtures" / "validator" / "schemas" / "calculator.yaml"
        
        @validate.from_file(str(fixture_path))
        def calculate(a: float, b: float, operation: str) -> dict:
            if operation == "add":
                result = a + b
            elif operation == "subtract":
                result = a - b
            elif operation == "multiply":
                result = a * b
            elif operation == "divide":
                result = a / b
            else:
                raise ValueError(f"Unknown operation: {operation}")
            
            return {"result": result, "operation": operation}
        
        # Test valid inputs
        output = calculate(5.5, 2.5, "add")
        assert output["result"] == 8.0
        assert output["operation"] == "add"
        
        # Test type conversion
        output = calculate("10", "5", "multiply")  # type: ignore
        assert output["result"] == 50.0
        
        # Test invalid operation
        with pytest.raises(ValidationError, match="Must be one of"):
            calculate(10, 5, "modulo")
        

    def test_schema_file_validation(self):
        """Test direct schema loading from file."""
        schema_path = Path(__file__).parent.parent / "fixtures" / "validator" / "schemas" / "calculator.yaml"
        
        # Load and create validator
        schema = load_schema_from_file(str(schema_path))
        validator = TypeValidator.from_dict(schema)
        
        # Test input validation
        result = validator.validate_input({"a": 10, "b": 20, "operation": "add"})
        assert result["a"] == 10.0
        assert result["b"] == 20.0
        assert result["operation"] == "add"
        
        # Test output validation
        output = validator.validate_output({"result": 30.0, "operation": "add"})
        assert output["result"] == 30.0
        assert output["operation"] == "add"
        
        # Test invalid output type
        with pytest.raises(ValidationError, match="Expected object"):
            validator.validate_output("thirty")
            
        # Test missing required field
        with pytest.raises(ValidationError, match="Missing required properties"):
            validator.validate_output({"result": 30.0})  # Missing operation 