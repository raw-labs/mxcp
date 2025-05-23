import pytest
from raw.endpoints.executor import TypeConverter
from datetime import datetime, date, time

def test_string_formats():
    """Test string format conversions"""
    # Email format
    assert TypeConverter.convert_value("test@example.com", {"type": "string", "format": "email"}) == "test@example.com"
    with pytest.raises(ValueError):
        TypeConverter.convert_value("invalid-email", {"type": "string", "format": "email"})
    
    # URI format
    assert TypeConverter.convert_value("https://example.com", {"type": "string", "format": "uri"}) == "https://example.com"
    with pytest.raises(ValueError):
        TypeConverter.convert_value("not-a-uri", {"type": "string", "format": "uri"})
    
    # Duration format
    assert TypeConverter.convert_value("P1DT2H", {"type": "string", "format": "duration"}) == "P1DT2H"
    with pytest.raises(ValueError):
        TypeConverter.convert_value("invalid-duration", {"type": "string", "format": "duration"})
    
    # Timestamp format
    timestamp = "1672531199"
    result = TypeConverter.convert_value(timestamp, {"type": "string", "format": "timestamp"})
    assert isinstance(result, datetime)
    with pytest.raises(ValueError):
        TypeConverter.convert_value("invalid-timestamp", {"type": "string", "format": "timestamp"})

def test_numeric_constraints():
    """Test numeric type constraints"""
    # Number constraints
    param_def = {
        "type": "number",
        "minimum": 0,
        "maximum": 100,
        "exclusiveMinimum": -1,
        "exclusiveMaximum": 101,
        "multipleOf": 0.5
    }
    assert TypeConverter.convert_value("50.0", param_def) == 50.0
    assert TypeConverter.convert_value("0.5", param_def) == 0.5
    with pytest.raises(ValueError):
        TypeConverter.convert_value("-1", param_def)  # Below minimum
    with pytest.raises(ValueError):
        TypeConverter.convert_value("101", param_def)  # Above maximum
    with pytest.raises(ValueError):
        TypeConverter.convert_value("0.3", param_def)  # Not multiple of 0.5
    with pytest.raises(ValueError):
        TypeConverter.convert_value("-1", {**param_def, "exclusiveMinimum": 0})  # Not greater than exclusiveMinimum
    with pytest.raises(ValueError):
        TypeConverter.convert_value("101", {**param_def, "exclusiveMaximum": 100})  # Not less than exclusiveMaximum
    
    # Integer constraints
    param_def = {
        "type": "integer",
        "minimum": 0,
        "maximum": 100,
        "exclusiveMinimum": -1,
        "exclusiveMaximum": 101,
        "multipleOf": 2
    }
    assert TypeConverter.convert_value("50", param_def) == 50
    with pytest.raises(ValueError):
        TypeConverter.convert_value("-1", param_def)  # Below minimum
    with pytest.raises(ValueError):
        TypeConverter.convert_value("101", param_def)  # Above maximum
    with pytest.raises(ValueError):
        TypeConverter.convert_value("3", param_def)  # Not multiple of 2
    with pytest.raises(ValueError):
        TypeConverter.convert_value("-1", {**param_def, "exclusiveMinimum": 0})  # Not greater than exclusiveMinimum
    with pytest.raises(ValueError):
        TypeConverter.convert_value("101", {**param_def, "exclusiveMaximum": 100})  # Not less than exclusiveMaximum

def test_string_constraints():
    """Test string type constraints"""
    param_def = {
        "type": "string",
        "minLength": 2,
        "maxLength": 5
    }
    
    # Valid string
    assert TypeConverter.convert_value("abc", param_def) == "abc"
    
    # Too short
    with pytest.raises(ValueError):
        TypeConverter.convert_value("a", param_def)
    
    # Too long
    with pytest.raises(ValueError):
        TypeConverter.convert_value("abcdef", param_def)

def test_string_format():
    """Test string format validation"""
    # Email format
    param_def = {
        "type": "string",
        "format": "email"
    }
    assert TypeConverter.convert_value("user@example.com", param_def) == "user@example.com"
    with pytest.raises(ValueError):
        TypeConverter.convert_value("invalid-email", param_def)
    
    # URI format
    param_def = {
        "type": "string",
        "format": "uri"
    }
    assert TypeConverter.convert_value("https://example.com", param_def) == "https://example.com"
    with pytest.raises(ValueError):
        TypeConverter.convert_value("not-a-uri", param_def)
    
    # Date format
    param_def = {
        "type": "string",
        "format": "date"
    }
    result = TypeConverter.convert_value("2024-03-20", param_def)
    assert isinstance(result, date)
    assert result.year == 2024
    assert result.month == 3
    assert result.day == 20
    with pytest.raises(ValueError):
        TypeConverter.convert_value("invalid-date", param_def)
    
    # Time format
    param_def = {
        "type": "string",
        "format": "time"
    }
    result = TypeConverter.convert_value("14:30:00", param_def)
    assert isinstance(result, time)
    assert result.hour == 14
    assert result.minute == 30
    assert result.second == 0
    with pytest.raises(ValueError):
        TypeConverter.convert_value("invalid-time", param_def)
    
    # Date-time format
    param_def = {
        "type": "string",
        "format": "date-time"
    }
    result = TypeConverter.convert_value("2024-03-20T14:30:00Z", param_def)
    assert isinstance(result, datetime)
    assert result.year == 2024
    assert result.month == 3
    assert result.day == 20
    assert result.hour == 14
    assert result.minute == 30
    assert result.second == 0
    with pytest.raises(ValueError):
        TypeConverter.convert_value("invalid-datetime", param_def)
    
    # Duration format
    param_def = {
        "type": "string",
        "format": "duration"
    }
    assert TypeConverter.convert_value("P1DT2H3M4S", param_def) == "P1DT2H3M4S"
    with pytest.raises(ValueError):
        TypeConverter.convert_value("invalid-duration", param_def)
    
    # Timestamp format
    param_def = {
        "type": "string",
        "format": "timestamp"
    }
    # Use a Unix timestamp (seconds since epoch)
    result = TypeConverter.convert_value("1672531199", param_def)
    assert isinstance(result, datetime)
    assert result.year == 2023
    assert result.month == 1
    assert result.day == 1
    with pytest.raises(ValueError):
        TypeConverter.convert_value("invalid-timestamp", param_def)

def test_array_constraints():
    """Test array type constraints"""
    param_def = {
        "type": "array",
        "minItems": 2,
        "maxItems": 4,
        "uniqueItems": True,
        "items": {"type": "string"}
    }
    
    # Valid array
    assert TypeConverter.convert_value(["a", "b"], param_def) == ["a", "b"]
    
    # Too few items
    with pytest.raises(ValueError):
        TypeConverter.convert_value(["a"], param_def)
    
    # Too many items
    with pytest.raises(ValueError):
        TypeConverter.convert_value(["a", "b", "c", "d", "e"], param_def)
    
    # Non-unique items
    with pytest.raises(ValueError):
        TypeConverter.convert_value(["a", "a"], param_def)
    
    # JSON string input
    assert TypeConverter.convert_value('["a", "b"]', param_def) == ["a", "b"]
    with pytest.raises(ValueError):
        TypeConverter.convert_value("invalid-json", param_def)
    
    # Test uniqueItems: False (should allow duplicates)
    param_def_no_unique = {
        "type": "array",
        "minItems": 1,
        "maxItems": 3,
        "uniqueItems": False,
        "items": {"type": "string"}
    }
    assert TypeConverter.convert_value(["a", "a"], param_def_no_unique) == ["a", "a"]

def test_object_constraints():
    """Test object type constraints"""
    param_def = {
        "type": "object",
        "required": ["name", "age"],
        "properties": {
            "name": {"type": "string"},
            "age": {"type": "integer"},
            "email": {"type": "string", "format": "email"}
        },
        "additionalProperties": False
    }
    
    # Valid object
    valid_obj = {"name": "John", "age": 30, "email": "john@example.com"}
    assert TypeConverter.convert_value(valid_obj, param_def) == valid_obj
    
    # Missing required property
    with pytest.raises(ValueError):
        TypeConverter.convert_value({"name": "John"}, param_def)
    
    # Invalid property type
    with pytest.raises(ValueError):
        TypeConverter.convert_value({"name": "John", "age": "not-a-number"}, param_def)
    
    # Invalid email format
    with pytest.raises(ValueError):
        TypeConverter.convert_value({"name": "John", "age": 30, "email": "invalid-email"}, param_def)
    
    # Unexpected property
    with pytest.raises(ValueError):
        TypeConverter.convert_value({"name": "John", "age": 30, "extra": "value"}, param_def)
    
    # JSON string input
    json_str = '{"name": "John", "age": 30, "email": "john@example.com"}'
    assert TypeConverter.convert_value(json_str, param_def) == valid_obj
    with pytest.raises(ValueError):
        TypeConverter.convert_value("invalid-json", param_def)

def test_boolean_conversion():
    """Test boolean type conversion"""
    assert TypeConverter.convert_value("true", {"type": "boolean"}) is True
    assert TypeConverter.convert_value("false", {"type": "boolean"}) is False
    assert TypeConverter.convert_value(True, {"type": "boolean"}) is True
    assert TypeConverter.convert_value(False, {"type": "boolean"}) is False
    assert TypeConverter.convert_value(1, {"type": "boolean"}) is True
    assert TypeConverter.convert_value(0, {"type": "boolean"}) is False 