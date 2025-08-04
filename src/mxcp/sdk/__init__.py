# -*- coding: utf-8 -*-
"""MXCP SDK - Enterprise-grade MCP framework for building production AI tools.

The MXCP SDK provides a comprehensive, standalone framework for building secure,
scalable AI applications with built-in authentication, policy enforcement, 
audit logging, and execution engines.

## Core Modules

### Authentication (`mxcp.sdk.auth`)
OAuth providers, user context management, and authentication middleware.

### Execution (`mxcp.sdk.executor`)  
Multi-language execution engine with DuckDB and Python support.

### Policy Enforcement (`mxcp.sdk.policy`)
CEL-based policy engine for input validation and output filtering.

### Audit Logging (`mxcp.sdk.audit`)
Enterprise-grade audit trails for all operations.

### Type Validation (`mxcp.sdk.validator`)
OpenAPI-style schema validation for inputs and outputs.

### LLM Integration (`mxcp.sdk.evals`)
LLM execution framework with tool calling support.

### Configuration (`mxcp.sdk.core`)
Configuration management with secret resolvers and analytics.

## Quick Start

```python
from mxcp.sdk.executor import ExecutionEngine, ExecutionContext
from mxcp.sdk.auth import UserContext
from mxcp.sdk.policy import PolicyEnforcer, PolicySet

# Set up execution engine
engine = ExecutionEngine()
context = ExecutionContext()

# Add user context
user = UserContext(username="alice", role="analyst")
context.set_user_context(user)

# Execute code with policy enforcement
result = await engine.execute(
    language="sql",
    source_code="SELECT * FROM users WHERE active = true",
    params={},
    context=context
)
```

## Design Principles

- **Security First**: Built-in authentication, authorization, and audit logging
- **Type Safety**: Comprehensive validation with clear error messages  
- **Plugin Architecture**: Extensible execution engines and auth providers
- **Zero Dependencies**: Clean separation from main MXCP CLI package
- **Production Ready**: Thread-safe, async-compatible, enterprise features
""" 