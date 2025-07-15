"""Core execution context for MXCP SDK executor components.

This module provides ExecutionContext for sharing user information
and extensible state between MXCP components.
"""

import contextvars
from typing import Dict, Any, Optional
from dataclasses import dataclass, field

from mxcp.sdk.auth import UserContext


@dataclass
class ExecutionContext:
    """Runtime context for MXCP executor components.
    
    This context provides:
    - User information via UserContext from mxcp.sdk.auth
    - Extensible context_data for component-specific state
    
    Example usage:
        >>> from mxcp.sdk.executor import ExecutionContext
        >>> from mxcp.sdk.auth import UserContext
        >>> 
        >>> # Create user context
        >>> user_context = UserContext(
        ...     user_id="user123",
        ...     username="john.doe",
        ...     provider="github",
        ...     external_token="ghp_xxx",
        ...     email="john@example.com"
        ... )
        >>> 
        >>> # Create execution context with user info
        >>> context = ExecutionContext(user_context=user_context)
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
    
    # User information from mxcp.sdk.auth
    user_context: Optional[UserContext] = None
    
    # Extensible context data for components
    context_data: Dict[str, Any] = field(default_factory=dict)
    
    # Convenience properties for backward compatibility
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