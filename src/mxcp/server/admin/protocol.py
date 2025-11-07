"""
Protocol definitions for admin API.

This module defines interfaces that the admin API requires from the MXCP server.
Keeping protocols separate avoids circular import issues.
"""

from typing import Any, Protocol


class AdminServerProtocol(Protocol):
    """
    Protocol defining what the admin API needs from the server.

    This protocol ensures the admin API remains decoupled from the
    specific server implementation.
    """

    profile_name: str
    site_config: dict[str, Any]
    user_config: dict[str, Any]
    debug: bool
    readonly: bool

    def reload_configuration(self) -> Any:
        """Request a configuration reload and return a ReloadRequest."""
        ...

    def get_config_info(self) -> dict[str, Any]:
        """Get configuration information."""
        ...

    def get_endpoint_counts(self) -> dict[str, int]:
        """Get counts of registered endpoints."""
        ...

