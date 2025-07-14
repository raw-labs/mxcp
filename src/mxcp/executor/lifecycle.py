"""Lifecycle management for MXCP executor system.

This module provides lifecycle management for execution engines, including
startup, shutdown, and reload functionality.

Example usage:
    >>> from mxcp.executor import ExecutionEngine, ExecutionContext, LifecycleManager
    >>> from mxcp.executor.plugins import DuckDBExecutor, PythonExecutor
    >>> 
    >>> # Create engines
    >>> sql_engine = ExecutionEngine(strict=False)
    >>> sql_engine.register_executor(DuckDBExecutor())
    >>> 
    >>> python_engine = ExecutionEngine(strict=True)
    >>> python_engine.register_executor(PythonExecutor())
    >>> 
    >>> # Create lifecycle manager
    >>> manager = LifecycleManager()
    >>> manager.register_engine("sql", sql_engine)
    >>> manager.register_engine("python", python_engine)
    >>> 
    >>> # Initialize with context (executors create their own resources)
    >>> context = ExecutionContext(
    ...     user_config=user_config,
    ...     site_config=site_config,
    ...     user_context=user_context
    ... )
    >>> manager.startup(context)
    >>> 
    >>> # Use engines
    >>> sql_engine = manager.get_engine("sql")
    >>> result = await sql_engine.execute("sql", "SELECT 1", {})
    >>> 
    >>> # Reload with new context
    >>> new_context = ExecutionContext(
    ...     user_config=new_user_config,
    ...     site_config=new_site_config,
    ...     user_context=new_user_context
    ... )
    >>> manager.reload(new_context)
    >>> 
    >>> # Shutdown
    >>> manager.shutdown()
"""

import logging
import threading
from typing import Optional, Dict, Any, Callable, List
from pathlib import Path

from .interfaces import ExecutionEngine, ExecutionContext

logger = logging.getLogger(__name__)


class LifecycleManager:
    """Manages the lifecycle of execution engines.
    
    Handles startup, shutdown, and reload functionality for the executor system.
    
    Example usage:
        >>> from mxcp.executor import LifecycleManager, ExecutionEngine, ExecutionContext
        >>> from mxcp.executor.plugins import DuckDBExecutor, PythonExecutor
        >>> 
        >>> # Create lifecycle manager
        >>> manager = LifecycleManager()
        >>> 
        >>> # Create and register engines
        >>> sql_engine = ExecutionEngine()
        >>> sql_engine.register_executor(DuckDBExecutor())
        >>> manager.register_engine("sql", sql_engine)
        >>> 
        >>> python_engine = ExecutionEngine()
        >>> python_engine.register_executor(PythonExecutor())
        >>> manager.register_engine("python", python_engine)
        >>> 
        >>> # Start up all engines
        >>> context = ExecutionContext(
        ...     user_config=user_config,
        ...     site_config=site_config,
        ...     user_context=user_context
        ... )
        >>> manager.startup(context)
        >>> 
        >>> # Get engine for use
        >>> sql_engine = manager.get_engine("sql")
        >>> 
        >>> # Register reload callback
        >>> def on_reload():
        ...     logger.info("Reloading custom components")
        >>> manager.register_reload_callback(on_reload)
        >>> 
        >>> # Shutdown
        >>> manager.shutdown()
    """
    
    def __init__(self):
        """Initialize the lifecycle manager."""
        self.engines: Dict[str, ExecutionEngine] = {}
        self.context: Optional[ExecutionContext] = None
        self._initialized = False
        self._shutdown_called = False
        self._reload_callbacks: List[Callable[[], None]] = []
        self._lock = threading.Lock()
    
    def register_engine(self, name: str, engine: ExecutionEngine) -> None:
        """Register an execution engine.
        
        Args:
            name: Unique name for the engine
            engine: The execution engine to register
        """
        if name in self.engines:
            raise ValueError(f"Engine '{name}' already registered")
        
        self.engines[name] = engine
        
        # Initialize if we have context
        if self._initialized and self.context:
            engine.startup(self.context)
    
    def startup(self, context: ExecutionContext) -> None:
        """Start all registered engines.
        
        Args:
            context: Runtime context to use
        """
        with self._lock:
            if self._initialized:
                logger.warning("Lifecycle manager already initialized")
                return
            
            logger.info("Starting executor lifecycle manager...")
            self.context = context
            
            # Initialize all engines
            for name, engine in self.engines.items():
                try:
                    logger.info(f"Starting execution engine: {name}")
                    engine.startup(context)
                except Exception as e:
                    logger.error(f"Failed to start engine '{name}': {e}")
                    # Continue with other engines
            
            self._initialized = True
            logger.info("Executor lifecycle manager started successfully")
    
    def shutdown(self) -> None:
        """Shutdown all engines gracefully."""
        with self._lock:
            if self._shutdown_called:
                return
            self._shutdown_called = True
            
            logger.info("Shutting down executor lifecycle manager...")
            
            # Shutdown all engines in reverse order
            engine_items = list(self.engines.items())
            for name, engine in reversed(engine_items):
                try:
                    logger.info(f"Shutting down execution engine: {name}")
                    engine.shutdown()
                except Exception as e:
                    logger.error(f"Error shutting down engine '{name}': {e}")
                    # Continue with other engines
            
            self._initialized = False
            self.context = None
            logger.info("Executor lifecycle manager shutdown complete")
    
    def reload(self, new_context: ExecutionContext) -> None:
        """Reload all engines with new context.
        
        Args:
            new_context: New runtime context
        """
        with self._lock:
            if not self._initialized:
                logger.warning("Cannot reload - lifecycle manager not initialized")
                return
            
            logger.info("Reloading executor lifecycle manager...")
            old_context = self.context
            self.context = new_context
            
            # Reload all engines
            for name, engine in self.engines.items():
                try:
                    logger.info(f"Reloading execution engine: {name}")
                    engine.reload(new_context)
                except Exception as e:
                    logger.error(f"Error reloading engine '{name}': {e}")
                    # Continue with other engines
            
            # Call registered reload callbacks
            for callback in self._reload_callbacks:
                try:
                    callback()
                except Exception as e:
                    logger.error(f"Error in reload callback: {e}")
            
            logger.info("Executor lifecycle manager reload complete")
    
    def register_reload_callback(self, callback: Callable[[], None]) -> None:
        """Register a callback to be called during reload.
        
        Args:
            callback: Function to call during reload
        """
        self._reload_callbacks.append(callback)
    
    def get_engine(self, name: str) -> Optional[ExecutionEngine]:
        """Get an execution engine by name.
        
        Args:
            name: Name of the engine
            
        Returns:
            ExecutionEngine or None if not found
        """
        return self.engines.get(name)
    
    def is_initialized(self) -> bool:
        """Check if the lifecycle manager is initialized."""
        return self._initialized


def create_execution_context(
    user_config=None,
    site_config=None,
    user_context=None
) -> ExecutionContext:
    """Create an ExecutionContext with the given parameters.
    
    This is a convenience function for creating contexts.
    
    Args:
        user_config: User configuration
        site_config: Site configuration
        user_context: User authentication context
        
    Returns:
        ExecutionContext instance
        
    Example usage:
        >>> from mxcp.executor.lifecycle import create_execution_context
        >>> 
        >>> # Create context with configuration
        >>> context = create_execution_context(
        ...     user_config=user_config,
        ...     site_config=site_config,
        ...     user_context=user_context
        ... )
        >>> 
        >>> # Create minimal context for testing
        >>> test_context = create_execution_context()
    """
    return ExecutionContext(
        user_config=user_config,
        site_config=site_config,
        user_context=user_context
    ) 