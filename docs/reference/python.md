---
title: "Python Reference"
description: "Python runtime API reference for MXCP. Database access, configuration, plugins, and lifecycle hooks."
sidebar:
  order: 4
---

Python endpoints have access to the `mxcp.runtime` module, which provides database access, configuration, secrets, and lifecycle management.

## Quick Example

```python
from mxcp.runtime import db, config, plugins, on_init, on_shutdown, reload_duckdb

def my_endpoint(param: str) -> dict:
    # Query database
    results = db.execute("SELECT * FROM users WHERE name = $name", {"name": param})

    # Access secrets
    api_key_params = config.get_secret("api_key")

    # Get configuration
    project = config.get_setting("project")

    return {"users": results, "project": project}
```

## Database Access

### db.execute()

Execute SQL query and return results as list of dictionaries.

```python
# Simple query
users = db.execute("SELECT * FROM users")

# Parameterized query
result = db.execute(
    "SELECT * FROM orders WHERE customer_id = $id AND status = $status",
    {"id": 123, "status": "pending"}
)

# Insert/Update (returns affected rows)
db.execute(
    "INSERT INTO logs (message, timestamp) VALUES ($msg, NOW())",
    {"msg": "Event occurred"}
)
```

**Parameters:**
- `query` (str): SQL query to execute
- `params` (dict, optional): Named parameters

**Returns:** `list[dict]` - Query results

### db.connection

Access raw DuckDB connection for advanced operations.

```python
conn = db.connection
# Use for advanced DuckDB operations
# Warning: Not thread-safe in server mode
```

## Configuration & Secrets

### config.get_secret()

Get secret parameters as dictionary.

```python
# Value-type secrets
secret_params = config.get_secret("api_key")
# Returns: {"value": "secret-value"}

api_key = secret_params["value"] if secret_params else None

# HTTP secrets
http_secret = config.get_secret("http_auth")
# Returns: {"BEARER_TOKEN": "...", "EXTRA_HTTP_HEADERS": {...}}

# Check if secret exists
if config.get_secret("optional_secret"):
    # Secret is configured
    pass
```

**Parameters:**
- `name` (str): Secret name

**Returns:** `dict | None` - Secret parameters or None

### config.get_setting()

Get configuration value from site config.

```python
# Get required setting
project = config.get_setting("project")

# Get with default
debug = config.get_setting("debug", default=False)
extensions = config.get_setting("extensions", default=[])
timeout = config.get_setting("timeout", default=30)
```

**Parameters:**
- `key` (str): Setting key
- `default` (any, optional): Default value if not found

**Returns:** Setting value or default

### config.user_config

Access full user configuration model.

```python
user_cfg = config.user_config
if user_cfg:
    active_project = user_cfg.projects[user_cfg.site]
    active_profile = active_project.profiles[user_cfg.profile]
    secret_names = [secret.name for secret in active_profile.secrets]
```

### config.site_config

Access full site configuration model.

```python
site_cfg = config.site_config
if site_cfg:
    secrets_list = site_cfg.secrets
    default_duckdb = site_cfg.profiles[site_cfg.profile].duckdb.path
```

## Plugin Access

### plugins.get()

Get plugin instance by name.

```python
my_plugin = plugins.get("custom_plugin")
if my_plugin:
    result = my_plugin.process_data(data)
```

**Parameters:**
- `name` (str): Plugin instance name

**Returns:** Plugin instance or None

### plugins.list()

Get list of available plugin names.

```python
available = plugins.list()
# Returns: ["plugin1", "plugin2", ...]

for name in plugins.list():
    plugin = plugins.get(name)
    print(f"Plugin: {name}")
```

**Returns:** `list[str]` - Plugin names

## MCP Logging & Progress

The `mxcp.runtime.mcp` proxy provides MCP-aware logging. When running in FastMCP, calls are forwarded to the client; during CLI/tests they fall back to server logging.

```python
from mxcp.runtime import mcp

async def run_job() -> None:
    await mcp.info("Starting ingestion")
    await mcp.progress(1, 4, "Fetched source metadata")
    await mcp.warning("External API is slow today")
    await mcp.progress(4, 4, "Done")
```

### Logging Functions

```python
# Log levels
await mcp.debug("Debug message")
await mcp.info("Info message")
await mcp.warning("Warning message")
await mcp.error("Error message")

# Progress reporting
await mcp.progress(current=1, total=10, message="Processing item 1")
```

### Synchronous Usage

For synchronous endpoints:

```python
import asyncio

def sync_endpoint(data: str) -> dict:
    asyncio.run(mcp.info("Processing data"))
    return {"result": process(data)}
```

## Lifecycle Hooks

### @on_init

Register function to run when server starts.

```python
from mxcp.runtime import on_init

@on_init
def setup():
    print("Server starting up")
    # Initialize resources
    # Load caches
    # Connect to services
```

**Use Cases:**
- Warm up caches
- Initialize connections
- Validate configuration
- Load static data

### @on_shutdown

Register function to run when server stops.

```python
from mxcp.runtime import on_shutdown

@on_shutdown
def cleanup():
    print("Server shutting down")
    # Close connections
    # Flush buffers
    # Clean up resources
```

**Use Cases:**
- Close database connections
- Flush log buffers
- Release external resources
- Save state

### Multiple Hooks

```python
@on_init
def setup_database():
    print("Setting up database connections")

@on_init
def setup_cache():
    print("Warming up cache")

@on_shutdown
def close_database():
    print("Closing database connections")

@on_shutdown
def flush_logs():
    print("Flushing log buffers")
```

## Reload Management

### reload_duckdb()

Request an asynchronous system reload.

```python
from mxcp.runtime import reload_duckdb
import subprocess
import shutil

def replace_database():
    """Payload function - runs with all connections closed."""
    # Run dbt to rebuild models
    subprocess.run(["dbt", "run"], check=True)

    # Or copy a new database file
    shutil.copy("/data/updated.duckdb", "/app/data.duckdb")

# Schedule reload with database replacement
reload_duckdb(
    payload_func=replace_database,
    description="Replacing database with updated version"
)

# Or just reload configuration
reload_duckdb()

# Return immediately - reload happens asynchronously
return {"status": "Reload scheduled"}
```

**Parameters:**
- `payload_func` (callable, optional): Function to run during reload
- `description` (str, optional): Description for logging

**Reload Process:**
1. Queues reload request
2. Active requests are drained
3. Runtime shuts down (Python hooks + DuckDB)
4. Payload function runs (if provided)
5. Runtime restarts with fresh configuration

**Use Cases:**
- Update DuckDB data without restart
- Run ETL pipelines on demand
- Refresh materialized views
- Swap in pre-built database files
- Reload configuration after secret rotation

**Important Notes:**
- Returns immediately (non-blocking)
- Only one reload processes at a time
- Payload runs with connections closed
- Cannot wait for completion from MCP tools

**When NOT to Use:**

For most database operations, use `db.execute()` directly:

```python
# Simple updates - no reload needed
db.execute("INSERT INTO users VALUES ($name)", {"name": "Alice"})
db.execute("UPDATE stats SET value = $value", {"value": 100})
```

Only use `reload_duckdb()` when external tools need exclusive database access.

## Type Compatibility

Python return values must match declared endpoint return types:

| YAML Type | Python Type | Example |
|-----------|-------------|---------|
| `string` | `str` | `"hello"` |
| `integer` | `int` | `42` |
| `number` | `float` | `3.14` |
| `boolean` | `bool` | `True` |
| `array` | `list` | `[1, 2, 3]` |
| `object` | `dict` | `{"key": "value"}` |

### Type Examples

```python
# String return
def get_name(id: int) -> str:
    return "Alice"

# Integer return
def get_count() -> int:
    return 42

# Number return
def get_average() -> float:
    return 3.14

# Boolean return
def is_valid(id: int) -> bool:
    return True

# Array return
def get_users() -> list:
    return [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}]

# Object return
def get_user(id: int) -> dict:
    return {"id": id, "name": "Alice", "active": True}
```

### Complex Types

```python
# Nested objects
def get_report() -> dict:
    return {
        "summary": {
            "total": 100,
            "average": 42.5
        },
        "items": [
            {"id": 1, "value": 10},
            {"id": 2, "value": 20}
        ]
    }

# Arrays of objects
def get_orders() -> list:
    return [
        {"id": 1, "items": ["a", "b"]},
        {"id": 2, "items": ["c", "d"]}
    ]
```

## Context Availability

The runtime context is automatically set when MXCP calls your function:

```python
def my_endpoint(param: str) -> dict:
    # db, config, plugins are all available
    # Context is thread-safe and isolated between requests
    users = db.execute("SELECT * FROM users")
    return {"users": users}
```

## Error Handling

```python
def safe_endpoint(id: int) -> dict:
    try:
        result = db.execute("SELECT * FROM users WHERE id = $id", {"id": id})
        if not result:
            return {"error": "User not found", "id": id}
        return result[0]
    except Exception as e:
        return {"error": str(e)}
```

## Complete Example

```python
from mxcp.runtime import db, config, plugins, on_init, on_shutdown, mcp
import asyncio

# Initialization
@on_init
def setup():
    print("Starting up...")

@on_shutdown
def cleanup():
    print("Shutting down...")

# Main endpoint
async def analyze_data(department: str, limit: int = 10) -> dict:
    await mcp.info(f"Analyzing {department}")

    # Get configuration
    threshold = config.get_setting("threshold", default=100)

    # Query database
    await mcp.progress(1, 3, "Fetching data")
    employees = db.execute(
        "SELECT * FROM employees WHERE department = $dept LIMIT $limit",
        {"dept": department, "limit": limit}
    )

    # Process with plugin
    await mcp.progress(2, 3, "Processing")
    analytics = plugins.get("analytics")
    if analytics:
        stats = analytics.calculate_stats(employees)
    else:
        stats = {"count": len(employees)}

    # Return results
    await mcp.progress(3, 3, "Complete")
    return {
        "department": department,
        "employees": employees,
        "stats": stats,
        "threshold": threshold
    }
```

## Next Steps

- [Plugin Reference](plugins) - Plugin development
- [Tutorials](/tutorials/python-endpoints) - Python examples
- [Type System](/concepts/type-system) - Type mapping
