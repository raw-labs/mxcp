---
title: "Python Reference"
description: "Quick reference for mxcp.runtime module APIs available in Python endpoints."
keywords:
  - mxcp python
  - python runtime
  - mxcp.runtime
  - python endpoints
  - db.execute
  - config.get_secret
sidebar_position: 5
slug: /reference/python
---

# Python Reference

Python endpoints in MXCP have access to the `mxcp.runtime` module, which provides functions for database access, configuration, secrets, and plugins. This reference provides a quick lookup of available APIs.

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

### `db.execute(query, params=None)`
Execute SQL query and return results as list of dictionaries.

```python
# Simple query
users = db.execute("SELECT * FROM users")

# Parameterized query
result = db.execute(
    "SELECT * FROM orders WHERE customer_id = $id AND status = $status",
    {"id": 123, "status": "pending"}
)
```

### `db.connection`
Access raw DuckDB connection. Use with caution in server mode (not thread-safe).

```python
conn = db.connection
# Use for advanced DuckDB operations
```

## Configuration & Secrets

### `config.get_secret(name)`
Get secret parameters as dictionary. Returns `None` if not found.

```python
# Returns entire parameters dict
secret_params = config.get_secret("api_key")
# For value-type secrets: {"value": "secret-value"}
# For HTTP secrets: {"BEARER_TOKEN": "...", "EXTRA_HTTP_HEADERS": {...}}

# Extract value from value-type secret
api_key = secret_params["value"] if secret_params else None
```

### `config.get_setting(key, default=None)`
Get configuration value from site config.

```python
project = config.get_setting("project")
debug = config.get_setting("debug", default=False)
extensions = config.get_setting("extensions", default=[])
```

### `config.user_config`
Access full user configuration dictionary.

```python
user_cfg = config.user_config
projects = user_cfg["projects"] if user_cfg else {}
```

### `config.site_config`
Access full site configuration dictionary.

```python
site_cfg = config.site_config
secrets_list = site_cfg.get("secrets", [])
```

## Plugin Access

### `plugins.get(name)`
Get plugin instance by name. Returns `None` if not found.

```python
my_plugin = plugins.get("custom_plugin")
if my_plugin:
    result = my_plugin.process_data(data)
```

### `plugins.list()`
Get list of available plugin names.

```python
available = plugins.list()
# Returns: ["plugin1", "plugin2", ...]
```

## Lifecycle Hooks

### `@on_init`
Register function to run when server starts.

```python
@on_init
def setup():
    # Initialize resources
    print("Server starting up")
```

### `@on_shutdown`
Register function to run when server stops.

```python
@on_shutdown
def cleanup():
    # Clean up resources
    print("Server shutting down")
```

## Reload Management

### `reload_duckdb(payload_func=None, description="")`
Request an asynchronous system reload with an optional payload function.

This feature allows Python endpoints to trigger a safe reload of the MXCP server, optionally executing custom logic like rebuilding the DuckDB database with new data. The reload process:
1. Queues the reload request and returns immediately
2. Active requests are drained (allowed to complete)
3. Runtime components (Python hooks + DuckDB) are shut down
4. Your payload function runs (if provided)
5. Runtime components are restarted with fresh configuration

**Important**: If you would like to update the DuckDB database, you can do so in a regular database operation without triggering any reload. Reloading is not required for database updates, since DuckDB supports a MVCC transactional model.

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
    
    # Or fetch and load new data
    fetch_latest_data()
    load_into_duckdb()

# Schedule reload with database replacement
reload_duckdb(
    payload_func=replace_database,
    description="Replacing database with updated version"
)

# Or just reload configuration (refreshes secrets, env vars, etc.)
reload_duckdb()

# Return immediately - reload happens asynchronously
return {"status": "Reload scheduled"}
```

**Use Cases:**
- Updating DuckDB data without server restart
- Running ETL pipelines on demand
- Refreshing materialized views
- Swapping in pre-built database files
- Reloading configuration after secret rotation

**Important Notes:**
- This function returns immediately (non-blocking)
- The reload happens asynchronously after the current request completes
- The payload function runs with all connections closed
- Only one reload can be processing at a time
- From MCP tools, you cannot wait for completion - check status indirectly
- Only available when called from within MXCP endpoints

## Context Availability

The runtime context is automatically set when your function is called by MXCP. All functions are thread-safe and maintain proper isolation between concurrent requests.

## Type Compatibility

Python return values must match the declared endpoint return type:

| YAML Type | Python Return |
|-----------|---------------|
| `array`   | `list[dict]`  |
| `object`  | `dict`        |
| `string`  | `str`         |
| `integer` | `int`         |
| `number`  | `float`       |
| `boolean` | `bool`        |

## See Also

- [Python Endpoints Guide](../features/python-endpoints.md)
- [Configuration Guide](../guides/configuration.md)
- [Plugin Development](plugins.md) 