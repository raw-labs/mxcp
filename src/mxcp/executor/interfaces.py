"""Core interfaces for MXCP executor system.

This module provides the core interfaces for the MXCP executor system, which
handles execution of source code in different languages (SQL, Python, etc.)
with proper validation and lifecycle management.

Example usage:
    >>> from mxcp.executor import ExecutionEngine
    >>> from mxcp.core import ExecutionContext
    >>> from mxcp.executor.plugins import DuckDBExecutor, PythonExecutor
    >>> 
    >>> # Create engine and register executors
    >>> engine = ExecutionEngine(strict=False)
    >>> engine.register_executor(DuckDBExecutor())
    >>> engine.register_executor(PythonExecutor())
    >>> 
    >>> # Initialize with context (shared runtime information)
    >>> context = ExecutionContext(
    ...     user_config=user_config,
    ...     site_config=site_config,
    ...     user_context=user_context
    ... )
    >>> engine.startup(context)
    >>> 
    >>> # Execute SQL with validation
    >>> sql_schema = {
    ...     "input": [{"name": "limit", "type": "integer", "default": 10}],
    ...     "output": {"type": "array", "items": {"type": "object"}}
    ... }
    >>> result = await engine.execute(
    ...     language="sql",
    ...     source_code="SELECT * FROM table LIMIT $limit",
    ...     params={"limit": 5},
    ...     input_schema=sql_schema["input"],
    ...     output_schema=sql_schema["output"]
    ... )
    >>> 
    >>> # Execute Python with validation
    >>> python_schema = {
    ...     "input": [{"name": "data", "type": "array", "items": {"type": "number"}}],
    ...     "output": {"type": "number"}
    ... }
    >>> result = await engine.execute(
    ...     language="python",
    ...     source_code="return sum(data) / len(data)",
    ...     params={"data": [1, 2, 3, 4, 5]},
    ...     input_schema=python_schema["input"],
    ...     output_schema=python_schema["output"]
    ... )
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List, Union, TYPE_CHECKING
from pathlib import Path
import threading
from contextvars import ContextVar

if TYPE_CHECKING:
    from mxcp.validator import TypeValidator

from mxcp.core import ExecutionContext


class ExecutorPlugin(ABC):
    """Base interface for execution plugins.
    
    Each plugin handles a specific execution language/environment
    (e.g., SQL, Python, R) and manages its own internal resources
    (database sessions, plugins, locking, etc.)
    
    Executors are fully constructed and ready to use after instantiation.
    Higher-level components handle lifecycle management by creating/destroying instances.
    
    Example implementation:
        >>> from mxcp.executor.interfaces import ExecutorPlugin
        >>> from mxcp.core import ExecutionContext
        >>> 
        >>> class CustomExecutor(ExecutorPlugin):
        ...     def __init__(self, config):
        ...         # Create all internal resources in constructor
        ...         self._internal_session = self._create_session(config)
        ...         self._internal_plugins = self._load_plugins(config)
        ...     
        ...     @property
        ...     def language(self) -> str:
        ...         return "custom"
        ...     
        ...     async def execute(self, source_code: str, params: Dict[str, Any], 
        ...                     context: ExecutionContext) -> Any:
        ...         # Use internal session and plugins with dynamic user context
        ...         return self._internal_session.execute(source_code, params, context)
        ...     
        ...     def shutdown(self) -> None:
        ...         # Clean up internal resources
        ...         self._internal_session.close()
        ...         self._internal_plugins.clear()
    """

    @property
    @abstractmethod
    def language(self) -> str:
        """Return the language this executor handles (e.g., 'sql', 'python')."""
        pass

    @abstractmethod
    async def execute(
        self, 
        source_code: str, 
        params: Dict[str, Any],
        context: ExecutionContext
    ) -> Any:
        """Execute source code with the given parameters.
        
        Args:
            source_code: The source code to execute
            params: Parameters for the execution
            context: Execution context with user info and runtime state
            
        Returns:
            The result of the execution
        """
        pass

    @abstractmethod
    def shutdown(self) -> None:
        """Shut down the executor and clean up resources.
        
        This is called when the executor is being stopped.
        Executors should clean up their internal resources here.
        """
        pass


class ExecutionEngine:
    """Central execution engine that manages multiple executor plugins.
    
    The engine handles:
    - Registration of executor plugins for different languages
    - Input/output validation using mxcp.validator
    - Routing execution requests to appropriate executors
    
    Executors are ready to use immediately after registration.
    No separate startup step is required.
    
    Example usage:
        >>> from mxcp.executor import ExecutionEngine
        >>> from mxcp.core import ExecutionContext
        >>> from mxcp.executor.plugins import DuckDBExecutor, PythonExecutor
        >>> 
        >>> # Create engine and register executors (ready immediately)
        >>> engine = ExecutionEngine(strict=False)
        >>> engine.register_executor(DuckDBExecutor(...))
        >>> engine.register_executor(PythonExecutor(...))
        >>> 
        >>> # Execute code with validation
        >>> context = ExecutionContext(username="user", provider="github")
        >>> result = await engine.execute(
        ...     language="python",
        ...     source_code="return x + y",
        ...     params={"x": 1, "y": 2},
        ...     context=context,
        ...     input_schema=[
        ...         {"name": "x", "type": "integer"},
        ...         {"name": "y", "type": "integer"}
        ...     ],
        ...     output_schema={"type": "integer"}
        ... )
    """
    
    def __init__(self, strict: bool = False):
        """Initialize the execution engine.
        
        Args:
            strict: If True, validation errors will raise exceptions
        """
        self._executors: Dict[str, ExecutorPlugin] = {}
        self._strict = strict
        self._lock = threading.Lock()
        
    def register_executor(self, executor: ExecutorPlugin) -> None:
        """Register an executor plugin.
        
        Args:
            executor: The executor plugin to register (must be fully constructed)
            
        Raises:
            ValueError: If an executor for this language is already registered
        """
        language = executor.language
        if language in self._executors:
            raise ValueError(f"Executor for language '{language}' is already registered")
        self._executors[language] = executor
            
    def shutdown(self) -> None:
        """Shut down all registered executors."""
        with self._lock:
            for executor in self._executors.values():
                executor.shutdown()
            self._executors.clear()
                
    async def execute(
        self,
        language: str,
        source_code: str,
        params: Dict[str, Any],
        context: ExecutionContext,
        input_schema: Optional[List[Dict[str, Any]]] = None,
        output_schema: Optional[Dict[str, Any]] = None
    ) -> Any:
        """Execute source code in the specified language.
        
        Args:
            language: The programming language
            source_code: The source code to execute
            params: Parameters for the execution
            context: Execution context with user info and runtime state
            input_schema: Optional input validation schema
            output_schema: Optional output validation schema
            
        Returns:
            The result of the execution
            
        Raises:
            ValueError: If language is not supported or validation fails
        """
        if language not in self._executors:
            available = list(self._executors.keys())
            raise ValueError(f"Language '{language}' not supported. Available: {available}")
            
        # Validate input parameters if schema provided
        if input_schema:
            from mxcp.validator import TypeValidator
            validator = TypeValidator.from_dict({"input": {"parameters": input_schema}}, strict=self._strict)
            params = validator.validate_input(params)
            
        # Execute the code
        executor = self._executors[language]
        result = await executor.execute(source_code, params, context)
        
        # Validate output if schema provided
        if output_schema:
            from mxcp.validator import TypeValidator
            validator = TypeValidator.from_dict({"output": output_schema}, strict=self._strict)
            result = validator.validate_output(result)
            
        return result 