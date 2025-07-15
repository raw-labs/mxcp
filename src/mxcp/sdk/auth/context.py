# -*- coding: utf-8 -*-
"""User context management for MXCP using contextvars."""
import contextvars
from typing import Optional

from .types import UserContext

# Create a contextvar to store the user context
# The default is None, indicating no authenticated user is present
user_context_var = contextvars.ContextVar[Optional[UserContext]](
    "user_context", default=None
)


def get_user_context() -> Optional[UserContext]:
    """
    Get the user context from the current context.

    Returns:
        The UserContext if an authenticated user is available, None otherwise.
    """
    return user_context_var.get()


def set_user_context(user_context: Optional[UserContext]) -> contextvars.Token:
    """
    Set the user context in the current context.
    
    Args:
        user_context: The UserContext to set
        
    Returns:
        A token that can be used to reset the context
    """
    return user_context_var.set(user_context)


def reset_user_context(token: contextvars.Token) -> None:
    """
    Reset the user context using a token.
    
    Args:
        token: The token returned by set_user_context
    """
    user_context_var.reset(token) 