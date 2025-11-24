import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from mxcp.server.core.config.models import SiteConfigModel, UserConfigModel
from mxcp.server.core.refs.migration import check_and_migrate_legacy_version
from mxcp.server.core.refs.resolver import interpolate_all, interpolate_selective

# No logging in this module as it's indirectly used to load the logging config

__all__ = ["load_user_config"]


def _generate_default_config(site_config: SiteConfigModel) -> UserConfigModel:
    """Generate a default user config based on site config."""
    project_name = site_config.project
    profile_name = site_config.profile

    config = {
        "mxcp": 1,
        "projects": {
            project_name: {"profiles": {profile_name: {"secrets": [], "plugin": {"config": {}}}}}
        },
    }
    return UserConfigModel.model_validate(config)


def _ensure_project_structure(config: dict[str, Any], project_name: str, profile_name: str) -> None:
    projects = config.setdefault("projects", {})
    project_config = projects.setdefault(project_name, {})
    profiles = project_config.setdefault("profiles", {})
    profiles.setdefault(profile_name, {})


def load_user_config(
    site_config: SiteConfigModel,
    active_profile: str | None = None,
    generate_default: bool = True,
    resolve_refs: bool = True,
) -> UserConfigModel:
    """Load the user configuration from ~/.mxcp/config.yml or MXCP_CONFIG env var."""
    path = Path(os.environ.get("MXCP_CONFIG", Path.home() / ".mxcp" / "config.yml"))
    project_name = site_config.project
    profile_name = active_profile or site_config.profile

    if not path.exists():
        if "MXCP_CONFIG" not in os.environ and generate_default:
            return _generate_default_config(site_config)
        raise FileNotFoundError(f"MXCP user config not found at {path}")

    with open(path) as f:
        config_data = yaml.safe_load(f) or {}

    if not isinstance(config_data, dict):
        raise ValueError("MXCP user config must be a mapping")

    # Check for legacy version format and provide migration guidance (stops execution)
    check_and_migrate_legacy_version(config_data, "user", str(path))

    # Interpolate environment variables and vault URLs in the config if requested
    if resolve_refs:
        vault_config = config_data.get("vault")
        op_config = config_data.get("onepassword")
        if active_profile is not None:
            config_data = interpolate_selective(
                config_data, project_name, profile_name, vault_config, op_config
            )
        else:
            config_data = interpolate_all(config_data, vault_config, op_config)

    _ensure_project_structure(config_data, project_name, profile_name)

    try:
        return UserConfigModel.model_validate(config_data)
    except ValidationError as exc:
        raise ValueError(f"Invalid user config: {exc}") from exc
