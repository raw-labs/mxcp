"""Test redaction strategies and functionality."""

import pytest

from mxcp.sdk.audit import RedactionStrategy, apply_redaction


def test_full_redaction():
    """Test complete redaction strategy."""
    assert apply_redaction("sensitive_data", RedactionStrategy.FULL) == "[REDACTED]"
    assert apply_redaction(None, RedactionStrategy.FULL) == "[REDACTED]"
    assert apply_redaction(12345, RedactionStrategy.FULL) == "[REDACTED]"


def test_partial_redaction():
    """Test partial redaction strategy."""
    # Default partial redaction
    assert apply_redaction("1234567890", RedactionStrategy.PARTIAL) == "12***90"
    assert apply_redaction("short", RedactionStrategy.PARTIAL) == "[REDACTED]"

    # Custom options
    assert (
        apply_redaction("1234567890", RedactionStrategy.PARTIAL, {"show_first": 0, "show_last": 4})
        == "***7890"
    )
    assert (
        apply_redaction("1234567890", RedactionStrategy.PARTIAL, {"show_first": 3, "show_last": 0})
        == "123***"
    )


def test_hash_redaction():
    """Test hash redaction strategy."""
    hashed = apply_redaction("secret_value", RedactionStrategy.HASH)
    assert hashed.startswith("sha256:")
    assert len(hashed) == 71  # "sha256:" + 64 hex chars

    # Same input produces same hash
    hashed2 = apply_redaction("secret_value", RedactionStrategy.HASH)
    assert hashed == hashed2

    # Different input produces different hash
    hashed3 = apply_redaction("different_value", RedactionStrategy.HASH)
    assert hashed != hashed3


def test_truncate_redaction():
    """Test truncate redaction strategy."""
    assert apply_redaction("verylongstring", RedactionStrategy.TRUNCATE) == "verylongst..."
    assert apply_redaction("short", RedactionStrategy.TRUNCATE) == "short"

    # Custom length
    assert (
        apply_redaction("verylongstring", RedactionStrategy.TRUNCATE, {"length": 5}) == "veryl..."
    )


def test_email_redaction():
    """Test email-specific redaction strategy."""
    assert apply_redaction("john.doe@example.com", RedactionStrategy.EMAIL) == "j***@example.com"
    assert apply_redaction("a@b.com", RedactionStrategy.EMAIL) == "***@b.com"
    assert apply_redaction("user@company.org", RedactionStrategy.EMAIL) == "u***@company.org"

    # Edge cases
    assert apply_redaction("invalid-email", RedactionStrategy.EMAIL) == "[REDACTED]"
    assert apply_redaction(None, RedactionStrategy.EMAIL) == "[REDACTED]"


def test_preserve_type_redaction():
    """Test type-preserving redaction strategy."""
    assert apply_redaction("string", RedactionStrategy.PRESERVE_TYPE) == "[REDACTED]"
    assert apply_redaction(123, RedactionStrategy.PRESERVE_TYPE) == 0
    assert apply_redaction(45.67, RedactionStrategy.PRESERVE_TYPE) == 0.0
    assert not apply_redaction(True, RedactionStrategy.PRESERVE_TYPE)
    assert apply_redaction([1, 2, 3], RedactionStrategy.PRESERVE_TYPE) == []
    assert apply_redaction({"key": "value"}, RedactionStrategy.PRESERVE_TYPE) == {}
    assert apply_redaction(None, RedactionStrategy.PRESERVE_TYPE) is None


def test_redaction_options():
    """Test redaction strategy options."""
    # Partial redaction options
    result = apply_redaction(
        "1234567890", RedactionStrategy.PARTIAL, {"show_first": 4, "show_last": 2, "min_length": 6}
    )
    assert result == "1234***90"

    # Email redaction options
    result = apply_redaction(
        "user@example.com", RedactionStrategy.EMAIL, {"preserve_domain": False}
    )
    assert result == "[REDACTED]"

    # Truncate options
    result = apply_redaction(
        "verylongstring", RedactionStrategy.TRUNCATE, {"length": 8, "suffix": "!!!"}
    )
    assert result == "verylong!!!"


def test_invalid_strategy():
    """Test handling of invalid redaction strategies."""
    # This would normally be caught at the enum level, but test the function
    with pytest.raises(ValueError, match="Unknown redaction strategy"):
        from mxcp.sdk.audit.redaction import apply_redaction as _apply_redaction

        # Simulate invalid enum value by monkey-patching
        class FakeStrategy:
            value = "invalid"

        _apply_redaction("test", FakeStrategy())
