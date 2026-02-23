"""Scope normalization helpers for provider adapters."""

from __future__ import annotations

from collections.abc import Sequence


def normalize_granted_scopes(
    scope_str: str | None,
    requested_scopes: Sequence[str],
    *,
    separator: str | None = None,
) -> list[str]:
    """Normalize provider scope response and fall back to requested scopes.

    Treat whitespace-only scope strings as missing. For providers that return
    comma-separated scopes, pass `separator=","` to preserve existing behavior.
    """
    if not scope_str or not scope_str.strip():
        return list(requested_scopes)
    if separator is None:
        return scope_str.split()
    return scope_str.split(separator)
