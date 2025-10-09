"""Core execution context for MXCP SDK executor components.

This module provides ExecutionContext for sharing user information
and extensible state between MXCP components.
"""

import contextvars
from dataclasses import dataclass, field
from typing import Any

from mcp.server.fastmcp import Context

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

    # User information
    user_context: UserContext | None = None

    # Simple key-value storage
    _data: dict[str, Any] = field(default_factory=dict)

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
    def user_id(self) -> str | None:
        """Get user ID from user context."""
        return self.user_context.user_id if self.user_context else None

    @property
    def username(self) -> str | None:
        """Get username from user context."""
        return self.user_context.username if self.user_context else None

    @property
    def provider(self) -> str | None:
        """Get provider from user context."""
        return self.user_context.provider if self.user_context else None

    @property
    def external_token(self) -> str | None:
        """Get external token from user context."""
        return self.user_context.external_token if self.user_context else None

    @property
    def email(self) -> str | None:
        """Get email from user context."""
        return self.user_context.email if self.user_context else None

    def has_user_info(self) -> bool:
        """Check if user information is available.

        Returns:
            True if user context is set and has username
        """
        return self.user_context is not None and self.user_context.username is not None

    def copy(self, **kwargs: Any) -> "ExecutionContext":
        """Create a copy of this context with optional field updates.

        Args:
            **kwargs: Fields to update in the new context

        Returns:
            A new ExecutionContext with updated fields
        """
        # Create a new context with current values
        new_context = ExecutionContext(user_context=self.user_context, _data=self._data.copy())

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
execution_context_var = contextvars.ContextVar[ExecutionContext | None](
    "execution_context", default=None
)


def get_execution_context() -> ExecutionContext | None:
    """
    Get the execution context from the current context.

    Returns:
        The ExecutionContext if available, None otherwise.
    """
    return execution_context_var.get()


def set_execution_context(
    context: ExecutionContext | None,
) -> "contextvars.Token[ExecutionContext | None]":
    """
    Set the execution context in the current context.

    Args:
        context: The ExecutionContext to set

    Returns:
        A token that can be used to reset the context
    """
    return execution_context_var.set(context)


def reset_execution_context(token: "contextvars.Token[ExecutionContext | None]") -> None:
    """
    Reset the execution context using a token.

    Args:
        token: The token returned by set_execution_context
    """
    execution_context_var.reset(token)



# Thread-safe MCP context management using contextvars
# This allows MCP handlers to set the FastMCP context and endpoint code to retrieve it
# without explicit parameter passing through the call stack

# Create a contextvar to store the current MCP context
# The default is None, indicating no MCP context available
mcp_context_var = contextvars.ContextVar[Context | None]("mcp_context", default=None)


def get_mcp_context() -> Context | None:
    """
    Get the current MCP context from the request context.

    Returns:
        The FastMCP Context if available, None otherwise.

    Example:
        >>> mcp_context = get_mcp_context()
        >>> if mcp_context:
        ...     request = mcp_context.request_context.request
        ...     if request:
        ...         headers = request.headers
        ...         user_agent = headers.get("user-agent")
    """
    return mcp_context_var.get()


def set_mcp_context(context: Context | None) -> "contextvars.Token[Context | None]":
    """
    Set the MCP context in the current request context.

    This is typically called by MCP handlers after receiving the FastMCP context.

    Args:
        context: The FastMCP Context to set, or None to clear context

    Returns:
        A token that can be used to reset the context

    Example:
        >>> token = set_mcp_context(ctx)
        >>> try:
        ...     # Execute endpoint code that can access MCP context
        ...     pass
        ... finally:
        ...     reset_mcp_context(token)
    """
    return mcp_context_var.set(context)


def reset_mcp_context(token: "contextvars.Token[Context | None]") -> None:
    """
    Reset the MCP context using a token.

    This should be called to restore the previous context state,
    typically in a finally block after setting an MCP context.

    Args:
        token: The token returned by set_mcp_context

    Example:
        >>> token = set_mcp_context(ctx)
        >>> try:
        ...     # Execute endpoint code
        ...     pass
        ... finally:
        ...     reset_mcp_context(token)
    """
    mcp_context_var.reset(token)


def get_request_headers() -> dict[str, str] | None:
    """
    Get HTTP headers from the current MCP request context.

    Returns:
        Dictionary of HTTP headers if available, None otherwise.

    Example:
        >>> headers = get_request_headers()
        >>> if headers:
        ...     user_agent = headers.get("user-agent")
        ...     authorization = headers.get("authorization")
        ...     custom_header = headers.get("x-custom-header")
    """
    mcp_context = get_mcp_context()
    if mcp_context and hasattr(mcp_context, "request_context"):
        request_context = mcp_context.request_context
        if request_context and hasattr(request_context, "request") and request_context.request:
            # Convert Starlette Headers to dict for easier access
            return dict(request_context.request.headers)
    return None


def get_request_info() -> dict[str, Any] | None:
    """
    Get comprehensive request information from the current MCP context.

    Returns:
        Dictionary with request information if available, None otherwise.
        Contains: method, url, headers, client_ip, etc.

    Example:
        >>> request_info = get_request_info()
        >>> if request_info:
        ...     method = request_info["method"]
        ...     url = request_info["url"]
        ...     client_ip = request_info["client_ip"]
        ...     headers = request_info["headers"]
    """
    mcp_context = get_mcp_context()
    if mcp_context and hasattr(mcp_context, "request_context"):
        request_context = mcp_context.request_context
        if request_context and hasattr(request_context, "request") and request_context.request:
            request = request_context.request
            return {
                "method": request.method,
                "url": str(request.url),
                "headers": dict(request.headers),
                "client_ip": request.client.host if request.client else None,
                "client_port": request.client.port if request.client else None,
                "path": request.url.path,
                "query_params": dict(request.query_params),
                "cookies": dict(request.cookies) if request.cookies else {},
            }
    return None
