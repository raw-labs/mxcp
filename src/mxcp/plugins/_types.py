"""Type definitions for MXCP plugins module."""

from typing import TypedDict


class PluginConfig(TypedDict, total=False):
    """Configuration for a plugin.

    This is a flexible TypedDict that allows any key-value pairs
    since plugin configurations can vary widely based on the plugin type.
    """

    # Common fields that many plugins might use
    enabled: bool
    debug: bool
    # Allow any other fields
    # (TypedDict doesn't support dynamic keys, so plugins will need to
    # access additional fields via .get() or cast to Dict[str, Any])
