"""Python executor plugin for Python code execution.

This plugin handles Python code execution with full lifecycle management,
including runtime hooks, context management, and module loading.

Example usage:
    >>> from mxcp.executor import ExecutionEngine, ExecutionContext
    >>> from mxcp.executor.plugins import PythonExecutor
    >>> from pathlib import Path
    >>> 
    >>> # Create Python executor
    >>> executor = PythonExecutor(repo_root=Path("/path/to/repo"))
    >>> 
    >>> # Create engine and register executor
    >>> engine = ExecutionEngine()
    >>> engine.register_executor(executor)
    >>> 
    >>> # Initialize with context
    >>> context = ExecutionContext(
    ...     user_config=user_config,
    ...     site_config=site_config,
    ...     user_context=user_context
    ... )
    >>> engine.startup(context)
    >>> 
    >>> # Execute inline Python code
    >>> result = await engine.execute(
    ...     language="python",
    ...     source_code="return sum(data)",
    ...     params={"data": [1, 2, 3, 4, 5]}
    ... )
    >>> 
    >>> # Execute Python file
    >>> result = await engine.execute(
    ...     language="python",
    ...     source_code="data_analysis.py",
    ...     params={"dataset": "sales_data"}
    ... )
    >>> 
    >>> # Execute with validation
    >>> input_schema = [{"name": "numbers", "type": "array", "items": {"type": "number"}}]
    >>> output_schema = {"type": "number"}
    >>> result = await engine.execute(
    ...     language="python",
    ...     source_code="return statistics.mean(numbers)",
    ...     params={"numbers": [1, 2, 3, 4, 5]},
    ...     input_schema=input_schema,
    ...     output_schema=output_schema
    ... )
"""

import asyncio
import functools
import logging
import sys
import tempfile
from contextvars import copy_context
from pathlib import Path
from typing import Dict, Any, Optional, Callable, List, TYPE_CHECKING

from ..interfaces import ExecutorPlugin, ExecutionContext

if TYPE_CHECKING:
    from .python_plugin.loader import PythonEndpointLoader

logger = logging.getLogger(__name__)


class PythonExecutor(ExecutorPlugin):
    """Executor plugin for Python code execution.
    
    Handles Python code execution with full lifecycle management,
    including runtime hooks, context management, and module loading.
    
    Example usage:
        >>> from mxcp.executor.plugins import PythonExecutor
        >>> from mxcp.executor import ExecutionContext
        >>> from pathlib import Path
        >>> 
        >>> # Create executor
        >>> executor = PythonExecutor(repo_root=Path("/path/to/repo"))
        >>> 
        >>> # Initialize with context
        >>> context = ExecutionContext(
        ...     user_config=user_config,
        ...     site_config=site_config,
        ...     user_context=user_context
        ... )
        >>> executor.startup(context)
        >>> 
        >>> # Execute inline Python code
        >>> result = await executor.execute(
        ...     "return sum(data)",
        ...     {"data": [1, 2, 3, 4, 5]},
        ...     context
        ... )
        >>> 
        >>> # Execute Python file
        >>> result = await executor.execute(
        ...     "data_analysis.py",
        ...     {"dataset": "sales_data"},
        ...     context
        ... )
        >>> 
        >>> # Validate Python syntax
        >>> is_valid = executor.validate_source("return 42")
        >>> 
        >>> # Lifecycle management
        >>> executor.shutdown()
    """
    
    def __init__(self, repo_root: Optional[Path] = None):
        """Initialize Python executor.
        
        Args:
            repo_root: Repository root directory. If None, will detect from context.
        """
        self.repo_root = repo_root
        if not self.repo_root:
            logger.warning("No repo root provided, using current working directory")
            self.repo_root = Path.cwd()

        self._context: Optional[ExecutionContext] = None
        self._loader: Optional['PythonEndpointLoader'] = None
        self._init_hooks: List[Callable] = []
        self._shutdown_hooks: List[Callable] = []
        self._hooks_discovered = False
    
    @property
    def language(self) -> str:
        """The language this executor handles."""
        return "python"
    
    @property
    def loader(self) -> 'PythonEndpointLoader':
        """Get the Python module loader."""
        if not self._loader:
            raise RuntimeError("Python loader not initialized")
        return self._loader
    
    def startup(self, context: ExecutionContext) -> None:
        """Initialize the Python executor.
        
        Args:
            context: Runtime context with configuration
        """
        self._context = context
        
        # Initialize Python loader
        from .python_plugin.loader import PythonEndpointLoader
        # repo_root is guaranteed to be set by __init__ if it was None
        assert self.repo_root is not None, "repo_root should be set by __init__"
        self._loader = PythonEndpointLoader(self.repo_root)
        
        # Discover and run initialization hooks
        self._discover_hooks()
        self._run_init_hooks()
        
        logger.info("Python executor initialized")
    
    def shutdown(self) -> None:
        """Clean up Python executor resources."""
        logger.info("Python executor shutting down")
        
        # Run shutdown hooks
        self._run_shutdown_hooks()
        
        # Clean up loader
        if self._loader:
            # The loader doesn't have explicit cleanup, but we can clear references
            self._loader = None
        
        self._context = None
        self._init_hooks.clear()
        self._shutdown_hooks.clear()
        self._hooks_discovered = False
        
        logger.info("Python executor shutdown complete")
    
    def reload(self, context: ExecutionContext) -> None:
        """Reload Python executor with new context.
        
        Args:
            context: New runtime context
        """
        logger.info("Reloading Python executor")
        
        # Run shutdown hooks with old context
        self._run_shutdown_hooks()
        
        # Update context
        old_context = self._context
        self._context = context
        
        # Reload modules if needed
        if self._loader:
            # Clear cached modules to force reload
            self._loader._loaded_modules.clear()
        
        # Rediscover hooks if context changed significantly
        if old_context is None or old_context.site_config != context.site_config:
            self._hooks_discovered = False
            self._discover_hooks()
        
        # Run init hooks with new context
        self._run_init_hooks()
        
        logger.info("Python executor reloaded")
    
    def validate_source(self, source_code: str) -> bool:
        """Validate Python source code syntax.
        
        Args:
            source_code: Python code to validate
            
        Returns:
            True if valid, False otherwise
        """
        try:
            # Check if it's a file path
            if self._is_file_path(source_code):
                if self.repo_root:
                    return (self.repo_root / "python" / source_code).exists()
                return False
            
            # Validate inline code syntax
            compile(source_code, '<string>', 'exec')
            return True
        except SyntaxError as e:
            logger.debug(f"Python syntax validation failed: {e}")
            return False
        except Exception as e:
            logger.debug(f"Python validation failed: {e}")
            return False
    
    async def execute(
        self,
        source_code: str,
        params: Dict[str, Any],
        context: ExecutionContext
    ) -> Any:
        """Execute Python source code with parameters.
        
        Args:
            source_code: Python code to execute or file path
            params: Parameter values
            context: Runtime context
            
        Returns:
            Execution result
        """
        try:
            # Check if it's a file path or inline code
            if self._is_file_path(source_code):
                return await self._execute_from_file(source_code, params)
            else:
                return await self._execute_inline(source_code, params)
        except Exception as e:
            logger.error(f"Python execution failed: {e}")
            raise RuntimeError(f"Failed to execute Python code: {e}")
    
    def _is_file_path(self, source_code: str) -> bool:
        """Check if source code is a file path."""
        # Simple heuristic: if it's a single line ending with .py, treat as file
        return (
            '\n' not in source_code.strip() and 
            source_code.strip().endswith('.py') and 
            not source_code.strip().startswith('return')
        )
    
    async def _execute_from_file(self, file_path: str, params: Dict[str, Any]) -> Any:
        """Execute Python code from a file."""
        try:
            # Load the module using the correct method name
            module = self.loader.load_python_module(Path(file_path))
            
            # Get the main function (assume it's named 'main' or matches the file name)
            file_name = Path(file_path).stem
            function_name = 'main'  # Default to 'main'
            
            # Try to find the function
            if hasattr(module, function_name):
                func = getattr(module, function_name)
            elif hasattr(module, file_name):
                func = getattr(module, file_name)
            else:
                # Look for any callable function that's not a built-in
                functions = [name for name in dir(module) 
                           if callable(getattr(module, name)) and not name.startswith('_')]
                if functions:
                    func = getattr(module, functions[0])
                else:
                    raise AttributeError(f"No callable function found in {file_path}")
            
            # Execute the function
            return await self._execute_function(func, params)
            
        except Exception as e:
            logger.error(f"Failed to execute file {file_path}: {e}")
            raise
    
    async def _execute_inline(self, source_code: str, params: Dict[str, Any]) -> Any:
        """Execute inline Python code."""
        try:
            # Create execution namespace with parameters
            namespace = params.copy()
            
            # Add common imports
            import pandas as pd
            import numpy as np
            namespace.update({
                'pd': pd,
                'np': np,
                'pandas': pd,
                'numpy': np,
            })
            
            # Handle return statements by wrapping in a function
            if source_code.strip().startswith('return '):
                # Extract the return expression
                return_expr = source_code.strip()[7:]  # Remove 'return '
                wrapped_code = f"__result = {return_expr}"
            else:
                wrapped_code = source_code
            
            # Execute in a temporary file to get proper error reporting
            with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
                f.write(wrapped_code)
                f.flush()
                
                # Execute the code
                exec(compile(wrapped_code, f.name, 'exec'), namespace)
            
            # Return the result
            if '__result' in namespace:
                return namespace['__result']
            elif 'result' in namespace:
                return namespace['result']
            else:
                return None
            
        except Exception as e:
            logger.error(f"Failed to execute inline code: {e}")
            raise
    
    async def _execute_function(self, func: Callable, params: Dict[str, Any]) -> Any:
        """Execute a function with parameters."""
        try:
            # Check if function is async
            if asyncio.iscoroutinefunction(func):
                return await func(**params)
            else:
                # Run in thread pool to avoid blocking
                loop = asyncio.get_event_loop()
                return await loop.run_in_executor(
                    None, 
                    functools.partial(func, **params)
                )
        except Exception as e:
            logger.error(f"Function execution failed: {e}")
            raise
    
    def _discover_hooks(self) -> None:
        """Discover lifecycle hooks in Python modules."""
        if self._hooks_discovered:
            return
        
        self._init_hooks.clear()
        self._shutdown_hooks.clear()
        
        try:
            if not self._loader:
                return
            
            # Look for lifecycle hooks in loaded modules  
            for module_name, module in self._loader._loaded_modules.items():
                # Look for functions with hook decorators
                for attr_name in dir(module):
                    attr = getattr(module, attr_name)
                    if callable(attr) and hasattr(attr, '_mxcp_on_init'):
                        self._init_hooks.append(attr)
                    elif callable(attr) and hasattr(attr, '_mxcp_on_shutdown'):
                        self._shutdown_hooks.append(attr)
                        
        except Exception as e:
            logger.warning(f"Failed to discover lifecycle hooks: {e}")
        
        self._hooks_discovered = True
    
    def _run_init_hooks(self) -> None:
        """Run initialization hooks."""
        for hook in self._init_hooks:
            try:
                hook()
            except Exception as e:
                logger.error(f"Error running init hook {hook.__name__}: {e}")
    
    def _run_shutdown_hooks(self) -> None:
        """Run shutdown hooks."""
        for hook in self._shutdown_hooks:
            try:
                hook()
            except Exception as e:
                logger.error(f"Error running shutdown hook {hook.__name__}: {e}") 