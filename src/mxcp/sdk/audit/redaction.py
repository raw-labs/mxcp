"""Redaction strategies for audit logging.

This module provides well-defined redaction strategies for reliable
serialization and consistent behavior.
"""

import hashlib
from typing import Any, cast

from ._types import RedactionStrategy


def apply_redaction(
    value: Any, strategy: RedactionStrategy, options: dict[str, Any] | None = None
) -> Any:
    """Apply redaction using the specified strategy.

    Args:
        value: Value to redact
        strategy: Redaction strategy to apply
        options: Strategy-specific options

    Returns:
        Redacted value
    """
    if strategy == RedactionStrategy.FULL:
        return _redact_full(value, options)
    elif strategy == RedactionStrategy.PARTIAL:
        return _redact_partial(value, options)
    elif strategy == RedactionStrategy.HASH:
        return _redact_hash(value, options)
    elif strategy == RedactionStrategy.TRUNCATE:
        return _redact_truncate(value, options)
    elif strategy == RedactionStrategy.EMAIL:
        return _redact_email(value, options)
    elif strategy == RedactionStrategy.PRESERVE_TYPE:
        return _redact_preserve_type(value, options)
    else:
        raise ValueError(f"Unknown redaction strategy: {strategy}")


def _redact_full(value: Any, options: dict[str, Any] | None = None) -> str:
    """Complete redaction - replaces entire value.

    Args:
        value: Value to redact
        options: Optional configuration (unused)

    Returns:
        "[REDACTED]" string
    """
    return "[REDACTED]"


def _redact_partial(value: Any, options: dict[str, Any] | None = None) -> str:
    """Partial redaction - shows first/last few characters.

    Args:
        value: Value to redact
        options: Optional configuration with:
            - show_first: Number of characters to show at start (default: 2)
            - show_last: Number of characters to show at end (default: 2)
            - min_length: Minimum length before partial redaction (default: 8)

    Returns:
        Partially redacted string like "ab***ef"
    """
    if value is None:
        return "[REDACTED]"

    str_value = str(value)
    show_first = (options or {}).get("show_first", 2)
    show_last = (options or {}).get("show_last", 2)
    min_length = (options or {}).get("min_length", 8)

    if len(str_value) < min_length:
        return "[REDACTED]"

    # Handle edge case where show_last is 0
    if show_last == 0:
        return f"{str_value[:show_first]}***"
    elif show_first == 0:
        return f"***{str_value[-show_last:]}"
    else:
        return f"{str_value[:show_first]}***{str_value[-show_last:]}"


def _redact_hash(value: Any, options: dict[str, Any] | None = None) -> str:
    """Hash redaction - replaces with SHA256 hash.

    Args:
        value: Value to redact
        options: Optional configuration with:
            - algorithm: Hash algorithm (default: "sha256")
            - prefix: Prefix for hash (default: "sha256:")

    Returns:
        Hashed value as hex string
    """
    if value is None:
        return "[REDACTED]"

    algorithm = (options or {}).get("algorithm", "sha256")
    prefix = (options or {}).get("prefix", f"{algorithm}:")

    if algorithm == "sha256":
        hash_obj = hashlib.sha256(str(value).encode())
    elif algorithm == "sha1":
        hash_obj = hashlib.sha1(str(value).encode())
    else:
        # Default to sha256 for unknown algorithms
        hash_obj = hashlib.sha256(str(value).encode())

    return cast(str, prefix + hash_obj.hexdigest())


def _redact_truncate(value: Any, options: dict[str, Any] | None = None) -> str:
    """Truncate redaction - shows only first N characters.

    Args:
        value: Value to redact
        options: Optional configuration with:
            - length: Number of characters to keep (default: 10)
            - suffix: Suffix to add (default: "...")

    Returns:
        Truncated string
    """
    if value is None:
        return "[REDACTED]"

    str_value = str(value)
    length = (options or {}).get("length", 10)
    suffix = (options or {}).get("suffix", "...")

    if len(str_value) <= length:
        return str_value

    return cast(str, str_value[:length] + suffix)


def _redact_email(value: Any, options: dict[str, Any] | None = None) -> str:
    """Email-specific redaction - preserves domain.

    Args:
        value: Email address to redact
        options: Optional configuration with:
            - preserve_domain: Whether to keep domain (default: True)

    Returns:
        Redacted email like "u***@example.com"
    """
    if value is None or "@" not in str(value):
        return "[REDACTED]"

    str_value = str(value)
    preserve_domain = (options or {}).get("preserve_domain", True)

    if not preserve_domain:
        return "[REDACTED]"

    local, domain = str_value.split("@", 1)
    if len(local) <= 2:
        return f"***@{domain}"

    return f"{local[0]}***@{domain}"


def _redact_preserve_type(value: Any, options: dict[str, Any] | None = None) -> Any:
    """Type-preserving redaction - maintains data type.

    Args:
        value: Value to redact
        options: Optional configuration

    Returns:
        Redacted value of same type
    """
    if value is None:
        return None
    elif isinstance(value, bool):
        return False
    elif isinstance(value, int):
        return 0
    elif isinstance(value, float):
        return 0.0
    elif isinstance(value, list):
        return []
    elif isinstance(value, dict):
        return {}
    else:
        return "[REDACTED]"
