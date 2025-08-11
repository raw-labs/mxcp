"""MXCP SDK Executor - Multi-language code execution engine.

This module provides the core execution framework for MXCP, including:
- `ExecutionContext`: Runtime context for execution state (sessions, configs, plugins)
- `ExecutorPlugin`: Base interface for execution plugins  
- `ExecutionEngine`: Main engine for executing code across different languages

The executor system supports multiple languages through a plugin architecture,
with built-in support for SQL (via DuckDB) and Python execution.

## Quick Examples

### Basic Execution
```python
from mxcp.sdk.executor import ExecutionEngine, ExecutionContext
from mxcp.sdk.auth import UserContext

# Create engine and context
engine = ExecutionEngine()
context = ExecutionContext()

# Set user context
user = UserContext(username="alice", role="analyst")
context.set_user_context(user)

# Execute SQL
result = await engine.execute(
    language="sql",
    source_code="SELECT COUNT(*) as user_count FROM users",
    params={},
    context=context
)

# Execute Python
result = await engine.execute(
    language="python", 
    source_code="return {'result': len(params.get('items', []))}",
    params={"items": [1, 2, 3]},
    context=context
)
```

### Context Management  
```python
from mxcp.sdk.executor import get_execution_context, set_execution_context

# Access current execution context
context = get_execution_context()
user = context.get_user_context()
db_session = context.get("duckdb_session")
```
"""

from .context import (
    ExecutionContext,
    get_execution_context,
    set_execution_context,
    reset_execution_context
)
from .interfaces import ExecutorPlugin, ExecutionEngine

__all__ = [
    # Context
    "ExecutionContext",
    "get_execution_context",
    "set_execution_context",
    "reset_execution_context",
    
    # Interfaces
    "ExecutorPlugin",
    "ExecutionEngine",
] 