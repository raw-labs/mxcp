"""MXCP SDK Core - Configuration management and shared utilities.

This package provides core functionality shared across the SDK including:
- Configuration resolution with secret providers (Vault, 1Password, environment)
- Analytics and telemetry collection
- Common utilities and helpers
- Package version information

## Key Modules

### Configuration (`mxcp.sdk.core.config`)
- `ResolverEngine`: Resolves configuration references like `vault://`, `op://`, `env:`
- Secret providers: `VaultResolver`, `OnePasswordResolver`, `EnvResolver`, `FileResolver`
- Configuration loading and validation

### Analytics (`mxcp.sdk.core.analytics`)
- Usage tracking and telemetry collection
- Performance monitoring and timing decorators
- Privacy-focused analytics with opt-out support

### Version (`mxcp.sdk.core.version`)
- `PACKAGE_NAME`: The package name ("mxcp")
- `PACKAGE_VERSION`: The current package version
- `get_package_info()`: Get both name and version as a tuple

## Quick Examples

### Configuration Resolution
```python
from mxcp.sdk.core.config import ResolverEngine

# Create resolver engine
engine = ResolverEngine({
    'vault': {'enabled': True, 'address': 'https://vault.company.com'},
    'onepassword': {'enabled': True, 'token_env': 'OP_SERVICE_ACCOUNT_TOKEN'}
})

# Resolve configuration references
config = {
    'database_url': 'env:DATABASE_URL',
    'api_key': 'vault://secret/api#key',
    'password': 'op://vault/item/password'
}

with engine:
    resolved = engine.resolve_references(config)
    # All references are now resolved to actual values
```

### Analytics Tracking
```python
from mxcp.sdk.core.analytics import track_event, track_timing

# Track custom events
track_event("tool_executed", {
    "tool_name": "query_database",
    "execution_time_ms": 150,
    "success": True
})

# Track function timing
@track_timing("expensive_operation")
def expensive_operation():
    # ... time-consuming work ...
    pass
```

### Version Information
```python
from mxcp.sdk.core.version import PACKAGE_NAME, PACKAGE_VERSION

print(f"{PACKAGE_NAME} version {PACKAGE_VERSION}")
# Output: mxcp version 0.4.0
```
"""

# Export version utilities for easy access
from .version import PACKAGE_NAME, PACKAGE_VERSION, get_package_info

__all__ = ["PACKAGE_NAME", "PACKAGE_VERSION", "get_package_info"]
