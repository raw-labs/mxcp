import pytest
import duckdb
from typing import Dict, Any, List, TypedDict
from mxcp.plugins import MXCPBasePlugin, udf
import base64
from datetime import date, time, datetime, timedelta


class MyStruct(TypedDict):
    name: str
    value: int


class PluginImpl(MXCPBasePlugin):
    """A test plugin that implements simple operations for all supported types."""

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)

    # Primitive types
    @udf
    def add_ints(self, a: int, b: int) -> int:
        return a + b

    @udf
    def add_floats(self, a: float, b: float) -> float:
        return a + b

    @udf
    def not_bool(self, b: bool) -> bool:
        return not b

    @udf
    def echo_str(self, s: str) -> str:
        return s

    @udf
    def b64encode_bytes(self, b: bytes) -> str:
        return base64.b64encode(b).decode("ascii")

    # Date/Time types
    @udf
    def add_days(self, d: date, days: int) -> date:
        return d + timedelta(days=days)

    @udf
    def add_hours(self, t: time, hours: int) -> time:
        # Convert to datetime for easier arithmetic
        dt = datetime.combine(date.today(), t)
        result = dt + timedelta(hours=hours)
        return result.time()

    @udf
    def add_days_to_datetime(self, dt: datetime, days: int) -> datetime:
        return dt + timedelta(days=days)

    # List
    @udf
    def sum_list(self, nums: list[int]) -> int:
        return sum(nums)

    # Map
    @udf
    def sum_map(self, d: dict[str, int]) -> int:
        return sum(d.values())

    # Struct
    @udf
    def struct_to_str(self, s: MyStruct) -> str:
        return f"{s['name']}={s['value']}"

    # Previous UDFs
    @udf
    def reverse(self, text: str) -> str:
        return text[::-1]

    @udf
    def repeat(self, text: str, times: int) -> str:
        return text * times

    def get_class_name(self, obj: Any) -> str:
        return obj.__class__.__name__

    @udf
    def return_my_struct(self) -> MyStruct:
        return {"name": "test", "value": 42}


@pytest.fixture
def db_connection():
    """Create a DuckDB connection for testing."""
    conn = duckdb.connect(":memory:")
    yield conn
    conn.close()


@pytest.fixture
def registered_udfs(db_connection):
    """Register all UDFs from the test plugin, postfixing names with _udf."""
    plugin = PluginImpl({})
    udfs = plugin.udfs()
    assert len(udfs) == 14, "Should have 14 UDFs (all types)"
    for udf_def in udfs:
        try:
            db_connection.create_function(
                udf_def["name"] + "_udf", udf_def["method"], udf_def["args"], udf_def["return_type"]
            )
        except Exception as e:
            raise ValueError(
                f"Failed to register UDF '{udf_def['name']}' with args {udf_def['args']} and return {udf_def['return_type']}: {e}"
            )
    return db_connection


def test_add_ints_udf(registered_udfs):
    assert registered_udfs.execute("SELECT add_ints_udf(2, 3)").fetchone()[0] == 5


def test_add_floats_udf(registered_udfs):
    assert registered_udfs.execute("SELECT add_floats_udf(1.0, 2.0)").fetchone()[0] == 3.0


def test_not_bool_udf(registered_udfs):
    assert registered_udfs.execute("SELECT not_bool_udf(TRUE)").fetchone()[0] is False
    assert registered_udfs.execute("SELECT not_bool_udf(FALSE)").fetchone()[0] is True


def test_echo_str_udf(registered_udfs):
    assert registered_udfs.execute("SELECT echo_str_udf('hello')").fetchone()[0] == "hello"


def test_b64encode_bytes_udf(registered_udfs):
    result = registered_udfs.execute("SELECT b64encode_bytes_udf(encode('hello'))").fetchone()[0]
    assert result == "aGVsbG8="  # base64 for 'hello'


def test_sum_list_udf(registered_udfs):
    assert registered_udfs.execute("SELECT sum_list_udf([1,2,3,4])").fetchone()[0] == 10


def test_sum_map_udf(registered_udfs):
    assert (
        registered_udfs.execute("SELECT sum_map_udf(map(['a','b'], [10, 20]))").fetchone()[0] == 30
    )


def test_struct_to_str_udf(registered_udfs):
    # DuckDB struct syntax: {'name': 'foo', 'value': 42}
    assert (
        registered_udfs.execute(
            "SELECT struct_to_str_udf({'name': 'foo', 'value': 42})"
        ).fetchone()[0]
        == "foo=42"
    )


def test_reverse_udf(registered_udfs):
    """Test the reverse_udf UDF."""
    result = registered_udfs.execute("SELECT reverse_udf('hello')").fetchone()[0]
    assert result == "olleh"

    # Test with empty string
    result = registered_udfs.execute("SELECT reverse_udf('')").fetchone()[0]
    assert result == ""

    # Test with palindrome
    result = registered_udfs.execute("SELECT reverse_udf('radar')").fetchone()[0]
    assert result == "radar"


def test_repeat_udf(registered_udfs):
    """Test the repeat_udf UDF."""
    result = registered_udfs.execute("SELECT repeat_udf('ha', 3)").fetchone()[0]
    assert result == "hahaha"

    # Test with zero repetitions
    result = registered_udfs.execute("SELECT repeat_udf('ha', 0)").fetchone()[0]
    assert result == ""

    # Test with single repetition
    result = registered_udfs.execute("SELECT repeat_udf('ha', 1)").fetchone()[0]
    assert result == "ha"


@pytest.mark.skip(reason="Test disabled - needs support for ANY type")
def test_get_class_name_udf(registered_udfs):
    # Test with string
    result = registered_udfs.execute("SELECT get_class_name_udf('hello')").fetchone()[0]
    assert result == "str"

    # Test with integer
    result = registered_udfs.execute("SELECT get_class_name_udf(42)").fetchone()[0]
    assert result == "int"

    # Test with decimal
    result = registered_udfs.execute("SELECT get_class_name_udf(3.14)").fetchone()[0]
    assert result == "Decimal"

    # Test with boolean
    result = registered_udfs.execute("SELECT get_class_name_udf(TRUE)").fetchone()[0]
    assert result == "bool"

    # Test with list
    result = registered_udfs.execute("SELECT get_class_name_udf([1, 2, 3])").fetchone()[0]
    assert result == "list"

    # Test with map
    result = registered_udfs.execute("SELECT get_class_name_udf(map(['a'], [1]))").fetchone()[0]
    assert result == "dict"

    # Test with struct
    result = registered_udfs.execute(
        "SELECT get_class_name_udf({'name': 'foo', 'value': 42})"
    ).fetchone()[0]
    assert result == "dict"


def test_return_my_struct_udf(registered_udfs):
    result = registered_udfs.execute("SELECT return_my_struct_udf()").fetchone()[0]
    assert result == {"name": "test", "value": 42}


def test_add_days_udf(registered_udfs):
    """Test the add_days_udf UDF."""
    # Test adding days to a date
    result = registered_udfs.execute("SELECT add_days_udf(DATE '2024-03-20', 5)").fetchone()[0]
    assert result == date(2024, 3, 25)

    # Test adding days across month boundary
    result = registered_udfs.execute("SELECT add_days_udf(DATE '2024-03-30', 5)").fetchone()[0]
    assert result == date(2024, 4, 4)


def test_add_hours_udf(registered_udfs):
    """Test the add_hours_udf UDF."""
    # Test adding hours within same day
    result = registered_udfs.execute("SELECT add_hours_udf(TIME '14:30:00', 2)").fetchone()[0]
    assert result == time(16, 30, 0)

    # Test adding hours across midnight
    result = registered_udfs.execute("SELECT add_hours_udf(TIME '23:30:00', 2)").fetchone()[0]
    assert result == time(1, 30, 0)


def test_add_days_to_datetime_udf(registered_udfs):
    """Test the add_days_to_datetime_udf UDF."""
    # Test adding days to a datetime
    result = registered_udfs.execute(
        "SELECT add_days_to_datetime_udf(TIMESTAMP '2024-03-20 14:30:00', 5)"
    ).fetchone()[0]
    assert result == datetime(2024, 3, 25, 14, 30, 0)

    # Test adding days across month boundary
    result = registered_udfs.execute(
        "SELECT add_days_to_datetime_udf(TIMESTAMP '2024-03-30 23:59:59', 5)"
    ).fetchone()[0]
    assert result == datetime(2024, 4, 4, 23, 59, 59)
