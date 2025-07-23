---
title: "Plugins"
description: "Extend MXCP with custom Python plugins. Create User Defined Functions (UDFs) for DuckDB, integrate with external APIs, and add custom data processing logic."
keywords:
  - mxcp plugins
  - python plugins
  - user defined functions
  - duckdb udfs
  - plugin development
  - custom functions
sidebar_position: 3
slug: /reference/plugins
---

# MXCP Plugins

MXCP's plugin system allows you to extend DuckDB with custom User Defined Functions (UDFs) written in Python. Plugins provide a powerful way to add domain-specific functionality, integrate with external APIs, and implement custom data processing logic directly within your SQL queries.

## Overview

MXCP plugins are Python modules that inherit from `MXCPBasePlugin` and use the `@udf` decorator to expose methods as DuckDB functions. When loaded, these plugins automatically register their functions in the DuckDB session, making them available in all SQL queries.

### Key Features

- **Automatic UDF Registration**: Methods decorated with `@udf` are automatically converted to DuckDB functions
- **Type Safety**: Full Python type hint support with automatic DuckDB type mapping
- **User Context Integration**: Access authenticated user information and OAuth tokens (when authentication is enabled)
- **Configuration Management**: Flexible configuration system with site-level plugin definitions and user-level settings
- **Hot Reload**: Plugins are loaded fresh for each DuckDB session

## Quick Start

### 1. Define a Plugin in Site Configuration

In your `mxcp-site.yml`, define the plugins you want to use:

```yaml
mxcp: 1
project: my-project
profile: dev

plugin:
  - name: my_cipher                    # Instance name (used in SQL as suffix)
    module: my_plugin                  # Python module to import
    config: dev_config                 # Configuration name from user config
```

### 2. Configure Plugin Settings

In your user configuration (`~/.mxcp/config.yml`), provide plugin-specific settings:

```yaml
mxcp: 1

projects:
  my-project:
    profiles:
      dev:
        plugin:
          config:
            dev_config:
              rotation: "13"           # Plugin-specific settings
              enable_logging: "true"
            prod_config:
              rotation: "5"
              enable_logging: "false"
```

### 3. Create the Plugin Module

Create a Python file/module with your plugin implementation. All plugin modules must be placed in the `plugins/` directory of your MXCP project:

```python
# plugins/my_plugin/__init__.py
from typing import Dict, Any
from mxcp.plugins import MXCPBasePlugin, udf

class MXCPPlugin(MXCPBasePlugin):
    def __init__(self, config: Dict[str, Any], user_context=None):
        super().__init__(config, user_context)
        self.rotation = int(config.get("rotation", 13))
    
    @udf
    def encrypt(self, text: str) -> str:
        """Encrypt text using Caesar cipher."""
        return self._rotate_text(text, self.rotation)
    
    @udf
    def decrypt(self, text: str) -> str:
        """Decrypt text using Caesar cipher."""
        return self._rotate_text(text, -self.rotation)
        
    def _rotate_text(self, text: str, shift: int) -> str:
        # Implementation details...
        pass
```

### 4. Use in SQL

The plugin functions are available in SQL with the naming pattern `{function_name}_{plugin_instance_name}`:

```sql
-- Using the functions from the plugin
SELECT encrypt_my_cipher('Hello World') as encrypted_text;
SELECT decrypt_my_cipher(encrypted_text) as decrypted_text;
```

## Configuration

### Site Configuration (`mxcp-site.yml`)

The site configuration defines which plugins are available in your project:

```yaml
plugin:
  - name: string_utils              # Required: Instance name
    module: utils.string_plugin     # Required: Python module path
    config: default                 # Optional: Config name from user config
  
  - name: api_client
    module: integrations.github
    config: github_settings
    
  - name: simple_plugin
    module: my_simple_plugin
    # No config means empty configuration {}
```

**Configuration Fields:**

- `name` (required): Unique identifier for this plugin instance. Used as suffix in SQL function names.
- `module` (required): Python module path containing the `MXCPPlugin` class. The module must exist in the `plugins/` directory.
- `config` (optional): Reference to configuration in user config. If omitted, plugin receives empty config `{}`.

### User Configuration (`~/.mxcp/config.yml`)

User configuration provides settings for plugin instances:

```yaml
projects:
  my-project:
    profiles:
      dev:
        plugin:
          config:
            default:                    # Config name referenced in site config
              api_key: "${API_KEY}"     # Environment variable interpolation
              timeout: "30"
              debug: "true"
              
            github_settings:
              base_url: "https://api.github.com"
              rate_limit: "5000"
              
            production_settings:
              debug: "false"
              timeout: "60"
```

**Configuration Features:**

- **Environment Variables**: Use `${VAR_NAME}` syntax for environment variable interpolation
- **Profile-Specific**: Different configurations per profile (dev, staging, prod)
- **Type Flexibility**: All values are provided as strings to plugins (plugins handle type conversion)

## Developing Plugins

### Basic Plugin Structure

Every MXCP plugin must:

1. Define a class named `MXCPPlugin` that inherits from `MXCPBasePlugin`
2. Implement the `__init__` method to accept configuration
3. Use the `@udf` decorator on methods you want to expose as SQL functions
4. Provide complete type hints for all UDF parameters and return values

```python
from typing import Dict, Any, Optional
from mxcp.plugins import MXCPBasePlugin, udf

class MXCPPlugin(MXCPBasePlugin):
    def __init__(self, config: Dict[str, Any], user_context=None):
        """Initialize plugin with config and optional user context.
        
        Args:
            config: Plugin configuration from user config
            user_context: Optional authenticated user context (new feature)
        """
        super().__init__(config, user_context)
        # Initialize your plugin state here
```

### UDF Definition

Use the `@udf` decorator to mark methods as SQL functions:

```python
@udf
def process_text(self, text: str, length: int) -> str:
    """Process text with specified length.
    
    Args:
        text: Input text to process
        length: Maximum length
        
    Returns:
        Processed text
    """
    return text[:length].upper()
```

**UDF Requirements:**

- Must have `@udf` decorator
- Must have complete type hints for all parameters and return value
- First parameter is always `self` (automatically handled)
- Type hints are used to generate DuckDB function signatures

### Supported Types

MXCP automatically maps Python types to DuckDB types:

| Python Type   | DuckDB Type  | Example              |
|---------------|--------------|----------------------|
| `str`         | `VARCHAR`    | `"hello"`            |
| `int`         | `INTEGER`    | `42`                 |
| `float`       | `DOUBLE`     | `3.14`               |
| `bool`        | `BOOLEAN`    | `True`               |
| `bytes`       | `BLOB`       | `b"data"`            |
| `date`        | `DATE`       | `date(2023, 1, 1)`   |
| `time`        | `TIME`       | `time(14, 30)`       |
| `datetime`    | `TIMESTAMP`  | `datetime.now()`     |
| `timedelta`   | `INTERVAL`   | `timedelta(hours=1)` |
| `list[T]`     | `T[]`        | `[1, 2, 3]`          |
| `dict[K, V]`  | `MAP(K, V)`  | `{"key": "value"}`   |
| `Optional[T]` | Nullable `T` | `None` or value      |

### Complex Types

You can also define structured types using classes or dataclasses:

```python
from dataclasses import dataclass

@dataclass
class UserInfo:
    name: str
    age: int
    active: bool

@udf
def create_user(self, name: str, age: int, active: bool) -> UserInfo:
    """Create a user info struct."""
    return UserInfo(name=name, age=age, active=active)
```

## Authentication Integration

When authentication is enabled, plugins can access user information and OAuth tokens through the UserContext.

### Accessing User Information

```python
class MXCPPlugin(MXCPBasePlugin):
    def __init__(self, config: Dict[str, Any], user_context=None):
        super().__init__(config, user_context)
    
    @udf
    def get_current_user(self) -> str:
        """Get the current authenticated user's username."""
        if self.is_authenticated():
            return self.get_username() or "unknown"
        return "not authenticated"
    
    @udf
    def user_specific_processing(self, data: str) -> str:
        """Process data differently for each user."""
        if self.is_authenticated():
            username = self.get_username()
            return f"[{username}] {data.upper()}"
        return data
```

### Making External API Calls

Use the user's OAuth token to make authenticated API calls:

```python
import httpx

@udf
async def fetch_user_repos(self) -> str:
    """Fetch user's GitHub repositories using their token."""
    if not self.is_authenticated():
        return "Authentication required"
    
    token = self.get_user_token()
    if not token:
        return "No external token available"
    
    async with httpx.AsyncClient() as client:
        response = await client.get(
            "https://api.github.com/user/repos",
            headers={"Authorization": f"Bearer {token}"}
        )
        repos = response.json()
        return f"Found {len(repos)} repositories"
```

### User Context Methods

The base plugin class provides these methods for user context access:

```python
# Check authentication status
self.is_authenticated() -> bool

# Get user information
self.get_username() -> Optional[str]
self.get_user_email() -> Optional[str] 
self.get_user_provider() -> Optional[str]  # 'github', 'atlassian', etc.

# Get OAuth token for API calls
self.get_user_token() -> Optional[str]

# Access full user context
self.user_context -> Optional[UserContext]
```

## Plugin Lifecycle and Resource Management

MXCP plugins have a formal lifecycle that allows for graceful startup and shutdown. This is crucial for managing long-lived resources like HTTP clients, database connections, or connection pools, especially when the server performs a hot-reload of its configuration.

### Lifecycle Overview

- **Initialization**: When the server starts or reloads, it creates plugin instances by calling their `__init__` method
- **Shutdown**: When the server shuts down or reloads, it calls shutdown hooks on all active plugins to clean up resources
- **Hot Reload**: During a configuration reload (via `SIGHUP` signal), plugins are gracefully shut down and re-initialized with new configuration

### Managing Resources with Shutdown Hooks

There are two ways to implement shutdown logic in your plugins:

#### 1. Override the `shutdown()` Method

For plugins with complex cleanup logic, override the `shutdown()` method:

```python
import httpx
from typing import Dict, Any

class MXCPPlugin(MXCPBasePlugin):
    def __init__(self, config: Dict[str, Any], user_context=None):
        super().__init__(config, user_context)
        # Initialize long-lived resources
        self.client = httpx.Client(
            base_url=config.get("api_url"),
            timeout=int(config.get("timeout", 30))
        )
        self.connection_pool = self._create_pool(config)
    
    def shutdown(self):
        """Called automatically on server shutdown or reload."""
        # Clean up resources in reverse order of initialization
        if hasattr(self, 'connection_pool'):
            self.connection_pool.close()
        if hasattr(self, 'client'):
            self.client.close()
    
    @udf
    def fetch_data(self, endpoint: str) -> str:
        """Fetch data using the persistent HTTP client."""
        response = self.client.get(endpoint)
        return response.text
```

#### 2. Use the `@on_shutdown` Decorator

For simpler cleanup tasks or when you need multiple cleanup functions:

```python
from mxcp.plugins import MXCPBasePlugin, udf, on_shutdown
import tempfile

class MXCPPlugin(MXCPBasePlugin):
    def __init__(self, config: Dict[str, Any], user_context=None):
        super().__init__(config, user_context)
        self.temp_dir = tempfile.mkdtemp()
        self.cache_file = open(f"{self.temp_dir}/cache.dat", "w")
    
    @on_shutdown
    def cleanup_temp_files(self):
        """Clean up temporary files on shutdown."""
        self.cache_file.close()
        import shutil
        shutil.rmtree(self.temp_dir)
    
    @on_shutdown
    def log_shutdown(self):
        """Log shutdown event."""
        import logging
        logging.info(f"Plugin shutting down: {self.__class__.__name__}")
```

### Important Notes

- Shutdown hooks are called in reverse order of plugin initialization
- The `@on_shutdown` decorator can be used multiple times in the same class
- Shutdown methods should handle errors gracefully and not raise exceptions
- Both `shutdown()` and `@on_shutdown` methods are called during hot reloads

## Advanced Examples

### File Processing Plugin

```python
import base64
from pathlib import Path
from typing import Dict, Any

class MXCPPlugin(MXCPBasePlugin):
    def __init__(self, config: Dict[str, Any], user_context=None):
        super().__init__(config, user_context)
        self.base_path = Path(config.get("base_path", "."))
    
    @udf
    def read_file(self, filename: str) -> str:
        """Read file contents as string."""
        file_path = self.base_path / filename
        if not file_path.exists():
            return f"File not found: {filename}"
        return file_path.read_text()
    
    @udf
    def read_file_base64(self, filename: str) -> str:
        """Read file contents as base64 encoded string."""
        file_path = self.base_path / filename
        if not file_path.exists():
            return f"File not found: {filename}"
        content = file_path.read_bytes()
        return base64.b64encode(content).decode('ascii')

    @udf
    def list_files(self, pattern: str) -> list[str]:
        """List files matching pattern."""
        return [str(p.name) for p in self.base_path.glob(pattern)]
```

### Web API Integration Plugin

```python
import httpx
from typing import Dict, Any

class MXCPPlugin(MXCPBasePlugin):
    def __init__(self, config: Dict[str, Any], user_context=None):
        super().__init__(config, user_context)
        self.api_key = config.get("api_key")
        self.base_url = config.get("base_url", "https://api.example.com")
    
    @udf
    def fetch_weather(self, city: str) -> str:
        """Fetch weather data for a city."""
        url = f"{self.base_url}/weather"
        params = {"q": city, "appid": self.api_key}
        
        with httpx.Client() as client:
            response = client.get(url, params=params)
            if response.status_code == 200:
                data = response.json()
                temp = data["main"]["temp"]
                desc = data["weather"][0]["description"]
                return f"{city}: {temp}°C, {desc}"
            else:
                return f"Error fetching weather for {city}"

    @udf  
    def geocode(self, address: str) -> dict[str, float]:
        """Geocode an address to lat/lng coordinates."""
        # Implementation would make API call and return coordinates
        # Return type maps to DuckDB MAP(VARCHAR, DOUBLE)
        return {"lat": 40.7128, "lng": -74.0060}
```

## SQL Usage Patterns

### Basic Function Calls

```sql
-- Simple function calls
SELECT encrypt_cipher('secret data') as encrypted;
SELECT process_text_utils('Hello World', 5) as processed;

-- Using with table data
SELECT 
    id,
    original_text,
    encrypt_cipher(original_text) as encrypted_text
FROM documents;
```

### Complex Data Processing

```sql
-- Working with arrays and maps
SELECT 
    list_files_processor('*.csv') as csv_files,
    geocode_location('123 Main St') as coordinates;

-- Using in WHERE clauses
SELECT * FROM users 
WHERE validate_email_utils(email_address) = true;

-- Aggregations with UDFs
SELECT 
    category,
    COUNT(*) as total,
    SUM(calculate_score_analytics(data_field)) as total_score
FROM analytics_data 
GROUP BY category;
```

### Authentication-Aware Queries

```sql
-- User-specific data processing
SELECT 
    id,
    title,
    encrypt_with_user_key_cipher(content) as encrypted_content
FROM documents
WHERE owner = get_username();

-- External API integration
SELECT fetch_user_repos_github() as repo_info;

-- Conditional processing based on authentication
SELECT 
    CASE 
        WHEN get_current_user_auth() != 'not authenticated' 
        THEN sensitive_process_secure(data)
        ELSE public_process_basic(data)
    END as processed_data
FROM public_data;
```

## Best Practices

### 1. Error Handling

Always handle errors gracefully in your UDFs:

```python
@udf
def safe_divide(self, a: float, b: float) -> float:
    """Safely divide two numbers."""
    try:
        if b == 0:
            return float('inf')  # or raise ValueError("Division by zero")
        return a / b
    except Exception as e:
        # Log error or return sentinel value
        return float('nan')
```

### 2. Configuration Validation

Validate configuration in your constructor:

```python
def __init__(self, config: Dict[str, Any], user_context=None):
    super().__init__(config, user_context)
    
    # Validate required configuration
    if "api_key" not in config:
        raise ValueError("api_key is required in plugin configuration")
    
    # Convert and validate types
    self.timeout = int(config.get("timeout", "30"))
    if self.timeout <= 0:
        raise ValueError("timeout must be positive")
```

### 3. Resource Management

Use context managers for short-lived resources within UDF calls, and the plugin lifecycle hooks for long-lived resources:

```python
# Short-lived resource: use context manager
@udf
def query_database(self, query: str) -> int:
    """Execute a one-off database query."""
    # Connection is created and closed for each call
    with psycopg2.connect(self._config["database_url"]) as conn:
        with conn.cursor() as cursor:
            cursor.execute(query)
            return cursor.rowcount

# Long-lived resource: use lifecycle hooks
class DatabasePlugin(MXCPBasePlugin):
    def __init__(self, config: Dict[str, Any], user_context=None):
        super().__init__(config, user_context)
        # Connection pool lives for the plugin's lifetime
        self.pool = psycopg2.pool.SimpleConnectionPool(
            1, 20, config["database_url"]
        )
    
    def shutdown(self):
        """Close connection pool on shutdown."""
        if hasattr(self, 'pool'):
            self.pool.closeall()
    
    @udf
    def query_pooled(self, query: str) -> int:
        """Execute query using connection pool."""
        conn = self.pool.getconn()
        try:
            with conn.cursor() as cursor:
                cursor.execute(query)
                return cursor.rowcount
        finally:
            self.pool.putconn(conn)
```

### 4. Type Safety

Always provide complete type hints:

```python
# Good - complete type hints
@udf
def process_data(self, items: list[str], limit: int) -> dict[str, int]:
    return {"processed": len(items[:limit])}

# Bad - missing type hints
@udf
def process_data(self, items, limit):  # This will be skipped!
    return {"processed": len(items[:limit])}
```

### 5. Documentation

Document your UDFs thoroughly:

```python
@udf
def complex_calculation(self, data: list[float], threshold: float) -> dict[str, float]:
    """Perform complex statistical calculation on data.
    
    Calculates mean, standard deviation, and percentage above threshold.
    
    Args:
        data: List of numeric values to analyze
        threshold: Threshold value for percentage calculation
        
    Returns:
        Dictionary with 'mean', 'std_dev', and 'pct_above_threshold'
        
    Example:
        SELECT complex_calculation_stats([1.0, 2.0, 3.0, 4.0], 2.5) as stats;
        -- Returns: {'mean': 2.5, 'std_dev': 1.29, 'pct_above_threshold': 50.0}
    """
    # Implementation...
```

## Deployment Considerations

### 1. Dependencies

Include a `requirements.txt` or specify dependencies clearly:

```text
httpx>=0.24.0
pandas>=1.5.0
requests>=2.28.0
```

### 2. Plugin Distribution

Plugins must be placed in the `plugins/` directory of your MXCP project. They can be distributed as:

- **Local modules**: Python files in your project's `plugins/` directory
- **Python packages**: Installable via pip into the `plugins/` directory
- **Git repositories**: Referenced via pip install from git URLs

**Directory Structure Example:**
```
my-mxcp-project/
├── mxcp-site.yml
├── python/                    # Python endpoints and shared code
├── plugins/                   # MXCP plugins for DuckDB
│   ├── my_plugin/
│   │   └── __init__.py
│   ├── utils/
│   │   └── string_plugin.py
│   └── integrations/
│       └── github.py
├── tools/
├── resources/
└── sql/
```

### 3. Environment Variables

Use environment variables for sensitive configuration:

```yaml
# User config
plugin:
  config:
    api_integration:
      api_key: "${SECRET_API_KEY}"
      database_url: "${DATABASE_URL}"
```

### 4. Testing

Test your plugins independently:

```python
# test_my_plugin.py
import pytest
from my_plugin import MXCPPlugin

def test_basic_functionality():
    config = {"rotation": "13"}
    plugin = MXCPPlugin(config)
    
    result = plugin.encrypt("hello")
    assert result == "uryyb"
    
    decrypted = plugin.decrypt(result)
    assert decrypted == "hello"
```

## Troubleshooting

### Common Issues

**1. Plugin Not Loading**
- Check that module is in Python path
- Verify `MXCPPlugin` class exists and inherits from `MXCPBasePlugin`
- Check configuration syntax in YAML files

**2. UDF Not Available in SQL**
- Ensure method has `@udf` decorator
- Verify complete type hints on method
- Check naming pattern: `{function_name}_{plugin_instance_name}`

**3. Type Errors**
- Ensure all UDF parameters and return values have type hints
- Use supported DuckDB types only
- Check for `Any` type annotations (not supported)

**4. Configuration Issues**
- Verify config name in site config matches user config
- Check environment variable syntax: `${VAR_NAME}`
- Ensure required configuration keys are present

### Debug Tips

**1. Enable Debug Logging**
```bash
mxcp serve --debug
```

**2. Check Plugin Loading**
Look for log messages like:
```
[...] Loaded plugin my_cipher from my_plugin
[...] Adding UDF: encrypt with args ['VARCHAR'] and return type VARCHAR
```

**3. Test SQL Functions**
```sql
-- List all available functions
SELECT function_name FROM duckdb_functions() WHERE function_name LIKE '%_pluginname';

-- Test function directly
SELECT encrypt_my_cipher('test') as result;
```

## Migration Guide

### From Legacy Plugins

If you have plugins without UserContext support:

```python
# Old style (still works)
class MXCPPlugin(MXCPBasePlugin):
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)

# New style (recommended)
class MXCPPlugin(MXCPBasePlugin):
    def __init__(self, config: Dict[str, Any], user_context=None):
        super().__init__(config, user_context)
```

The plugin loader automatically detects which constructor style your plugin uses and calls it appropriately.

## Examples Repository

Complete working examples are available in the `examples/plugin/` directory:

- **Caesar Cipher Plugin**: Basic text encryption/decryption
- **Configuration Examples**: User and site config setup
- **Authentication Integration**: Using UserContext features

## Next Steps

- Explore the `examples/plugin/` directory for hands-on examples
- Read the [Authentication Guide](../guides/authentication.md) to understand user context integration
- Check the [Configuration Guide](../guides/configuration.md) for advanced config management
- Review the [Type System](type-system.md) documentation for complex type mappings
