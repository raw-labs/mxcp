"""Utilities for working with MXCP JSON schemas."""

import json
from collections.abc import Sequence
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def get_user_config_top_level_keys() -> set[str]:
    """Get top-level property names from user config schema.

    These are properties that should always be interpolated (resolved)
    regardless of which profile is active. The 'projects' key is excluded
    because it requires special handling - only the active project/profile
    should be interpolated.

    Returns:
        Set of top-level property names (e.g., {"mxcp", "vault", "onepassword", ...})

    Note:
        This is cached since the schema doesn't change at runtime.
    """
    schema_path = Path(__file__).parent.parent.parent / "schemas" / "mxcp-config-schema-1.json"
    with open(schema_path) as f:
        schema = json.load(f)

    # Get all top-level properties except 'projects' (which needs special handling)
    all_props = set(schema.get("properties", {}).keys())

    # Remove 'projects' - it's handled specially in selective interpolation
    all_props.discard("projects")

    return all_props


def should_interpolate_path(
    path: Sequence[str | int],
    project_name: str,
    profile_name: str,
) -> bool:
    """Determine if a config path should be interpolated for the active profile.

    This is the single source of truth for selective interpolation logic.

    Interpolation rules:
    1. Site config (path[0] == "site") → YES
    2. Top-level user config (derived from schema, e.g. vault, onepassword, transport, logging, models, mxcp) → YES
    3. Active project/profile (projects.{project}.profiles.{profile}.*) → YES
    4. Everything else (inactive profiles/projects) → NO

    Args:
        path: Config path, e.g. ["user", "projects", "myproj", "profiles", "dev", "secrets"]
        project_name: Active project name
        profile_name: Active profile name

    Returns:
        True if path should be interpolated

    Examples:
        >>> should_interpolate_path(["site", "project"], "myproj", "dev")
        True  # Rule 1: site config

        >>> should_interpolate_path(["user", "vault", "url"], "myproj", "dev")
        True  # Rule 2: top-level user config

        >>> should_interpolate_path(["user", "projects", "myproj", "profiles", "dev", "secrets"], "myproj", "dev")
        True  # Rule 3: active project/profile

        >>> should_interpolate_path(["user", "projects", "myproj", "profiles", "prod", "secrets"], "myproj", "dev")
        False  # Rule 4: inactive profile (prod vs dev)
    """
    if not path:
        return False

    # Rule 1: Always interpolate site config
    if path[0] == "site":
        return True

    # All other rules are for user config
    if path[0] != "user" or len(path) < 2:
        return False

    # Rule 2: Top-level user config keys (from schema)
    top_level_keys = get_user_config_top_level_keys()
    if path[1] in top_level_keys:
        return True

    # Rule 3: Active project/profile
    # Structure: ["user", "projects", PROJECT, "profiles", PROFILE, ...]
    # Rule 4: Everything else - don't interpolate
    return (
        path[1] == "projects"
        and len(path) >= 5
        and path[2] == project_name
        and path[3] == "profiles"
        and path[4] == profile_name
    )
