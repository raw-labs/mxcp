"""Configuration loaders for MXCP site and user configurations.

This module consolidates the loading logic for both site and user configurations,
providing a unified interface for configuration management.
"""

# Re-export the existing functions during migration
from mxcp.config.site_config import (
    find_repo_root,
    get_active_profile,
    get_profile_root,
    load_site_config,
)
from mxcp.config.user_config import (
    get_user_config_path,
    load_user_config,
)

__all__ = [
    "find_repo_root",
    "get_active_profile", 
    "get_profile_root",
    "load_site_config",
    "get_user_config_path",
    "load_user_config",
]
