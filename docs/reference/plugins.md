---
title: "Plugin Reference"
description: "Extend MXCP with custom DuckDB plugins. User Defined Functions, type mapping, authentication integration, and lifecycle management."
sidebar:
  order: 5
---

MXCP plugins extend DuckDB with custom User Defined Functions (UDFs) written in Python. Plugins provide domain-specific functionality, API integrations, and custom data processing.

## Overview

Plugins are Python modules that:
- Inherit from `MXCPBasePlugin`
- Use `@udf` decorator to expose methods as SQL functions
- Support automatic DuckDB type mapping
- Access authenticated user context
- Have lifecycle hooks for resource management

## Quick Start

### 1. Define Plugin in Site Config

```yaml
# mxcp-site.yml
plugin:
  - name: my_cipher           # Instance name
    module: my_plugin         # Python module
    config: dev_config        # Config reference
```

### 2. Configure Settings

```yaml
# ~/.mxcp/config.yml
projects:
  my-project:
    profiles:
      dev:
        plugin:
          config:
            dev_config:
              rotation: "13"
              enable_logging: "true"
```

### 3. Create Plugin Module

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
        # Implementation
        result = []
        for char in text:
            if char.isalpha():
                base = ord('A') if char.isupper() else ord('a')
                result.append(chr((ord(char) - base + shift) % 26 + base))
            else:
                result.append(char)
        return ''.join(result)
```

### 4. Use in SQL

Functions are named `{function_name}_{plugin_instance_name}`:

```sql
SELECT encrypt_my_cipher('Hello World') as encrypted;
SELECT decrypt_my_cipher(encrypted) as decrypted;
```

## Configuration

### Site Configuration

```yaml
# mxcp-site.yml
plugin:
  - name: string_utils        # Required: Instance name
    module: utils.strings     # Required: Python module
    config: default           # Optional: Config name

  - name: api_client
    module: integrations.api
    config: api_settings

  - name: simple_plugin
    module: simple            # No config = empty {}
```

### User Configuration

```yaml
# ~/.mxcp/config.yml
projects:
  my-project:
    profiles:
      dev:
        plugin:
          config:
            default:
              api_key: "${API_KEY}"       # Environment variable
              timeout: "30"
              debug: "true"

            api_settings:
              base_url: "https://api.example.com"
              rate_limit: "100"
```

## Plugin Structure

### Required Elements

```python
from typing import Dict, Any
from mxcp.plugins import MXCPBasePlugin, udf

class MXCPPlugin(MXCPBasePlugin):
    def __init__(self, config: Dict[str, Any], user_context=None):
        super().__init__(config, user_context)
        # Initialize plugin state

    @udf
    def my_function(self, param: str) -> str:
        """Function documentation."""
        return process(param)
```

### UDF Requirements

- Must have `@udf` decorator
- Complete type hints for all parameters and return
- First parameter is `self` (handled automatically)
- Type hints generate DuckDB signatures

## Type Mapping

### Basic Types

| Python Type | DuckDB Type | Example |
|-------------|-------------|---------|
| `str` | `VARCHAR` | `"hello"` |
| `int` | `INTEGER` | `42` |
| `float` | `DOUBLE` | `3.14` |
| `bool` | `BOOLEAN` | `True` |
| `bytes` | `BLOB` | `b"data"` |

### Date/Time Types

| Python Type | DuckDB Type | Example |
|-------------|-------------|---------|
| `date` | `DATE` | `date(2024, 1, 1)` |
| `time` | `TIME` | `time(14, 30)` |
| `datetime` | `TIMESTAMP` | `datetime.now()` |
| `timedelta` | `INTERVAL` | `timedelta(hours=1)` |

### Complex Types

| Python Type | DuckDB Type | Example |
|-------------|-------------|---------|
| `list[T]` | `T[]` | `[1, 2, 3]` |
| `dict[K, V]` | `MAP(K, V)` | `{"key": "value"}` |
| `Optional[T]` | Nullable `T` | `None` or value |

### Struct Types

```python
from dataclasses import dataclass

@dataclass
class UserInfo:
    name: str
    age: int
    active: bool

@udf
def create_user(self, name: str, age: int) -> UserInfo:
    return UserInfo(name=name, age=age, active=True)
```

## Authentication Integration

### Accessing User Context

```python
class MXCPPlugin(MXCPBasePlugin):
    def __init__(self, config: Dict[str, Any], user_context=None):
        super().__init__(config, user_context)

    @udf
    def get_current_user(self) -> str:
        """Get authenticated user's username."""
        if self.is_authenticated():
            return self.get_username() or "unknown"
        return "not authenticated"
```

### User Context Methods

```python
# Check authentication
self.is_authenticated() -> bool

# User information
self.get_username() -> Optional[str]
self.get_user_email() -> Optional[str]
self.get_user_provider() -> Optional[str]  # 'github', 'atlassian', etc.

# OAuth token for API calls
self.get_user_token() -> Optional[str]

# Full context object
self.user_context -> Optional[UserContext]
```

### External API Calls

```python
import httpx

@udf
async def fetch_user_repos(self) -> str:
    """Fetch GitHub repositories using user's token."""
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

## Lifecycle Management

### Shutdown Hook (Override Method)

```python
import httpx

class MXCPPlugin(MXCPBasePlugin):
    def __init__(self, config: Dict[str, Any], user_context=None):
        super().__init__(config, user_context)
        self.client = httpx.Client(base_url=config.get("api_url"))

    def shutdown(self):
        """Called on server shutdown or reload."""
        if hasattr(self, 'client'):
            self.client.close()

    @udf
    def fetch_data(self, endpoint: str) -> str:
        return self.client.get(endpoint).text
```

### Shutdown Hook (Decorator)

```python
from mxcp.plugins import MXCPBasePlugin, udf, on_shutdown
import tempfile
import shutil

class MXCPPlugin(MXCPBasePlugin):
    def __init__(self, config: Dict[str, Any], user_context=None):
        super().__init__(config, user_context)
        self.temp_dir = tempfile.mkdtemp()

    @on_shutdown
    def cleanup_temp(self):
        """Clean up temporary files."""
        shutil.rmtree(self.temp_dir)

    @on_shutdown
    def log_shutdown(self):
        """Log shutdown event."""
        print(f"Plugin {self.__class__.__name__} shutting down")
```

## Advanced Examples

### File Processing Plugin

```python
import base64
from pathlib import Path

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
        """Read file contents as base64."""
        file_path = self.base_path / filename
        if not file_path.exists():
            return f"File not found: {filename}"
        return base64.b64encode(file_path.read_bytes()).decode('ascii')

    @udf
    def list_files(self, pattern: str) -> list[str]:
        """List files matching pattern."""
        return [str(p.name) for p in self.base_path.glob(pattern)]
```

### Web API Plugin

```python
import httpx

class MXCPPlugin(MXCPBasePlugin):
    def __init__(self, config: Dict[str, Any], user_context=None):
        super().__init__(config, user_context)
        self.api_key = config.get("api_key")
        self.base_url = config.get("base_url")

    @udf
    def fetch_weather(self, city: str) -> str:
        """Fetch weather data for a city."""
        with httpx.Client() as client:
            response = client.get(
                f"{self.base_url}/weather",
                params={"q": city, "appid": self.api_key}
            )
            if response.status_code == 200:
                data = response.json()
                return f"{city}: {data['main']['temp']}C"
            return f"Error fetching weather for {city}"

    @udf
    def geocode(self, address: str) -> dict[str, float]:
        """Geocode address to coordinates."""
        # Returns MAP(VARCHAR, DOUBLE) in DuckDB
        return {"lat": 40.7128, "lng": -74.0060}
```

## SQL Usage Patterns

### Basic Usage

```sql
-- Simple function call
SELECT encrypt_cipher('secret') as encrypted;

-- With table data
SELECT
    id,
    original_text,
    encrypt_cipher(original_text) as encrypted
FROM documents;
```

### Complex Queries

```sql
-- Arrays and maps
SELECT
    list_files_processor('*.csv') as csv_files,
    geocode_location('123 Main St') as coords;

-- WHERE clause
SELECT * FROM users
WHERE validate_email_utils(email) = true;

-- Aggregations
SELECT
    category,
    SUM(calculate_score_analytics(data)) as total_score
FROM analytics
GROUP BY category;
```

### Authentication-Aware

```sql
-- User-specific processing
SELECT
    id,
    encrypt_with_user_cipher(content) as encrypted
FROM documents
WHERE owner = get_username();

-- External API
SELECT fetch_user_repos_github() as repos;
```

## Best Practices

### 1. Error Handling

```python
@udf
def safe_divide(self, a: float, b: float) -> float:
    try:
        if b == 0:
            return float('inf')
        return a / b
    except Exception:
        return float('nan')
```

### 2. Configuration Validation

```python
def __init__(self, config: Dict[str, Any], user_context=None):
    super().__init__(config, user_context)

    if "api_key" not in config:
        raise ValueError("api_key is required")

    self.timeout = int(config.get("timeout", "30"))
    if self.timeout <= 0:
        raise ValueError("timeout must be positive")
```

### 3. Resource Management

```python
# Short-lived: context manager
@udf
def query_db(self, query: str) -> int:
    with psycopg2.connect(self._config["url"]) as conn:
        with conn.cursor() as cur:
            cur.execute(query)
            return cur.rowcount

# Long-lived: lifecycle hooks
class DatabasePlugin(MXCPBasePlugin):
    def __init__(self, config: Dict[str, Any], user_context=None):
        super().__init__(config, user_context)
        self.pool = create_pool(config["url"])

    def shutdown(self):
        self.pool.close()
```

### 4. Complete Type Hints

```python
# Good - complete hints
@udf
def process(self, items: list[str], limit: int) -> dict[str, int]:
    return {"processed": len(items[:limit])}

# Bad - missing hints (will be skipped!)
@udf
def process(self, items, limit):
    return {"processed": len(items[:limit])}
```

### 5. Documentation

```python
@udf
def complex_calc(self, data: list[float], threshold: float) -> dict[str, float]:
    """Perform statistical calculation on data.

    Calculates mean, std dev, and percentage above threshold.

    Args:
        data: List of numeric values
        threshold: Threshold for percentage calculation

    Returns:
        Dictionary with 'mean', 'std_dev', 'pct_above_threshold'

    Example:
        SELECT complex_calc_stats([1.0, 2.0, 3.0], 2.0);
    """
    # Implementation
```

## Project Structure

```
my-project/
├── mxcp-site.yml
├── plugins/
│   ├── my_plugin/
│   │   └── __init__.py
│   ├── utils/
│   │   └── strings.py
│   └── integrations/
│       └── api.py
├── tools/
├── resources/
└── sql/
```

## Troubleshooting

### Plugin Not Loading

- Check module is in `plugins/` directory
- Verify `MXCPPlugin` class exists
- Check YAML syntax

### UDF Not Available

- Ensure `@udf` decorator
- Verify complete type hints
- Check naming: `{function}_{instance_name}`

### Type Errors

- All parameters need type hints
- Use supported DuckDB types
- Avoid `Any` type

### Configuration Issues

- Config name must match user config
- Check `${VAR}` syntax for env vars
- Verify required keys exist

### Debug

```bash
# Enable debug logging
mxcp serve --debug
```

```sql
-- List available functions
SELECT function_name FROM duckdb_functions()
WHERE function_name LIKE '%_pluginname';
```

## Next Steps

- [Python Reference](python) - Runtime API
- [SQL Reference](sql) - SQL capabilities
- [Authentication](/security/authentication) - User context
