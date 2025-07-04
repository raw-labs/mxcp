"""Core execution context for MXCP SDK executor components.

This module provides ExecutionContext for sharing user information
and extensible state between MXCP components.
"""

import contextvars
from typing import Dict, Any, Optional
from dataclasses import dataclass, field
from contextlib import contextmanager

from mxcp.sdk.auth import UserContext


@dataclass
class ExecutionContext:
    """Simplified runtime context for MXCP executor components.
    
    This context provides simple key-value storage where:
    - Keys are strings
    - Values can be anything
    
    Example usage:
        >>> from mxcp.sdk.executor import ExecutionContext
        >>> 
        >>> # Create context
        >>> context = ExecutionContext()
        >>> 
        >>> # Simple key-value operations
        >>> context.set("session", db_session)
        >>> context.set("site_config", config_dict)
        >>> context.update("user_count", 42)
        >>> 
        >>> # Retrieve values
        >>> session = context.get("session")
        >>> config = context.get("site_config")
        >>> count = context.get("user_count", default=0)
        >>> 
        >>> # Store user information
        >>> context.set("user_id", "user123")
        >>> context.set("username", "john.doe")
    """
    
    # User information from mxcp.sdk.auth (for backward compatibility)
    user_context: Optional[UserContext] = None
    
    # Simple key-value storage
    _data: Dict[str, Any] = field(default_factory=dict)
    
    # Simple key-value operations (new interface)
    def get(self, key: str, default: Any = None) -> Any:
        """Get a value by key.
        
        Args:
            key: The key to look up
            default: Default value if key not found
            
        Returns:
            The value for the key, or default if not found
        """
        return self._data.get(key, default)
    
    def set(self, key: str, value: Any) -> None:
        """Set a value for a key.
        
        Args:
            key: The key to set
            value: The value to store
        """
        self._data[key] = value
    
    def update(self, key: str, value: Any) -> None:
        """Update/set a value for a key (alias for set).
        
        Args:
            key: The key to update
            value: The value to store
        """
        self._data[key] = value
    
    # Convenience properties for user context
    @property
    def user_id(self) -> Optional[str]:
        """Get user ID from user context."""
        return self.user_context.user_id if self.user_context else None
    
    @property
    def username(self) -> Optional[str]:
        """Get username from user context."""
        return self.user_context.username if self.user_context else None
    
    @property
    def provider(self) -> Optional[str]:
        """Get provider from user context."""
        return self.user_context.provider if self.user_context else None
    
    @property
    def external_token(self) -> Optional[str]:
        """Get external token from user context."""
        return self.user_context.external_token if self.user_context else None
    
    @property
    def email(self) -> Optional[str]:
        """Get email from user context."""
        return self.user_context.email if self.user_context else None
    
    def has_user_info(self) -> bool:
        """Check if user information is available.
        
        Returns:
            True if user context is set and has username
        """
        return self.user_context is not None and self.user_context.username is not None
    
    def copy(self, **kwargs) -> 'ExecutionContext':
        """Create a copy of this context with optional field updates.
        
        Args:
            **kwargs: Fields to update in the new context
            
        Returns:
            A new ExecutionContext with updated fields
        """
        # Create a new context with current values
        new_context = ExecutionContext(
            user_context=self.user_context,
            _data=self._data.copy()
        )
        
        # Update any provided fields
        for key, value in kwargs.items():
            if hasattr(new_context, key):
                setattr(new_context, key, value)
            else:
                raise ValueError(f"Invalid field: {key}")
        
        return new_context


# Thread-safe context management using contextvars
# This allows components to access the current execution context
# without explicit parameter passing through the call stack

# Create a contextvar to store the execution context
# The default is None, indicating no context is currently set
execution_context_var = contextvars.ContextVar[Optional[ExecutionContext]](
    "execution_context", default=None
)


def get_execution_context() -> Optional[ExecutionContext]:
    """
    Get the execution context from the current context.

    Returns:
        The ExecutionContext if available, None otherwise.
    """
    return execution_context_var.get()


def set_execution_context(context: Optional[ExecutionContext]) -> contextvars.Token:
    """
    Set the execution context in the current context.
    
    Args:
        context: The ExecutionContext to set
        
    Returns:
        A token that can be used to reset the context
    """
    return execution_context_var.set(context)


def reset_execution_context(token: contextvars.Token) -> None:
    """
    Reset the execution context using a token.
    
    Args:
        token: The token returned by set_execution_context
    """
    execution_context_var.reset(token)


@contextmanager
def execution_context_for_init_hooks(
    user_config: Optional[Dict] = None,
    site_config: Optional[Dict] = None,
    duckdb_session = None,
    plugins: Optional[Dict] = None
):
    """
    Context manager for setting up ExecutionContext for init hooks.
    
    This helper function creates an ExecutionContext with the provided
    runtime data, sets it as the current context, and automatically
    cleans it up when done.
    
    Args:
        user_config: User configuration for runtime context
        site_config: Site configuration for runtime context
        duckdb_session: DuckDB session for runtime context
        plugins: Plugins dict for runtime context
        
    Yields:
        The ExecutionContext that was created and set
        
    Example:
        >>> with execution_context_for_init_hooks(user_config, site_config, session) as context:
        ...     run_init_hooks()  # init hooks have access to context
    """
    import logging
    logger = logging.getLogger(__name__)
    
    context = None
    token = None
    
    try:
        if user_config and site_config and duckdb_session:
            context = ExecutionContext()
            context.set("user_config", user_config)
            context.set("site_config", site_config)
            context.set("duckdb_session", duckdb_session)
            if plugins:
                context.set("plugins", plugins)
            token = set_execution_context(context)
            logger.info("Set up ExecutionContext for init hooks")
        
        yield context
        
    finally:
        if token:
            reset_execution_context(token)
            logger.info("Cleaned up ExecutionContext after init hooks") 