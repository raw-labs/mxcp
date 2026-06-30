"""Audit backend implementations."""

from typing import Any

__all__ = ["JSONLAuditWriter"]


def __getattr__(name: str) -> Any:
    if name == "JSONLAuditWriter":
        from .jsonl import JSONLAuditWriter

        return JSONLAuditWriter
    raise AttributeError(name)
