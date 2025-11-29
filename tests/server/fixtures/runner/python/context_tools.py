from typing import Any, Dict

from mxcp.runtime import mcp
from mxcp.sdk.executor import get_execution_context


def headers() -> dict[str, str]:
    """Show the request headers."""
    request_headers = get_execution_context().get("request_headers")
    return request_headers


async def mcp_logging_demo() -> Dict[str, Any]:
    """Exercise the runtime MCP logging/progress proxy."""
    await mcp.info("runtime info log from test")
    await mcp.progress(1, 4, "quarter done")
    await mcp.debug("runtime debug log")
    return {"ok": True}
