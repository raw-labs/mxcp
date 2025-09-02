"""Tests for the centralized version module."""

from mxcp.sdk.core import PACKAGE_NAME, PACKAGE_VERSION, get_package_info


def test_package_name():
    """Test that package name is correct."""
    assert PACKAGE_NAME == "mxcp"


def test_package_version():
    """Test that package version is not unknown."""
    assert PACKAGE_VERSION != "unknown"
    # Version should be in a reasonable format (e.g., "0.4.0" or similar)
    assert "." in PACKAGE_VERSION or PACKAGE_VERSION.startswith("0.0.0")


def test_get_package_info():
    """Test that get_package_info returns correct tuple."""
    name, version = get_package_info()
    assert name == PACKAGE_NAME
    assert version == PACKAGE_VERSION
    assert name == "mxcp"
