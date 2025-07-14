"""Core interfaces for MXCP executor system.

This module provides the core interfaces for the MXCP executor system, which
handles execution of source code in different languages (SQL, Python, etc.)
with proper validation and lifecycle management.

Example usage:
    >>> from mxcp.executor import ExecutionEngine, ExecutionContext
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
    from mxcp.config.user_config import UserConfig
    from mxcp.config.site_config import SiteConfig
    from mxcp.auth.providers import UserContext


class ExecutionContext:
    """Runtime context for execution environments.
    
    Provides access to shared runtime information like configuration
    and user context. Each executor handles its own internal concerns
    (database sessions, plugins, locking, etc.)
    
    Example usage:
        >>> from mxcp.executor import ExecutionContext
        >>> 
        >>> # Create context with shared runtime information
        >>> context = ExecutionContext(
        ...     user_config=user_config,
        ...     site_config=site_config,
        ...     user_context=user_context
        ... )
        >>> 
        >>> # Access configuration
        >>> project = context.site_config.get("project")
        >>> profile = context.site_config.get("profile")
        >>> 
        >>> # Access user information
        >>> if context.user_context:
        ...     username = context.user_context.username
        ...     provider = context.user_context.provider
    """
    
    def __init__(
        self,
        user_config: Optional['UserConfig'] = None,
        site_config: Optional['SiteConfig'] = None,
        user_context: Optional['UserContext'] = None
    ):
        """Initialize execution context.
        
        Args:
            user_config: User configuration
            site_config: Site configuration
            user_context: Authenticated user context
        """
        self.user_config = user_config
        self.site_config = site_config
        self.user_context = user_context
    
    def get_secret(self, key: str) -> Optional[Dict[str, Any]]:
        """Get secret from user configuration.
        
        Args:
            key: Secret name to retrieve
            
        Returns:
            Secret parameters dictionary or None if not found
        """
        if not self.user_config or not self.site_config:
            return None
            
        try:
            project = self.site_config.get("project")
            profile = self.site_config.get("profile")
            if not project or not profile:
                return None
                
            project_config = self.user_config["projects"][project]
            profile_config = project_config["profiles"][profile]
            secrets = profile_config.get("secrets", [])
            
            if not secrets:
                return None
                
            for secret in secrets:
                if secret.get("name") == key:
                    return secret.get("parameters", {})
                    
            return None
        except (KeyError, TypeError):
            return None


class ExecutorPlugin(ABC):
    """Base interface for execution plugins.
    
    Each plugin handles a specific execution language/environment
    (e.g., SQL, Python, R) and manages its own internal resources
    (database sessions, plugins, locking, etc.)
    
    Example implementation:
        >>> from mxcp.executor.interfaces import ExecutorPlugin, ExecutionContext
        >>> 
        >>> class CustomExecutor(ExecutorPlugin):
        ...     def __init__(self):
        ...         self._internal_session = None
        ...         self._internal_plugins = {}
        ...     
        ...     @property
        ...     def language(self) -> str:
        ...         return "custom"
        ...     
        ...     async def execute(self, source_code: str, params: Dict[str, Any], 
        ...                     context: ExecutionContext) -> Any:
        ...         # Use internal session and plugins
        ...         return self._internal_session.execute(source_code, params)
        ...     
        ...     def startup(self, context: ExecutionContext) -> None:
        ...         # Create internal resources using context config
        ...         self._internal_session = self._create_session(context)
        ...         self._internal_plugins = self._load_plugins(context)
        ...     
        ...     def shutdown(self) -> None:
        ...         # Clean up internal resources
        ...         if self._internal_session:
        ...             self._internal_session.close()
        ...         self._internal_plugins.clear()
        ...     
        ...     def reload(self, context: ExecutionContext) -> None:
        ...         # Reload internal resources with new context
        ...         self.shutdown()
        ...         self.startup(context)
    """
    
    @property
    @abstractmethod
    def language(self) -> str:
        """The language this executor handles (e.g., 'sql', 'python')."""
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
            params: Input parameters (already validated)
            context: Runtime context with shared information
            
        Returns:
            Execution result (will be validated by engine)
        """
        pass
    
    @abstractmethod
    def startup(self, context: ExecutionContext) -> None:
        """Initialize the executor with runtime context.
        
        Called when the engine starts up. Should create any internal
        resources needed for execution using the provided context.
        
        Args:
            context: Runtime context with shared information
        """
        pass
    
    @abstractmethod
    def shutdown(self) -> None:
        """Clean up executor resources.
        
        Called when the engine shuts down. Should clean up any internal
        resources that were allocated during startup.
        """
        pass
    
    @abstractmethod
    def reload(self, context: ExecutionContext) -> None:
        """Reload executor with new context.
        
        Called when the engine receives a reload signal (e.g., SIGHUP).
        Should update internal resources with new context.
        
        Args:
            context: New runtime context with updated information
        """
        pass
    
    def validate_source(self, source_code: str) -> bool:
        """Validate source code syntax (optional).
        
        Args:
            source_code: Source code to validate
            
        Returns:
            True if valid, False otherwise
        """
        return True


class ExecutionEngine:
    """Main execution engine that orchestrates validation and execution.
    
    Manages multiple executor plugins and provides a unified interface
    for executing code with proper validation and lifecycle management.
    
    Example usage:
        >>> from mxcp.executor import ExecutionEngine, ExecutionContext
        >>> from mxcp.executor.plugins import DuckDBExecutor, PythonExecutor
        >>> 
        >>> # Create engine and register executors
        >>> engine = ExecutionEngine(strict=False)
        >>> engine.register_executor(DuckDBExecutor())
        >>> engine.register_executor(PythonExecutor())
        >>> 
        >>> # Initialize with context (executors create their own resources)
        >>> context = ExecutionContext(
        ...     user_config=user_config,
        ...     site_config=site_config,
        ...     user_context=user_context
        ... )
        >>> engine.startup(context)
        >>> 
        >>> # Execute with per-query validation
        >>> input_schema = [{"name": "limit", "type": "integer", "default": 10}]
        >>> output_schema = {"type": "array", "items": {"type": "object"}}
        >>> 
        >>> result = await engine.execute(
        ...     language="sql",
        ...     source_code="SELECT * FROM table LIMIT $limit",
        ...     params={"limit": 5},
        ...     input_schema=input_schema,
        ...     output_schema=output_schema
        ... )
        >>> 
        >>> # Execute without validation
        >>> result = await engine.execute(
        ...     language="python",
        ...     source_code="return 42",
        ...     params={}
        ... )
    """
    
    def __init__(self, strict: bool = False):
        """Initialize execution engine.
        
        Args:
            strict: Whether to use strict validation mode for all executions
        """
        self.strict = strict
        self.executors: Dict[str, ExecutorPlugin] = {}
        self.context: Optional[ExecutionContext] = None
        self._initialized = False
    
    def register_executor(self, executor: ExecutorPlugin) -> None:
        """Register an execution plugin.
        
        Args:
            executor: The executor plugin to register
        """
        language = executor.language
        if language in self.executors:
            raise ValueError(f"Executor for language '{language}' already registered")
        
        self.executors[language] = executor
        
        # Initialize if we have context
        if self._initialized and self.context:
            executor.startup(self.context)
    
    def startup(self, context: ExecutionContext) -> None:
        """Initialize the engine with runtime context.
        
        Args:
            context: Runtime context with shared information
        """
        self.context = context
        
        # Initialize all registered executors
        for executor in self.executors.values():
            executor.startup(context)
        
        self._initialized = True
    
    def shutdown(self) -> None:
        """Shutdown the engine and all executors."""
        for executor in self.executors.values():
            try:
                executor.shutdown()
            except Exception as e:
                # Log error but continue shutdown
                import logging
                logging.error(f"Error shutting down executor {executor.language}: {e}")
        
        self._initialized = False
        self.context = None
    
    def reload(self, context: ExecutionContext) -> None:
        """Reload the engine with new context.
        
        Args:
            context: New runtime context
        """
        old_context = self.context
        self.context = context
        
        # Reload all executors
        for executor in self.executors.values():
            try:
                executor.reload(context)
            except Exception as e:
                # Log error but continue
                import logging
                logging.error(f"Error reloading executor {executor.language}: {e}")
    
    async def execute(
        self,
        language: str,
        source_code: str,
        params: Dict[str, Any],
        input_schema: Optional[List[Dict[str, Any]]] = None,
        output_schema: Optional[Dict[str, Any]] = None
    ) -> Any:
        """Execute source code with per-query validation.
        
        Args:
            language: Execution language (e.g., 'sql', 'python')
            source_code: Source code to execute
            params: Input parameters
            input_schema: Optional input parameter validation schema
            output_schema: Optional output validation schema
            
        Returns:
            Validated and serialized result
            
        Raises:
            ValueError: If executor not found or validation fails
            Exception: If execution fails
        """
        if not self._initialized or not self.context:
            raise RuntimeError("Engine not initialized - call startup() first")
        
        # Get executor
        executor = self.executors.get(language)
        if not executor:
            available = list(self.executors.keys())
            raise ValueError(f"No executor for language '{language}'. Available: {available}")
        
        # Create validator for this execution if schemas provided
        validator = None
        if input_schema is not None or output_schema is not None:
            from mxcp.validator import TypeValidator
            schema_dict = {}
            if input_schema is not None:
                schema_dict["input"] = input_schema
            if output_schema is not None:
                schema_dict["output"] = output_schema
            validator = TypeValidator.from_dict(schema_dict, strict=self.strict)
        
        # Input validation
        if validator and input_schema is not None:
            validated_params = validator.validate_input(params)
        else:
            validated_params = params
        
        # Execute
        raw_result = await executor.execute(source_code, validated_params, self.context)
        
        # Output validation and serialization
        if validator and output_schema is not None:
            return validator.validate_output(raw_result, serialize=True)
        else:
            # Still serialize for consistency
            from mxcp.validator import TypeValidator
            temp_validator = TypeValidator.from_dict({}, strict=self.strict)
            return temp_validator.validate_output(raw_result, serialize=True)
    
    def get_available_languages(self) -> List[str]:
        """Get list of available execution languages."""
        return list(self.executors.keys())
    
    def is_initialized(self) -> bool:
        """Check if engine is initialized."""
        return self._initialized 