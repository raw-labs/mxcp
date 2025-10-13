"""Centralized package information for MXCP.

This module provides a single source of truth for the MXCP package name
and version, avoiding duplication across the codebase.
"""

__all__ = ["PACKAGE_NAME", "PACKAGE_VERSION", "get_package_info"]

# Package name constant
PACKAGE_NAME = "mxcp"

# Get package version dynamically
try:
    from importlib.metadata import version

    PACKAGE_VERSION = version(PACKAGE_NAME)
except ImportError:
    # Fallback for Python < 3.8
    try:
        import pkg_resources

        PACKAGE_VERSION = pkg_resources.get_distribution(PACKAGE_NAME).version
    except Exception:
        PACKAGE_VERSION = "unknown"


def get_package_info() -> tuple[str, str]:
    """Get the package name and version as a tuple.

    Returns:
        A tuple of (package_name, package_version)
    """
    return PACKAGE_NAME, PACKAGE_VERSION
