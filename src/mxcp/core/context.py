"""Core execution context for MXCP components.

This module provides a minimal ExecutionContext for sharing user information
and extensible state between MXCP components without config dependencies.
"""

import contextvars
from typing import Dict, Any, Optional
from dataclasses import dataclass, field


@dataclass
class ExecutionContext:
    """Minimal runtime context for MXCP components.
    
    This context provides:
    - Static user information passed at construction time
    - Extensible context_data for component-specific state
    
    No dependencies on mxcp.config or mxcp.auth - user info is passed directly.
    
    Example usage:
        >>> from mxcp.core import ExecutionContext
        >>> 
        >>> # Create context with user information
        >>> context = ExecutionContext(
        ...     user_id="user123",
        ...     username="john.doe",
        ...     provider="github",
        ...     external_token="ghp_xxx",
        ...     email="john@example.com"
        ... )
        >>> 
        >>> # Access user information
        >>> print(f"User: {context.username}")
        >>> print(f"Provider: {context.provider}")
        >>> 
        >>> # Store component-specific data
        >>> context.set_context_data("validator", {"strict_mode": True})
        >>> validator_config = context.get_context_data("validator")
        >>> 
        >>> # Create minimal context for testing
        >>> test_context = ExecutionContext()
    """
    
    # Static user information - immutable after creation
    user_id: Optional[str] = None
    username: Optional[str] = None
    provider: Optional[str] = None
    external_token: Optional[str] = None
    email: Optional[str] = None

    # Extensible context data for components
    context_data: Dict[str, Any] = field(default_factory=dict)
    
    def get_context_data(self, component: str) -> Optional[Dict[str, Any]]:
        """Get context data for a specific component.
        
        Args:
            component: The component name (e.g., "validator", "executor", "audit")
            
        Returns:
            The context data for the component, or None if not found
        """
        return self.context_data.get(component)
    
    def set_context_data(self, component: str, data: Dict[str, Any]) -> None:
        """Set context data for a specific component.
        
        Args:
            component: The component name (e.g., "validator", "executor", "audit")
            data: The context data to store
        """
        self.context_data[component] = data
    
    def update_context_data(self, component: str, data: Dict[str, Any]) -> None:
        """Update context data for a specific component.
        
        Args:
            component: The component name (e.g., "validator", "executor", "audit")
            data: The context data to merge with existing data
        """
        if component not in self.context_data:
            self.context_data[component] = {}
        self.context_data[component].update(data)
    
    def has_user_info(self) -> bool:
        """Check if user information is available.
        
        Returns:
            True if username is set
        """
        return self.username is not None
    
    def copy(self, **kwargs) -> 'ExecutionContext':
        """Create a copy of this context with optional field updates.
        
        Args:
            **kwargs: Fields to update in the new context
            
        Returns:
            A new ExecutionContext with updated fields
        """
        # Create a new context with current values
        new_context = ExecutionContext(
            user_id=self.user_id,
            username=self.username,
            provider=self.provider,
            external_token=self.external_token,
            email=self.email,
            context_data=self.context_data.copy()
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