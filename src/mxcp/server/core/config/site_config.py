from __future__ import annotations

import logging
from pathlib import Path

import yaml
from pydantic import ValidationError

from mxcp.server.core.config.models import (
    SiteConfigModel,
    UserConfigModel,
    UserProfileConfigModel,
)
from mxcp.server.core.refs.migration import check_and_migrate_legacy_version

logger = logging.getLogger(__name__)

__all__ = ["load_site_config", "find_repo_root", "get_active_profile"]


def find_repo_root() -> Path:
    """Find the repository root by looking for mxcp-site.yml.

    Returns:
        Path to the repository root

    Raises:
        FileNotFoundError: If mxcp-site.yml is not found in current directory or any parent
    """
    current = Path.cwd()
    for parent in [current] + list(current.parents):
        if (parent / "mxcp-site.yml").exists():
            return parent
    raise FileNotFoundError("mxcp-site.yml not found in current directory or any parent directory")


def load_site_config(repo_path: Path | None = None) -> SiteConfigModel:
    """Load and validate the mxcp-site.yml configuration from the repository.

    Args:
        repo_path: Optional path to the repository root. If not provided, uses current directory.

    Returns:
        The loaded and validated site configuration

    Raises:
        FileNotFoundError: If mxcp-site.yml is not found
        ValueError: If validation fails
    """
    if repo_path is None:
        repo_path = Path.cwd()

    config_path = repo_path / "mxcp-site.yml"
    if not config_path.exists():
        raise FileNotFoundError(f"mxcp-site.yml not found at {config_path}")

    with open(config_path) as f:
        config = yaml.safe_load(f) or {}

    # Check for legacy version format and provide migration guidance (stops execution)
    check_and_migrate_legacy_version(config, "site", str(config_path))

    try:
        return SiteConfigModel.model_validate(
            config,
            context={"repo_root": config_path.parent},
        )
    except ValidationError as exc:
        raise ValueError(f"Site config validation error: {exc}") from exc


def get_active_profile(
    user_config: UserConfigModel, site_config: SiteConfigModel, profile: str | None = None
) -> UserProfileConfigModel:
    """Get the active profile from the user config based on site configuration.

    Args:
        user_config: The user configuration loaded from ~/.mxcp/config.yml
        site_config: The site configuration loaded from mxcp-site.yml
        profile: Optional profile name to override the default profile

    Returns:
        The active profile configuration
    """
    project_name = site_config.project
    profile_name = profile or site_config.profile

    project = user_config.projects.get(project_name)
    if not project:
        raise ValueError(f"Project '{project_name}' not found in user config")

    profile_config = project.profiles.get(profile_name)
    if not profile_config:
        raise ValueError(f"Profile '{profile_name}' not found in project '{project_name}'")

    return profile_config
