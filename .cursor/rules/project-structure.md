# MXCP Project Structure

This document describes the organization of the MXCP codebase and where different types of code should be placed.

## Overview

MXCP is organized into two main parts:
- **`mxcp.server`**: The MCP server implementation (all server-side functionality)
- **`mxcp.sdk`**: Standalone SDK for building MCP tools (can be used independently)

There are also two top-level modules for backward compatibility:
- **`mxcp.runtime`**: Extension system hooks (kept at top-level for third-party compatibility)
- **`mxcp.plugins`**: Plugin base classes (kept at top-level for third-party compatibility)

## Directory Structure

```
src/mxcp/
├── __main__.py         # CLI entry point
├── runtime/            # Extension system (backward compatibility)
│   └── __init__.py     # Hooks: on_init, on_shutdown, config, db, plugins
├── plugins/            # Plugin system (backward compatibility)
│   ├── __init__.py
│   ├── base.py         # MXCPBasePlugin class
│   └── _types.py       # Plugin types
├── server/             # All server implementation
│   ├── __init__.py
│   ├── core/           # Core utilities and configuration
│   ├── definitions/    # Static definitions (endpoints, evals)
│   ├── executor/       # Execution engine and runners
│   ├── interfaces/     # External interfaces (CLI, MCP server)
│   ├── schemas/        # JSON schemas
│   └── services/       # Business logic services
└── sdk/                # Standalone SDK
    ├── __init__.py
    ├── audit/          # Audit logging system
    ├── auth/           # Authentication framework
    ├── core/           # SDK core utilities
    ├── evals/          # LLM evaluation framework
    ├── executor/       # Execution interfaces and plugins
    ├── policy/         # Policy enforcement
    └── validator/      # Type validation system
```

## Where to Put Code

### Server Code (`mxcp.server.*`)

All server-specific functionality goes under `mxcp.server`:

#### `mxcp.server.core/`
- **Purpose**: Core utilities, configuration management, and shared types
- **What goes here**:
  - Configuration loading and parsing (`config/`)
  - External reference resolution (`refs/`)
  - Authentication helpers (`auth/`)
  - Shared type definitions
- **Example**: `mxcp.server.core.config.site_config`

#### `mxcp.server.definitions/`
- **Purpose**: Static definitions loaded from YAML/JSON files
- **What goes here**:
  - Endpoint definitions and loaders (`endpoints/`)
  - Evaluation suite definitions (`evals/`)
  - Definition utilities and types
- **Example**: `mxcp.server.definitions.endpoints.loader`

#### `mxcp.server.executor/`
- **Purpose**: Low-level execution engine
- **What goes here**:
  - Execution engine factory (`engine.py`)
  - Session management (`session/`)
  - Core execution runners (`runners/`)
- **Example**: `mxcp.server.executor.engine.create_execution_engine()`

#### `mxcp.server.interfaces/`
- **Purpose**: External interfaces to the server
- **What goes here**:
  - CLI commands (`cli/`)
  - MCP server implementation (`server/`)
  - Interface utilities
- **Example**: `mxcp.server.interfaces.cli.run`



#### `mxcp.server.schemas/`
- **Purpose**: JSON schemas for validation
- **What goes here**:
  - All JSON schema files (`*.json`)
  - Python schema definitions (e.g., `audit.py`)
- **Example**: `mxcp.server.schemas.tool-schema-1.json`

#### `mxcp.server.services/`
- **Purpose**: High-level business services organized by feature
- **Structure**: Each service has a folder with `service.py` as the entry point
- **What goes here**:
  - Endpoint execution and validation (`endpoints/service.py` + `endpoints/validator.py`)
  - Test execution service (`tests/service.py`)
  - Evaluation service (`evals/service.py`)
  - Audit utilities (`audit/` - exporters, utils, no service.py as CLI works directly with SDK)
  - Drift detection (`drift/`)
  - DBT integration (`dbt/`)
- **Pattern**: Use `<feature>/service.py` for main logic (exception: audit uses utilities directly)
- **Example**: `mxcp.server.services.endpoints.execute_endpoint()`

### SDK Code (`mxcp.sdk.*`)

The SDK is designed to be standalone and should NEVER import from `mxcp.server.*`:

#### `mxcp.sdk.audit/`
- **Purpose**: Schema-based audit logging
- **What goes here**:
  - Audit logger and types
  - Audit backends (`backends/`)
  - Redaction strategies
- **Helpers**: Future wrappers could go in `mxcp.sdk.audit.wrappers/`

#### `mxcp.sdk.auth/`
- **Purpose**: Authentication and authorization
- **What goes here**:
  - Auth base classes and context
  - OAuth providers (`providers/`)
  - Middleware and persistence
- **Example**: `mxcp.sdk.auth.providers.github.GitHubOAuthHandler`

#### `mxcp.sdk.core/`
- **Purpose**: SDK-specific core utilities
- **What goes here**:
  - Configuration management (`config/`)
  - Analytics (`analytics/`)
  - SDK-specific utilities
- **Note**: This is separate from `mxcp.server.core`

#### `mxcp.sdk.executor/`
- **Purpose**: Execution interfaces and plugins
- **What goes here**:
  - Execution engine interface
  - Executor plugins (`plugins/`)
  - Execution context
- **Example**: `mxcp.sdk.executor.ExecutionEngine`

#### `mxcp.sdk.policy/`
- **Purpose**: Policy enforcement framework
- **What goes here**:
  - Policy types and enforcer
  - Policy evaluation logic
- **Example**: `mxcp.sdk.policy.PolicyEnforcer`

#### `mxcp.sdk.validator/`
- **Purpose**: Type validation and conversion
- **What goes here**:
  - Core validator (`core.py`, `converters.py`)
  - Type definitions (`_types.py`)
  - **Decorators** go in `decorators/` submodule
- **Example**: `mxcp.sdk.validator.TypeValidator`

### Extension System (`mxcp.runtime`)

**IMPORTANT**: This is kept at the top level for backward compatibility with third-party code.

- **Purpose**: Runtime hooks for extensions
- **What goes here**: Nothing new - this is a stable API
- **Available hooks**:
  - `@on_init`: Register initialization hooks
  - `@on_shutdown`: Register shutdown hooks
  - `config`: Access configuration
  - `db`: Access database session
  - `plugins`: Access loaded plugins

### Plugin System (`mxcp.plugins`)

**IMPORTANT**: This is kept at the top level for backward compatibility with third-party code.

- **Purpose**: Base classes for creating DuckDB plugins
- **What goes here**: Nothing new - this is a stable API
- **Available classes**:
  - `MXCPBasePlugin`: Base class for DuckDB plugins
  - `@udf`: Decorator for user-defined functions
  - `@on_shutdown`: Decorator for plugin shutdown hooks

## Import Rules

### For Server Code
- ✅ Can import from `mxcp.server.*`
- ✅ Can import from `mxcp.sdk.*`
- ✅ Can import from `mxcp.runtime`
- ✅ Can import from `mxcp.plugins`

### For SDK Code
- ❌ NEVER import from `mxcp.server.*`
- ✅ Can import from other `mxcp.sdk.*` modules
- ⚠️  Can import from `mxcp.runtime` only in executor plugins
- ✅ Can import from `mxcp.plugins` (for DuckDB plugin support)
- ⚠️  If you need types from server, copy them to SDK to maintain isolation

### For Extensions (Third-party code)
- ✅ Import from `mxcp.runtime`
- ✅ Import from `mxcp.plugins`
- ✅ Import from `mxcp.sdk.*` if using SDK features

## Adding New Features

### Server Feature
1. Determine the appropriate `mxcp.server.*` submodule
2. If it's a new service:
   - Create a folder under `mxcp.server.services/<feature>/`
   - Add `service.py` as the main entry point
   - Create `__init__.py` to export main functions
   - Add supporting modules (utils, types) in same folder
3. If it's a new interface, add to `mxcp.server.interfaces/`
4. Update imports to use full paths

### SDK Feature
1. Ensure it has no dependencies on `mxcp.server.*`
2. Place in appropriate `mxcp.sdk.*` submodule
3. If it's a high-level helper (like decorators), use a submodule
4. Document in the SDK module's `__init__.py`

### Extension Hook
1. Only add to `mxcp.runtime` if absolutely necessary
2. Maintain backward compatibility
3. Document thoroughly as this is a public API

## Testing Structure

```
tests/
├── sdk/                # SDK-specific tests
│   ├── audit/
│   ├── auth/
│   ├── core/
│   ├── evals/
│   ├── executor/
│   ├── policy/
│   ├── validator/      # Includes schema comparison tests
│   └── fixtures/       # SDK test fixtures
└── server/             # Server tests
    ├── fixtures/       # Server test fixtures
    └── test_*.py       # All server test files
```

**Note**: Tests should be placed based on what they're testing:
- SDK functionality → `tests/sdk/`
- Server functionality → `tests/server/`
- No separate top-level test directories

## Future Considerations

The current structure supports future packaging options:
1. **Monolithic**: `pip install mxcp` (current)
2. **Separate packages**: `pip install mxcp-server` + `pip install mxcp-sdk`
3. **Optional SDK**: `pip install mxcp[sdk]`

The clear separation between `mxcp.server` and `mxcp.sdk` makes any of these options possible without major refactoring.
