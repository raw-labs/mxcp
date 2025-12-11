---
title: "Python Endpoints Tutorial"
description: "Build complex AI tools with Python. Learn the runtime API, database access, async operations, and lifecycle hooks."
sidebar:
  order: 4
---

> **Related Topics:** [Python Runtime Reference](/reference/python) (API details) | [Type System](/concepts/type-system) (parameter types) | [Plugins](/reference/plugins) (custom UDFs) | [SQL Endpoints](sql-endpoints) (when to use SQL instead)

Python endpoints let you build tools with complex logic, API integrations, and ML models. In this tutorial, you'll learn to use MXCP's Python runtime features effectively.

## Goal

Build Python tools that:
- Access the database from Python
- Use configuration and secrets
- Handle async operations
- Implement lifecycle hooks
- Combine SQL and Python logic

## Prerequisites

- Completed the [Hello World Tutorial](hello-world)
- Basic Python knowledge
- A project directory with `mxcp init`

## Step 1: Basic Python Tool

Create a simple Python tool.

**Tool definition** (`tools/greet.yml`):
```yaml
mxcp: 1
tool:
  name: personalized_greeting
  description: Generate a personalized greeting with timestamp
  language: python

  parameters:
    - name: name
      type: string
      description: Name to greet
      examples: ["Alice", "Bob"]

    - name: formal
      type: boolean
      description: Use formal greeting
      default: false

  return:
    type: object
    properties:
      greeting:
        type: string
      timestamp:
        type: string
        format: date-time

  source:
    file: ../python/greetings.py

  tests:
    - name: informal_greeting
      arguments:
        - key: name
          value: "Alice"
        - key: formal
          value: false
      result_contains_text: "Hi Alice"
```

**Python implementation** (`python/greetings.py`):
```python
from datetime import datetime, timezone

def personalized_greeting(name: str, formal: bool = False) -> dict:
    """Generate a personalized greeting with timestamp."""
    if formal:
        greeting = f"Good day, {name}. How may I assist you?"
    else:
        greeting = f"Hi {name}! How are you doing?"

    return {
        "greeting": greeting,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
```

Test it:
```bash
mxcp run tool personalized_greeting --param name=Alice
mxcp run tool personalized_greeting --param name=Alice --param formal=true
```

## Step 2: Database Access

Access the DuckDB database from Python using the runtime API.

**Tool definition** (`tools/user-lookup.yml`):
```yaml
mxcp: 1
tool:
  name: user_lookup
  description: Look up user by email with additional processing
  language: python

  parameters:
    - name: email
      type: string
      format: email
      description: User's email address

  return:
    type: object
    properties:
      found:
        type: boolean
      user:
        type: object
        properties:
          id:
            type: integer
          name:
            type: string
          email:
            type: string
          domain:
            type: string

  source:
    file: ../python/user_tools.py
```

**Python implementation** (`python/user_tools.py`):
```python
from mxcp.runtime import db

def user_lookup(email: str) -> dict:
    """Look up user by email and extract domain."""
    # Query the database - returns list of dicts
    results = db.execute(
        "SELECT id, name, email FROM users WHERE email = $email",
        {"email": email}
    )

    if not results:
        return {"found": False, "user": None}

    result = results[0]  # Get first result

    # Add Python processing
    domain = email.split("@")[1] if "@" in email else "unknown"

    return {
        "found": True,
        "user": {
            "id": result["id"],
            "name": result["name"],
            "email": result["email"],
            "domain": domain
        }
    }
```

The `db` object provides:
- `db.execute(sql, params)` - Execute SQL with parameters, returns `list[dict]`
- `db.connection` - Raw DuckDB connection for advanced operations

## Step 3: Configuration and Secrets

Access configuration and secrets securely.

**User configuration** (`~/.mxcp/config.yml`):
```yaml
mxcp: 1
projects:
  my-project:
    profiles:
      default:
        secrets:
          - name: api_credentials
            type: custom
            parameters:
              api_key: "your-api-key-here"
              api_url: "https://api.example.com"
```

**Tool definition** (`tools/api-call.yml`):
```yaml
mxcp: 1
tool:
  name: fetch_external_data
  description: Fetch data from external API
  language: python

  parameters:
    - name: query
      type: string
      description: Search query

  return:
    type: object
    properties:
      status:
        type: string
      data:
        type: array
        items:
          type: object

  source:
    file: ../python/api_tools.py
```

**Python implementation** (`python/api_tools.py`):
```python
import httpx
from mxcp.runtime import config

def fetch_external_data(query: str) -> dict:
    """Fetch data from external API using configured credentials."""
    # Get secrets from configuration
    api_key = config.get_secret("api_credentials", "api_key")
    api_url = config.get_secret("api_credentials", "api_url")

    if not api_key:
        return {"status": "error", "data": [], "error": "API key not configured"}

    try:
        response = httpx.get(
            f"{api_url}/search",
            params={"q": query},
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=30.0
        )
        response.raise_for_status()
        return {"status": "success", "data": response.json()}

    except httpx.HTTPError as e:
        return {"status": "error", "data": [], "error": str(e)}
```

## Step 4: Async Operations

Use async/await for concurrent operations.

**Tool definition** (`tools/batch-fetch.yml`):
```yaml
mxcp: 1
tool:
  name: batch_user_data
  description: Fetch data for multiple users concurrently
  language: python

  parameters:
    - name: user_ids
      type: array
      items:
        type: integer
      description: List of user IDs
      minItems: 1
      maxItems: 50

  return:
    type: array
    items:
      type: object
      properties:
        user_id:
          type: integer
        name:
          type: string
        status:
          type: string

  source:
    file: ../python/async_tools.py
```

**Python implementation** (`python/async_tools.py`):
```python
import asyncio
from mxcp.runtime import db

async def batch_user_data(user_ids: list[int]) -> list[dict]:
    """Fetch multiple users concurrently."""

    async def fetch_one(user_id: int) -> dict:
        # Simulate async database lookup
        results = db.execute(
            "SELECT id, name FROM users WHERE id = $id",
            {"id": user_id}
        )

        if results:
            result = results[0]
            return {
                "user_id": user_id,
                "name": result["name"],
                "status": "found"
            }
        return {
            "user_id": user_id,
            "name": None,
            "status": "not_found"
        }

    # Execute all lookups concurrently
    tasks = [fetch_one(uid) for uid in user_ids]
    results = await asyncio.gather(*tasks)
    return list(results)
```

MXCP automatically detects async functions and awaits them.

## Step 5: Lifecycle Hooks

Use lifecycle hooks for initialization and cleanup.

**Python implementation** (`python/services.py`):
```python
from mxcp.runtime import db, config, on_init, on_shutdown, on_reload

# Global state (use sparingly)
_cache = {}
_model = None

@on_init
def initialize():
    """Called when the server starts."""
    global _cache, _model
    print("Initializing service...")

    # Load ML model
    # _model = load_model("path/to/model")

    # Pre-populate cache
    _cache = {}

    print("Service initialized")

@on_shutdown
def cleanup():
    """Called when the server stops."""
    global _cache, _model
    print("Cleaning up service...")

    # Save state
    _cache.clear()
    _model = None

    print("Service cleaned up")

@on_reload
def refresh():
    """Called on SIGHUP (configuration reload)."""
    global _cache
    print("Reloading configuration...")

    # Clear caches
    _cache.clear()

    print("Configuration reloaded")

def cached_lookup(key: str) -> dict:
    """Tool that uses the cache."""
    if key in _cache:
        return {"source": "cache", "value": _cache[key]}

    # Fetch from database
    results = db.execute(
        "SELECT value FROM cache_table WHERE key = $key",
        {"key": key}
    )

    if results:
        _cache[key] = results[0]["value"]
        return {"source": "database", "value": results[0]["value"]}

    return {"source": "none", "value": None}
```

Lifecycle hooks:
- `@on_init` - Called once when server starts
- `@on_shutdown` - Called when server stops
- `@on_reload` - Called on SIGHUP signal

## Step 6: Combining SQL and Python

Leverage both SQL efficiency and Python flexibility.

**Tool definition** (`tools/customer-analysis.yml`):
```yaml
mxcp: 1
tool:
  name: customer_analysis
  description: Comprehensive customer analysis with ML insights
  language: python

  parameters:
    - name: customer_id
      type: integer
      description: Customer ID

  return:
    type: object
    properties:
      customer_id:
        type: integer
      basic_info:
        type: object
      purchase_summary:
        type: object
      insights:
        type: object

  source:
    file: ../python/analysis.py
```

**Python implementation** (`python/analysis.py`):
```python
from mxcp.runtime import db
import statistics

def customer_analysis(customer_id: int) -> dict:
    """Combine SQL aggregation with Python analysis."""

    # Use SQL for efficient data aggregation
    basic_results = db.execute("""
        SELECT name, email, department, created_at
        FROM users
        WHERE id = $id
    """, {"id": customer_id})

    if not basic_results:
        return {"error": "Customer not found"}

    basic = basic_results[0]

    # Use SQL for purchase aggregation
    purchase_results = db.execute("""
        SELECT
            COUNT(*) as count,
            SUM(amount) as total,
            AVG(amount) as average,
            MIN(amount) as min_purchase,
            MAX(amount) as max_purchase
        FROM orders
        WHERE user_id = $id AND status = 'completed'
    """, {"id": customer_id})

    purchases = purchase_results[0] if purchase_results else None

    # Get purchase history for Python analysis
    history = db.execute("""
        SELECT amount, created_at
        FROM orders
        WHERE user_id = $id AND status = 'completed'
        ORDER BY created_at DESC
        LIMIT 100
    """, {"id": customer_id})

    # Python-based insights
    amounts = [h["amount"] for h in history]
    insights = generate_insights(amounts)

    return {
        "customer_id": customer_id,
        "basic_info": dict(basic),
        "purchase_summary": dict(purchases) if purchases and purchases["count"] > 0 else None,
        "insights": insights
    }

def generate_insights(amounts: list[float]) -> dict:
    """Generate insights using Python statistics."""
    if not amounts:
        return {"status": "no_data"}

    recent = amounts[:10]
    older = amounts[10:20] if len(amounts) > 10 else []

    insights = {
        "total_analyzed": len(amounts),
        "spending_trend": "unknown"
    }

    if len(recent) >= 3:
        recent_avg = statistics.mean(recent)
        insights["recent_average"] = round(recent_avg, 2)

        if older:
            older_avg = statistics.mean(older)
            if recent_avg > older_avg * 1.1:
                insights["spending_trend"] = "increasing"
            elif recent_avg < older_avg * 0.9:
                insights["spending_trend"] = "decreasing"
            else:
                insights["spending_trend"] = "stable"

    if len(amounts) >= 2:
        insights["std_dev"] = round(statistics.stdev(amounts), 2)

    return insights
```

## Step 7: Error Handling

Handle errors gracefully in Python tools.

```python
from mxcp.runtime import db
import logging

logger = logging.getLogger(__name__)

def safe_operation(param: str) -> dict:
    """Demonstrate proper error handling."""
    try:
        # Validate input
        if not param or len(param) < 3:
            return {
                "status": "error",
                "error": "Parameter must be at least 3 characters"
            }

        # Database operation - db.execute returns list[dict]
        results = db.execute(
            "SELECT * FROM data WHERE key = $key",
            {"key": param}
        )

        if not results:
            return {
                "status": "not_found",
                "error": f"No data found for key: {param}"
            }

        return {
            "status": "success",
            "data": results[0]
        }

    except Exception as e:
        logger.error(f"Operation failed: {e}")
        return {
            "status": "error",
            "error": "An internal error occurred"
        }
```

## Verification

Test all your Python tools:

```bash
# Validate
mxcp validate

# Run tests
mxcp test

# Test specific tools
mxcp run tool personalized_greeting --param name=Test
mxcp run tool user_lookup --param email="alice@example.com"
```

## Step 8: Dynamic Database Reload

MXCP provides a feature to trigger safe reload of the server, useful when external processes need to update the DuckDB database.

**When to use `reload_duckdb`:**
- External tools require exclusive database access
- Running dbt as a separate process (not via Python API)
- Replacing the database file with a pre-built one

**When NOT to use it (use direct `db` operations instead):**
- Normal database operations
- Running dbt via Python API
- Any operation that can work with the existing connection

```python
from mxcp.runtime import reload_duckdb, db
import subprocess

def update_analytics_data() -> dict:
    """Endpoint that triggers a data refresh."""

    def rebuild_database():
        """This runs with all connections closed."""
        # Option 1: Run external dbt command
        subprocess.run(["dbt", "run", "--target", "prod"], check=True)

        # Option 2: Replace database file
        import shutil
        shutil.copy("/staging/analytics.duckdb", "/app/data/analytics.duckdb")

    # Schedule the reload - happens asynchronously
    reload_duckdb(
        payload_func=rebuild_database,
        description="Updating analytics data"
    )

    return {"status": "scheduled", "message": "Data refresh will complete in background"}
```

**The reload process:**
1. Queues the reload request (function returns immediately)
2. Drains active requests
3. Closes DuckDB connections
4. Runs your payload function
5. Restarts runtime components
6. Processes waiting requests

## Step 9: Plugin Access

Access registered plugins from Python code:

```python
from mxcp.runtime import plugins

def use_plugin_functions() -> dict:
    """Demonstrate plugin access."""
    # Get a specific plugin
    my_plugin = plugins.get("my_custom_plugin")
    if my_plugin:
        result = my_plugin.some_method()

    # List available plugins
    available = plugins.list()

    return {"plugins": available}
```

## Step 10: Code Organization

Organize Python code with shared modules.

**Create shared utilities** (`python/utils/validators.py`):
```python
import re

def validate_email(email: str) -> bool:
    pattern = r'^[\w\.-]+@[\w\.-]+\.\w+$'
    return bool(re.match(pattern, email))

def validate_phone(phone: str) -> str:
    digits = re.sub(r'\D', '', phone)
    if len(digits) == 10:
        return f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"
    return phone
```

**Import in your endpoints** (`python/customer_tools.py`):
```python
from utils.validators import validate_email, validate_phone
from mxcp.runtime import db

def validate_customer(email: str, phone: str) -> dict:
    return {
        "email_valid": validate_email(email),
        "phone_formatted": validate_phone(phone)
    }
```

## Best Practices

### 1. Use Type Hints
```python
def my_tool(name: str, count: int = 10) -> dict:
    ...
```

### 2. Match Function Name to Tool Name
```yaml
tool:
  name: my_tool  # Matches function name
```

### 3. Return Structured Data
```python
# Good
return {"status": "success", "data": result}

# Avoid
return result  # Unstructured
```

### 4. Use the Runtime API
```python
from mxcp.runtime import db, config

# Always access through the runtime proxy
# Don't create your own connections
```

### 5. Never Cache Database Connections

```python
# CORRECT - Access DB through runtime proxy
def get_user_data(user_id: int) -> dict:
    results = db.execute(
        "SELECT * FROM users WHERE id = $id",
        {"id": user_id}
    )
    return results[0] if results else None

# INCORRECT - Don't store connections
cached_conn = db.connection  # Never do this!

class DataService:
    def __init__(self):
        # INCORRECT - Don't store in instances
        self.conn = db.connection  # Will fail after reload
```

The `db` proxy ensures your code uses the current active connection, even after configuration reloads.

### 6. Handle Missing Data
```python
results = db.execute(...)  # Returns list[dict]
if not results:
    return {"error": "Not found"}
result = results[0]  # First row
```

### 7. Log Appropriately
```python
import logging
logger = logging.getLogger(__name__)
logger.info("Processing request")
```

## Performance Considerations

Python endpoints have more overhead than SQL queries:

- For simple data retrieval, prefer SQL endpoints
- Use Python for complex logic, external API calls, or data transformations
- Lifecycle hooks help avoid repeated initialization
- Async functions can improve performance for I/O-bound operations

```python
# Prefer SQL for simple queries:
# tools/list-users.yml with SQL source

# Use Python when you need:
# - Complex business logic
# - External API calls
# - ML model predictions
# - Data transformations with Python libraries
```

## Migration from SQL

To migrate an SQL endpoint to Python:

1. Keep the same tool/resource definition
2. Change `language: sql` to `language: python`
3. Update the source file reference
4. Implement the function with the same name as the endpoint

**Before (SQL):**
```yaml
tool:
  name: get_total
  language: sql
  source:
    file: ../sql/queries.sql
```

**After (Python):**
```yaml
tool:
  name: get_total
  language: python
  source:
    file: ../python/calculations.py
```

```python
# python/calculations.py
from mxcp.runtime import db

def get_total() -> dict:
    results = db.execute("SELECT SUM(amount) as total FROM orders")
    return {"total": results[0]["total"] if results else 0}
```

## Next Steps

- [Policies](/security/policies) - Add access control
- [Testing](/quality/testing) - Test Python tools
- [Python Reference](/reference/python) - Complete API reference
- [Plugins](/reference/plugins) - Create DuckDB extensions
