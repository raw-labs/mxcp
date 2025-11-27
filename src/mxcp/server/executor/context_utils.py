"""
Utilities for constructing ExecutionContext instances consistently.
"""

from __future__ import annotations

from typing import Any, TYPE_CHECKING

from mxcp.sdk.mcp import LoggingMCPProxy, MCPLogProxy
from mxcp.sdk.auth import UserContext
from mxcp.sdk.executor import ExecutionContext

from mxcp.server.core.config.models import SiteConfigModel, UserConfigModel

if TYPE_CHECKING:
    from mxcp.server.interfaces.server.mcp import RAWMCP


def build_execution_context(
    *,
    user_context: UserContext | None,
    user_config: UserConfigModel,
    site_config: SiteConfigModel,
    server_ref: "RAWMCP | None" = None,
    request_headers: dict[str, str] | None = None,
    transport: str | None = None,
    mcp_interface: MCPLogProxy | None = None,
    extra_values: dict[str, Any] | None = None,
) -> ExecutionContext:
    """Create and populate an ExecutionContext with common runtime data."""

    context = ExecutionContext(user_context=user_context)
    context.set("user_config", user_config.model_dump(mode="python", exclude_unset=True))
    context.set("site_config", site_config.model_dump(mode="python", exclude_unset=True))

    if server_ref:
        context.set("_mxcp_server", server_ref)

    if request_headers is not None:
        context.set("request_headers", request_headers)

    if transport:
        context.set("transport", transport)

    context.set("mcp", mcp_interface or LoggingMCPProxy(transport=transport))

    if extra_values:
        for key, value in extra_values.items():
            context.set(key, value)

    return context

