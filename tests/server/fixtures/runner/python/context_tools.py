from mxcp.sdk.executor import get_execution_context


def headers() -> dict[str, str]:
    """Show the request headers."""
    request_headers = get_execution_context().get("request_headers")
    return request_headers
