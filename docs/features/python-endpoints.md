# Python Endpoints

MXCP supports Python-based endpoints alongside SQL endpoints, allowing you to implement more complex logic while still leveraging the MXCP infrastructure.

## Overview

Python endpoints enable you to:
- Write complex business logic that would be difficult in SQL
- Integrate with external APIs and services
- Process data with Python libraries
- Access the DuckDB database from Python code
- Share code between endpoints through modules

## Creating Python Endpoints

### Basic Example

1. Create a Python file in the `python/` directory:

```python
# python/customer_tools.py
from mxcp.runtime import db

def get_customer_summary(customer_id: int) -> dict:
    """Get a summary of customer information."""
    # Query the database
    customers = db.execute(
        "SELECT * FROM customers WHERE id = ?",
        {"customer_id": customer_id}
    )
    
    if not customers:
        return {"error": "Customer not found"}
    
    customer = customers[0]
    
    # Get order count
    orders = db.execute(
        "SELECT COUNT(*) as count FROM orders WHERE customer_id = ?",
        {"customer_id": customer_id}
    )
    
    return {
        "id": customer["id"],
        "name": customer["name"],
        "email": customer["email"],
        "order_count": orders[0]["count"]
    }
```

2. Create a tool definition that references the Python file:

```yaml
# tools/get_customer_summary.yml
mxcp: "1.0"
tool:
  name: get_customer_summary
  description: Get customer summary including order count
  language: python  # Specify Python language
  source:
    file: ../python/customer_tools.py
  parameters:
    - name: customer_id
      type: integer
      description: Customer ID
  return:
    type: object
    properties:
      id:
        type: integer
      name:
        type: string
      email:
        type: string
      order_count:
        type: integer
```

## Runtime API

The `mxcp.runtime` module provides access to MXCP services:

### Database Access

```python
from mxcp.runtime import db

# Execute queries
results = db.execute("SELECT * FROM users WHERE active = true")

# With parameters
results = db.execute(
    "SELECT * FROM orders WHERE customer_id = ? AND status = ?",
    {"customer_id": 123, "status": "pending"}
)

# Access raw connection (use with caution in server mode)
conn = db.connection
```

### Configuration Access

```python
from mxcp.runtime import config

# Get secrets - returns the entire parameters dict
secret_params = config.get_secret("external_api_key")
# For a simple value secret: {"value": "api-key-123"}
api_key = secret_params["value"] if secret_params else None

# For complex secrets like HTTP with headers:
http_secret = config.get_secret("api_service")
# Returns: {"BEARER_TOKEN": "token", "EXTRA_HTTP_HEADERS": {"X-API-Key": "key"}}
if http_secret:
    token = http_secret.get("BEARER_TOKEN")
    headers = http_secret.get("EXTRA_HTTP_HEADERS", {})

# Get settings
project_name = config.get_setting("project")
debug_mode = config.get_setting("debug", default=False)

# Access full configs
user_config = config.user_config
site_config = config.site_config
```

### Plugin Access

```python
from mxcp.runtime import plugins

# Get a specific plugin
my_plugin = plugins.get("my_custom_plugin")
if my_plugin:
    result = my_plugin.some_method()

# List available plugins
available = plugins.list()
```

## Lifecycle Hooks

You can register functions to run when the server starts or stops:

```python
from mxcp.runtime import on_init, on_shutdown
import requests

# Global session for reuse
session = None

@on_init
def setup():
    """Initialize resources when server starts."""
    global session
    session = requests.Session()
    print("API client initialized")

@on_shutdown
def cleanup():
    """Clean up resources when server stops."""
    global session
    if session:
        session.close()
    print("API client closed")
```

**Important:** These hooks are for managing Python resources (HTTP clients, connections to external services, etc.), NOT for database management. The DuckDB connection is managed automatically by MXCP.

## Dynamic Reload with Database Rebuild

MXCP provides a powerful feature that allows Python endpoints to trigger a safe reload of the server. This enables you to .e.g update your DuckDB database with fresh data without restarting the server.

### Why Use Dynamic Reload?

Traditional approaches to updating analytical databases often require:
- Stopping the server to update data files
- Running ETL pipelines separately and hoping no queries run during updates
- Complex orchestration to minimize downtime

MXCP's `request_reload` solves these problems by providing a safe, atomic way to rebuild your database while the server continues handling requests.

### How It Works

```python
from mxcp.runtime import request_reload
import subprocess
import pandas as pd

def update_analytics_data():
    """Endpoint that triggers a data refresh."""
    
    def rebuild_database():
        """This runs with exclusive access to the database file."""
        # Option 1: Run dbt to rebuild models
        subprocess.run(["dbt", "run", "--target", "prod"], check=True)
        
        # Option 2: Replace with a pre-built database
        import shutil
        shutil.copy("/staging/analytics.duckdb", "/app/data/analytics.duckdb")
        
        # Option 3: Load fresh data from APIs/files
        df = pd.read_parquet("s3://bucket/latest-data.parquet")
        # DuckDB file is exclusively ours during rebuild
        import duckdb
        conn = duckdb.connect("/app/data/analytics.duckdb")
        conn.execute("CREATE OR REPLACE TABLE sales AS SELECT * FROM df")
        conn.close()
    
    # Trigger the reload with our rebuild function
    request_reload(rebuild_database)
    
    return {"status": "Data refresh completed successfully"}
```

### The Reload Process

When you call `request_reload`, MXCP:

1. **Starts draining requests** - New requests wait, existing ones complete
2. **Acquires exclusive lock** - Ensures no concurrent operations
3. **Shuts down DuckDB** - Closes all connections cleanly
4. **Runs your rebuild function** - With exclusive access to the database file
5. **Reloads configuration** - Picks up any changed secrets or settings
6. **Recreates services** - New DuckDB connection with fresh data
7. **Resumes normal operations** - Queued requests proceed with new data

### Real-World Example: Scheduled Data Updates

```python
from mxcp.runtime import request_reload, db
from datetime import datetime
import requests

def scheduled_update(source: str = "api") -> dict:
    """Endpoint called by cron to update data."""
    
    start_time = datetime.now()
    
    def rebuild_from_api():
        """Fetch latest data and rebuild database."""
        # Fetch data from external API
        response = requests.get("https://api.example.com/analytics/export")
        data = response.json()
        
        # Write to DuckDB (we have exclusive access)
        import duckdb
        conn = duckdb.connect("/app/data/analytics.duckdb")
        
        # Clear old data
        conn.execute("DROP TABLE IF EXISTS daily_metrics")
        
        # Load new data
        conn.execute("""
            CREATE TABLE daily_metrics AS 
            SELECT * FROM read_json_auto(?)
        """, [data])
        
        # Update metadata
        conn.execute("""
            INSERT INTO update_log (timestamp, source, record_count)
            VALUES (?, ?, ?)
        """, [datetime.now(), source, len(data)])
        
        conn.close()
    
    # Trigger the rebuild
    request_reload(rebuild_from_api)
    
    # Check the results
    result = db.execute("SELECT COUNT(*) as count FROM daily_metrics")
    duration = (datetime.now() - start_time).total_seconds()
    
    return {
        "status": "success",
        "records_loaded": result[0]["count"],
        "duration_seconds": duration
    }
```

### Best Practices

1. **Keep rebuilds focused** - Do one thing well in your rebuild function
2. **Handle errors gracefully** - Failed rebuilds leave the server in its previous state
3. **Monitor duration** - Requests wait up to 30 seconds during reload
4. **Test thoroughly** - Rebuild functions run with elevated privileges
5. **Use for data updates** - Not for schema migrations or structural changes

### Configuration-Only Reloads

You can also reload just the configuration (secrets, environment variables) without a rebuild:

```python
def rotate_secrets():
    """Endpoint to reload after secret rotation."""
    # Trigger config reload without database rebuild
    request_reload()
    
    # New secrets are now active
    new_key = config.get_secret("api_key")
    return {"status": "Secrets reloaded successfully"}
```

## Async Functions

Python endpoints support both synchronous and asynchronous functions:

```python
import asyncio
import aiohttp
from mxcp.runtime import db

async def fetch_weather(city: str) -> dict:
    """Fetch weather data asynchronously."""
    async with aiohttp.ClientSession() as session:
        async with session.get(f"https://api.weather.com/v1/{city}") as response:
            data = await response.json()
    
    # Store in database
    db.execute(
        "INSERT INTO weather_cache (city, data, timestamp) VALUES (?, ?, CURRENT_TIMESTAMP)",
        {"city": city, "data": data}
    )
    
    return data
```

## Return Types

Python functions must return data that matches the endpoint's return type:

- **Array type**: Return a list of dictionaries
- **Object type**: Return a single dictionary
- **Scalar types**: Return the value directly (string, int, float, bool)

```python
# Array return type
def list_products() -> list:
    return [
        {"id": 1, "name": "Product A"},
        {"id": 2, "name": "Product B"}
    ]

# Object return type
def get_stats() -> dict:
    return {
        "total_users": 1000,
        "active_users": 750
    }

# Scalar return type
def count_items() -> int:
    result = db.execute("SELECT COUNT(*) as count FROM items")
    return result[0]["count"]
```

## Code Organization

### Shared Modules

You can create shared modules in the `python/` directory:

```python
# python/utils/validators.py
import re

def validate_email(email: str) -> bool:
    pattern = r'^[\w\.-]+@[\w\.-]+\.\w+$'
    return bool(re.match(pattern, email))

def validate_phone(phone: str) -> str:
    # Remove non-digits
    digits = re.sub(r'\D', '', phone)
    if len(digits) == 10:
        return f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"
    return phone
```

Then import in your endpoints:

```python
# python/customer_tools.py
from utils.validators import validate_email, validate_phone
from mxcp.runtime import db

def validate_customer(email: str, phone: str) -> dict:
    return {
        "email_valid": validate_email(email),
        "phone_formatted": validate_phone(phone)
    }
```

### Plugin Integration

Python endpoints can use the same code as plugins:

```python
# python/mxcp_plugin_custom/__init__.py
from mxcp.plugins import MXCPBasePlugin, udf

class MXCPPlugin(MXCPBasePlugin):
    @udf
    def format_currency(self, amount: float) -> str:
        return f"${amount:,.2f}"

# python/reporting.py
from mxcp_plugin_custom import MXCPPlugin
from mxcp.runtime import db

def generate_report() -> list:
    plugin = MXCPPlugin({})
    
    sales = db.execute("SELECT product, amount FROM sales")
    return [
        {
            "product": row["product"],
            "amount": row["amount"],
            "formatted": plugin.format_currency(row["amount"])
        }
        for row in sales
    ]
```

## Best Practices

### Database Access

**Do:**
- Always access the database through `db.execute()` for each operation
- Let MXCP manage the database connection lifecycle
- Use parameterized queries to prevent SQL injection

**Don't:**
- Store the database connection (`db.connection`) in global variables
- Cache database connections in class attributes
- Assume the connection persists across server reloads

```python
from mxcp.runtime import db

# ✅ CORRECT - Access DB through runtime proxy
def get_user_data(user_id: int) -> dict:
    results = db.execute(
        "SELECT * FROM users WHERE id = ?",
        {"user_id": user_id}
    )
    return results[0] if results else None

# ❌ INCORRECT - Don't store the connection
cached_conn = db.connection  # Never do this!

class DataService:
    def __init__(self):
        # ❌ INCORRECT - Don't store connections in instances
        self.conn = db.connection
    
    def get_data(self):
        # This will fail after a configuration reload
        return self.conn.execute("SELECT * FROM data")
```

The `db` proxy ensures your code always uses the current active connection, even after configuration reloads triggered by SIGHUP signals.

1. **Error Handling**: Always handle potential errors gracefully
   ```python
   def safe_divide(a: float, b: float) -> dict:
       if b == 0:
           return {"error": "Division by zero"}
       return {"result": a / b}
   ```

2. **Type Hints**: Use type hints for better IDE support and documentation
   ```python
   def process_data(items: list[dict], threshold: float) -> list[dict]:
       return [item for item in items if item["value"] > threshold]
   ```

3. **Logging**: Use the standard logging module
   ```python
   import logging
   logger = logging.getLogger(__name__)
   
   def process_order(order_id: int) -> dict:
       logger.info(f"Processing order {order_id}")
       # ... processing logic ...
   ```

4. **Resource Management**: Use context managers for external resources
   ```python
   import tempfile
   
   def process_file(content: str) -> dict:
       with tempfile.NamedTemporaryFile(mode='w') as f:
           f.write(content)
           f.flush()
           # Process the file
           return {"processed": True}
   ```

## Performance Considerations

- Python endpoints have more overhead than SQL queries
- For simple data retrieval, prefer SQL endpoints
- Use Python for complex logic, external API calls, or data transformations
- Lifecycle hooks help avoid repeated initialization
- Async functions can improve performance for I/O-bound operations

## Migration from SQL

To migrate an SQL endpoint to Python:

1. Keep the same tool/resource definition
2. Change `language: sql` to `language: python`
3. Update the source file reference
4. Implement the function with the same name as the endpoint

Before (SQL):
```yaml
tool:
  name: get_total
  language: sql
  source:
    file: ../sql/queries.sql
```

After (Python):
```yaml
tool:
  name: get_total
  language: python
  source:
    file: ../python/calculations.py
```

## See Also

- [Python Reference](../reference/python.md) - Quick reference for all runtime APIs
- [SQL Reference](../reference/sql.md) - SQL syntax and built-in functions
- [Configuration Guide](../guides/configuration.md) - Secrets and settings
- [Plugin Development](../reference/plugins.md) - Create reusable components 