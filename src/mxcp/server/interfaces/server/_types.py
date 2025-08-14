"""Type definitions for MXCP server module."""

from typing import TypedDict


class ConfigInfo(TypedDict):
    """Configuration information returned by get_config_info."""

    project: str
    profile: str
    transport: str
    host: str
    port: int
    readonly: bool
    stateless: bool
    sql_tools_enabled: bool
