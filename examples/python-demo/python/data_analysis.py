"""
Example Python endpoints for data analysis.
"""

import statistics
from datetime import datetime, timedelta

from mxcp.runtime import config, db


def analyze_numbers(numbers: list, operation: str = "mean") -> dict:
    """
    Analyze a list of numbers with various statistical operations.
    """
    if not numbers:
        return {"error": "No numbers provided"}

    operations = {
        "mean": statistics.mean,
        "median": statistics.median,
        "mode": statistics.mode,
        "stdev": statistics.stdev if len(numbers) > 1 else lambda x: 0,
        "sum": sum,
        "min": min,
        "max": max,
    }

    if operation not in operations:
        return {"error": f"Unknown operation: {operation}"}

    try:
        result = operations[operation](numbers)
        return {"operation": operation, "result": result, "count": len(numbers)}
    except Exception as e:
        return {"error": str(e)}


def create_sample_data(table_name: str, row_count: int) -> dict:
    """
    Create a sample table with test data.
    """
    try:
        # Drop table if exists
        db.execute(f"DROP TABLE IF EXISTS {table_name}")

        # Create table
        db.execute(
            f"""
            CREATE TABLE {table_name} (
                id INTEGER PRIMARY KEY,
                name VARCHAR,
                value DOUBLE,
                category VARCHAR,
                created_at TIMESTAMP
            )
        """
        )

        # Insert sample data
        for i in range(row_count):
            db.execute(
                f"""
                INSERT INTO {table_name} (id, name, value, category, created_at)
                VALUES (
                    $id,
                    'Item ' || $item_num,
                    ROUND(RANDOM() * 1000, 2),
                    CASE 
                        WHEN RANDOM() < 0.33 THEN 'A'
                        WHEN RANDOM() < 0.66 THEN 'B'
                        ELSE 'C'
                    END,
                    CURRENT_TIMESTAMP - INTERVAL ($days || ' days')
                )
            """,
                {"id": i + 1, "item_num": i + 1, "days": i % 30},
            )

        return {"status": "success", "table": table_name, "rows_created": row_count}
    except Exception as e:
        return {"status": "error", "error": str(e)}


def aggregate_by_category(table_name: str) -> list:
    """
    Aggregate data by category from a table.
    """
    try:
        results = db.execute(
            f"""
            SELECT 
                category,
                COUNT(*) as count,
                ROUND(AVG(value), 2) as avg_value,
                ROUND(SUM(value), 2) as total_value,
                MIN(value) as min_value,
                MAX(value) as max_value
            FROM {table_name}
            GROUP BY category
            ORDER BY category
        """
        )

        return results
    except Exception as e:
        return [{"error": str(e)}]


async def process_time_series(table_name: str, window_days: int = 7) -> list:
    """
    Async function to process time series data with rolling windows.
    """
    import asyncio

    # Simulate some async processing
    await asyncio.sleep(0.1)

    results = db.execute(
        f"""
        WITH daily_data AS (
            SELECT 
                DATE_TRUNC('day', created_at) as date,
                category,
                COUNT(*) as daily_count,
                ROUND(AVG(value), 2) as daily_avg
            FROM {table_name}
            GROUP BY DATE_TRUNC('day', created_at), category
        )
        SELECT 
            date,
            category,
            daily_count,
            daily_avg,
            ROUND(AVG(daily_avg) OVER (
                PARTITION BY category 
                ORDER BY date 
                ROWS BETWEEN {window_days - 1} PRECEDING AND CURRENT ROW
            ), 2) as rolling_avg
        FROM daily_data
        ORDER BY date DESC, category
        LIMIT 50
    """
    )

    return results
