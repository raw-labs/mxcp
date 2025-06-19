import pytest
import duckdb
import pandas as pd
from pandas import NaT, Timestamp
import numpy as np
from datetime import datetime
from typing import Dict, Any, List
from mxcp.engine.duckdb_session import execute_query_to_dict


def test_nat_handling_with_actual_nat_values():
    """Test execute_query_to_dict with actual NaT values to understand the real requirements."""
    
    # Create test database with datetime data including NaT
    conn = duckdb.connect(":memory:")
    
    # Create table with timestamp column
    conn.execute("CREATE TABLE test_timestamps (id INTEGER, created_at TIMESTAMP, name VARCHAR)")
    
    # Insert data including NULL timestamps (which become NaT in pandas)
    conn.execute("""
        INSERT INTO test_timestamps VALUES 
        (1, '2023-01-01 10:00:00', 'Alice'),
        (2, NULL, 'Bob'),
        (3, '2023-01-03 12:00:00', 'Charlie')
    """)
    
    # Test 1: Direct pandas DataFrame behavior
    print("=== Test 1: Direct DataFrame from DuckDB ===")
    df = conn.execute("SELECT * FROM test_timestamps").fetchdf()
    print(f"DataFrame:\n{df}")
    print(f"DataFrame dtypes:\n{df.dtypes}")
    print(f"NaT values present: {df.isnull().any().any()}")
    
    # Check what's actually in the DataFrame
    for i, row in df.iterrows():
        for col, val in row.items():
            if pd.isna(val):
                print(f"Row {i}, Column {col}: {val} (type: {type(val)})")
    
    # Test 2: Original problematic approach
    print(f"\n=== Test 2: Original approach ===")
    try:
        original_result = df.replace({NaT: None}).to_dict("records")
        print(f"Original approach result: {original_result}")
        print(f"Length: {len(original_result)}")
        
        # Check if any NaT values remain
        for i, record in enumerate(original_result):
            for key, val in record.items():
                if str(type(val)) == "<class 'pandas._libs.tslibs.nattype.NaTType'>":
                    print(f"Record {i}, Key {key}: Still has NaT! {val}")
    except Exception as e:
        print(f"Original approach failed: {e}")
    
    # Test 3: Simple fillna approach
    print(f"\n=== Test 3: Simple fillna approach ===")
    try:
        fillna_result = df.fillna(None).to_dict("records")
        print(f"fillna approach result: {fillna_result}")
        print(f"Length: {len(fillna_result)}")
    except Exception as e:
        print(f"fillna approach failed: {e}")
    
    # Test 4: Using current execute_query_to_dict
    print(f"\n=== Test 4: Current execute_query_to_dict ===")
    try:
        current_result = execute_query_to_dict(conn, "SELECT * FROM test_timestamps")
        print(f"Current execute_query_to_dict result: {current_result}")
        print(f"Length: {len(current_result)}")
    except Exception as e:
        print(f"Current execute_query_to_dict failed: {e}")
    
    conn.close()


def test_simple_alternatives():
    """Test simpler alternatives to the complex NaT replacement."""
    
    conn = duckdb.connect(":memory:")
    
    # Test with regular data (no NaT)
    conn.execute("CREATE TABLE test_simple (id INTEGER, name VARCHAR)")
    conn.execute("INSERT INTO test_simple VALUES (1, 'Alice'), (2, 'Bob')")
    
    print("=== Testing with simple data (no NaT) ===")
    
    # Alternative 1: No replace at all
    def simple_no_replace(conn, query, params=None):
        return conn.execute(query, params).fetchdf().to_dict("records")
    
    # Alternative 2: where/notnull instead of replace
    def simple_fillna(conn, query, params=None):
        df = conn.execute(query, params).fetchdf()
        return df.where(pd.notnull(df), None).to_dict("records")
    
    # Alternative 3: replace with broader catch
    def simple_replace_nan(conn, query, params=None):
        df = conn.execute(query, params).fetchdf()
        return df.replace({pd.NaT: None, np.nan: None}).to_dict("records")
    
    # Test all alternatives
    query = "SELECT * FROM test_simple"
    
    result1 = simple_no_replace(conn, query)
    print(f"No replace: {result1}")
    
    result2 = simple_fillna(conn, query)
    print(f"where/notnull: {result2}")
    
    result3 = simple_replace_nan(conn, query)
    print(f"replace NaT+NaN: {result3}")
    
    # All should be identical for simple data
    assert result1 == result2 == result3
    assert len(result1) == 2
    
    conn.close()


def test_datetime_edge_cases():
    """Test various datetime edge cases to understand when NaT issues occur."""
    
    conn = duckdb.connect(":memory:")
    
    # Create table with various timestamp scenarios
    conn.execute("""
        CREATE TABLE test_datetime_edge_cases (
            id INTEGER,
            ts_null TIMESTAMP,
            ts_valid TIMESTAMP,
            ts_string VARCHAR
        )
    """)
    
    conn.execute("""
        INSERT INTO test_datetime_edge_cases VALUES 
        (1, NULL, '2023-01-01 10:00:00', '2023-01-01'),
        (2, NULL, '1970-01-01 00:00:00', 'invalid-date'),
        (3, NULL, '2099-12-31 23:59:59', NULL)
    """)
    
    print("=== Testing datetime edge cases ===")
    
    # Test what DuckDB returns
    df = conn.execute("SELECT * FROM test_datetime_edge_cases").fetchdf()
    print(f"DataFrame:\n{df}")
    print(f"DataFrame dtypes:\n{df.dtypes}")
    
    # Test different replacement strategies
    print(f"\nOriginal replace: {df.replace({NaT: None}).to_dict('records')}")
    print(f"where/notnull: {df.where(pd.notnull(df), None).to_dict('records')}")
    
    conn.close()


def test_reproduce_actual_empty_results_bug():
    """Try to reproduce the actual empty results bug without mocking."""
    
    conn = duckdb.connect(":memory:")
    conn.execute("CREATE TABLE test_minimal (id INTEGER, name VARCHAR)")
    conn.execute("INSERT INTO test_minimal VALUES (1, 'Alice'), (2, 'Bob')")
    
    print("=== Trying to reproduce actual empty results bug ===")
    
    # Test the exact original implementation
    def original_implementation(conn, query, params=None):
        return conn.execute(query, params).fetchdf().replace({NaT: None}).to_dict("records")
    
    # Test various scenarios that might trigger the bug
    scenarios = [
        "SELECT * FROM test_minimal",
        "SELECT id, name FROM test_minimal WHERE id > 0",
        "SELECT COUNT(*) as count FROM test_minimal",
        "SELECT 'test' as message, 42 as number",
    ]
    
    for scenario in scenarios:
        print(f"\nTesting: {scenario}")
        try:
            result = original_implementation(conn, scenario)
            print(f"  Result: {result}")
            print(f"  Length: {len(result)}")
            
            if len(result) == 0:
                print(f"  *** FOUND EMPTY RESULTS BUG WITH: {scenario} ***")
            
        except Exception as e:
            print(f"  Error: {e}")
    
    conn.close()


def test_nat_replacement_functionality():
    """Test that NaT values are properly replaced with None for JSON serialization."""
    
    conn = duckdb.connect(":memory:")
    conn.execute("CREATE TABLE test_timestamps (id INTEGER, created_at TIMESTAMP, name VARCHAR)")
    conn.execute("""
        INSERT INTO test_timestamps VALUES 
        (1, '2023-01-01 10:00:00', 'Alice'),
        (2, NULL, 'Bob'),
        (3, '2023-01-03 12:00:00', 'Charlie')
    """)
    
    # Test that NaT values are converted to None
    result = execute_query_to_dict(conn, "SELECT * FROM test_timestamps")
    
    assert len(result) == 3
    assert result[0]['created_at'] is not None  # Should be a Timestamp
    assert result[1]['created_at'] is None      # Should be None (was NaT)
    assert result[2]['created_at'] is not None  # Should be a Timestamp
    
    # Ensure no NaT values remain in the result
    for record in result:
        for value in record.values():
            assert str(type(value)) != "<class 'pandas._libs.tslibs.nattype.NaTType'>", f"NaT found: {value}"
    
    conn.close()


if __name__ == "__main__":
    test_nat_handling_with_actual_nat_values()
    print("\n" + "="*80 + "\n")
    test_simple_alternatives()
    print("\n" + "="*80 + "\n") 
    test_datetime_edge_cases()
    print("\n" + "="*80 + "\n")
    test_reproduce_actual_empty_results_bug() 