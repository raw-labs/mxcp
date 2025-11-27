from typing import Any, Dict

from mxcp.runtime import db, mcp
from mxcp.sdk.executor import get_execution_context


def headers() -> dict[str, str]:
    """Show the request headers."""
    request_headers = get_execution_context().get("request_headers")
    return request_headers


def headers_sql() -> dict[str, Any]:
    """Fetch request headers through DuckDB helper UDFs."""
    rows = db.execute(
        "SELECT get_request_header('Authorization') AS auth, get_request_headers_json() AS headers_json"
    )
    row = rows[0] if rows else {}
    return {
        "auth": row.get("auth"),
        "headers_json": row.get("headers_json"),
    }


async def mcp_logging_demo() -> Dict[str, Any]:
    """Exercise the runtime MCP logging/progress proxy."""
    await mcp.info("runtime info log from test")
    await mcp.progress(1, 4, "quarter done")
    await mcp.debug("runtime debug log")
    return {"ok": True}
