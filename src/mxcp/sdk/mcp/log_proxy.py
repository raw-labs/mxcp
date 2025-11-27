"""
MCP logging/progress proxy implementations for ExecutionContext.
"""

from __future__ import annotations

import logging
from typing import Any, Protocol, runtime_checkable


try:  # Optional dependency when not running server side
    from mcp.server.fastmcp import Context as FastMCPContext
except Exception:  # pragma: no cover
    FastMCPContext = Any  # type: ignore[assignment]


@runtime_checkable
class MCPLogProxy(Protocol):
    """Protocol exposed to runtime code for MCP logging/progress."""

    async def debug(self, message: str, **extra: Any) -> None: ...

    async def info(self, message: str, **extra: Any) -> None: ...

    async def warning(self, message: str, **extra: Any) -> None: ...

    async def error(self, message: str, **extra: Any) -> None: ...

    async def progress(
        self, progress: float, total: float | None = None, message: str | None = None
    ) -> None: ...


class NullMCPProxy:
    """No-op implementation used when MCP features are unavailable."""

    async def debug(self, message: str, **extra: Any) -> None:
        return None

    async def info(self, message: str, **extra: Any) -> None:
        return None

    async def warning(self, message: str, **extra: Any) -> None:
        return None

    async def error(self, message: str, **extra: Any) -> None:
        return None

    async def progress(
        self, progress: float, total: float | None = None, message: str | None = None
    ) -> None:
        return None


class LoggingMCPProxy:
    """Fallback proxy that logs locally instead of sending MCP events."""

    def __init__(self, *, transport: str | None = None) -> None:
        self._logger = logging.getLogger("mxcp.runtime.mcp")
        self._transport = transport or "unknown"

    async def debug(self, message: str, **extra: Any) -> None:
        self._logger.debug("%s", message, extra=extra or None)

    async def info(self, message: str, **extra: Any) -> None:
        self._logger.info("%s", message, extra=extra or None)

    async def warning(self, message: str, **extra: Any) -> None:
        self._logger.warning("%s", message, extra=extra or None)

    async def error(self, message: str, **extra: Any) -> None:
        self._logger.error("%s", message, extra=extra or None)

    async def progress(
        self, progress: float, total: float | None = None, message: str | None = None
    ) -> None:
        total_str = f"/{total}" if total is not None else ""
        msg = message or ""
        self._logger.info("[%s progress] %s%s %s", self._transport, progress, total_str, msg)


class FastMCPLogProxy:
    """Adapter that forwards logging/progress to an upstream FastMCP Context."""

    def __init__(self, context: FastMCPContext) -> None:
        self._context = context

    async def debug(self, message: str, **extra: Any) -> None:
        await self._context.debug(message, **extra)

    async def info(self, message: str, **extra: Any) -> None:
        await self._context.info(message, **extra)

    async def warning(self, message: str, **extra: Any) -> None:
        await self._context.warning(message, **extra)

    async def error(self, message: str, **extra: Any) -> None:
        await self._context.error(message, **extra)

    async def progress(
        self, progress: float, total: float | None = None, message: str | None = None
    ) -> None:
        await self._context.report_progress(progress, total, message)

