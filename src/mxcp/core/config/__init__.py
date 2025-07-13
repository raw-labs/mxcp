"""
Core configuration module with resolver support.

The mxcp.core.config module provides a comprehensive, plugin-based configuration 
system designed for enterprise applications that need to securely manage external 
references to secrets, environment variables, files, and other configuration sources.

## Architecture Overview

The module implements a two-stage configuration approach:

1. **Resolver Configuration**: Load settings for external services (Vault, 1Password, etc.)
2. **Application Configuration**: Process app configs with reference resolution and tracking

This separation allows secure credential management while keeping application 
configurations clean and portable across environments.

## Key Components

### ResolverEngine
The main orchestrator that coordinates resolver plugins, tracks references, 
and provides the primary API for configuration processing.

### ResolverPlugin System  
Extensible plugin architecture allowing custom resolvers for any external 
reference type. Built-in resolvers handle common patterns:

- Environment variables: `${VAR_NAME}`
- Files: `file://path/to/file` 
- HashiCorp Vault: `vault://secret/path#key`
- 1Password: `op://vault/item/field`

### Reference Tracking
Comprehensive tracking of all resolved references including success/failure 
status, timing, and detailed error information for debugging and monitoring.

## Quick Start

```python
from mxcp.core.config import ResolverEngine

# Basic usage with default configuration  
with ResolverEngine() as engine:
    config = {
        'database': {
            'host': '${DB_HOST}',
            'password': 'vault://secret/db#password'
        }
    }
    
    resolved = engine.process_config(config)
    print(resolved['database']['host'])  # Resolved from environment
```

## Configuration Format

Resolver configuration uses YAML format:

```yaml
config:
  vault:
    enabled: true
    address: "https://vault.example.com"
    token_env: "VAULT_TOKEN"
  onepassword:
    enabled: true  
    token_env: "OP_SERVICE_ACCOUNT_TOKEN"
```

## Advanced Features

### Reference Tracking
Monitor and debug configuration resolution:

```python
engine = ResolverEngine()
resolved = engine.process_config(config, track_references=True)

# Get detailed tracking information
references = engine.get_resolved_references()
failed_refs = engine.get_failed_references() 
summary = engine.get_reference_summary()
```

### Custom Resolvers
Extend the system with custom resolver plugins:

```python
from mxcp.core.config import ResolverPlugin

class CustomResolver(ResolverPlugin):
    @property
    def name(self) -> str:
        return "custom"
    
    # Implement required methods...

engine = ResolverEngine()
engine.register_resolver(CustomResolver())
```

### Schema Validation
Validate resolved configurations against JSON schemas:

```python
resolved = engine.process_file(
    "app.yaml",
    schema_file="app-schema.json"
)
```

## Error Handling

The system gracefully handles resolution failures:
- Failed references preserve original values
- Detailed error tracking available
- Warning logs for debugging
- No exceptions raised for individual failures

## Resource Management

Automatic cleanup of external clients:

```python
# Preferred: Context manager
with ResolverEngine.from_config_file("config.yaml") as engine:
    result = engine.process_config(config)
    # Automatic cleanup

# Alternative: Explicit cleanup  
engine = ResolverEngine()
try:
    result = engine.process_config(config)
finally:
    engine.cleanup()
```

## Security Considerations

- Credentials are loaded from environment variables, never hardcoded
- Vault and 1Password tokens are handled securely 
- Failed resolutions don't expose credential information in logs
- Reference tracking can be disabled in production if needed

## Production Usage

For production deployments:
- Use context managers for proper resource cleanup
- Enable reference tracking for monitoring and debugging  
- Configure appropriate logging levels
- Validate configurations with JSON schemas
- Monitor failed references for security incidents

## Module Exports

The module exports all necessary components for configuration processing:

- **ResolverEngine**: Main configuration processor
- **ResolverPlugin**: Base class for custom resolvers  
- **Built-in Resolvers**: EnvResolver, FileResolver, VaultResolver, OnePasswordResolver
- **Types**: ResolverConfig, ResolvedReference
- **Utilities**: load_resolver_config, ResolverRegistry

See individual class documentation for detailed usage information.
"""

from .types import ResolverConfig
from .loader import load_resolver_config
from .plugins import ResolverPlugin, ResolverRegistry
from .processor import ResolverEngine, ResolvedReference
from .resolvers import EnvResolver, FileResolver, VaultResolver, OnePasswordResolver

__all__ = [
    # Types
    'ResolverConfig',
    'ResolvedReference',
    
    # Core classes
    'ResolverEngine',
    'ResolverPlugin',
    'ResolverRegistry',
    
    # Built-in resolvers
    'EnvResolver',
    'FileResolver',
    'VaultResolver',
    'OnePasswordResolver',
    
    # Utilities
    'load_resolver_config',
] 