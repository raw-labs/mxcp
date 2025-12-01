"""User context management for MXCP authentication.

This module provides context variable management for user authentication information
that can be set by auth middleware and retrieved by endpoint execution code.
"""

import contextvars

from .models import UserContextModel

# Thread-safe user context management using contextvars
# This allows auth middleware to set user context and endpoint code to retrieve it
# without explicit parameter passing through the call stack

# Create a contextvar to store the current user context
# The default is None, indicating no authenticated user
user_context_var = contextvars.ContextVar[UserContextModel | None]("user_context", default=None)


def get_user_context() -> UserContextModel | None:
    """
    Get the current user context from the authentication context.

    Returns:
        The UserContextModel if a user is authenticated, None otherwise.

    Example:
        >>> user_context = get_user_context()
        >>> if user_context:
        ...     print(f"Authenticated user: {user_context.username}")
        ... else:
        ...     print("No authenticated user")
    """
    return user_context_var.get()


def set_user_context(
    context: UserContextModel | None,
) -> "contextvars.Token[UserContextModel | None]":
    """
    Set the user context in the current authentication context.

    This is typically called by authentication middleware after successful authentication.

    Args:
        context: The UserContextModel to set, or None to clear authentication

    Returns:
        A token that can be used to reset the context

    Example:
        >>> token = set_user_context(user_context)
        >>> try:
        ...     # Execute authenticated code
        ...     pass
        ... finally:
        ...     reset_user_context(token)
    """
    return user_context_var.set(context)


def reset_user_context(token: "contextvars.Token[UserContextModel | None]") -> None:
    """
    Reset the user context using a token.

    This should be called to restore the previous authentication state,
    typically in a finally block after setting a user context.

    Args:
        token: The token returned by set_user_context

    Example:
        >>> token = set_user_context(user_context)
        >>> try:
        ...     # Execute authenticated code
        ...     pass
        ... finally:
        ...     reset_user_context(token)
    """
    user_context_var.reset(token)
