"""
External configuration reference tracking and resolution.

This module provides functionality to track and resolve external configuration
values (vault://, file://, environment variables). Configuration reloading is
handled via SIGHUP signal, which re-reads all config files from disk.
"""

import copy
import logging
from dataclasses import dataclass
from typing import Any

from mxcp.server.core.config.schema_utils import should_interpolate_path
from mxcp.server.core.refs.resolver import (
    find_references,
    resolve_value,
)

logger = logging.getLogger(__name__)


@dataclass
class ExternalRef:
    """Represents an external configuration reference."""

    path: list[str | int]  # Path to the value in the config dict
    source: str  # Original reference string (e.g., "vault://secret/db#password")
    ref_type: str  # Type: "vault", "file", or "env"
    last_resolved: Any | None = None
    last_error: str | None = None

    def resolve(
        self,
        vault_config: dict[str, Any] | None = None,
        op_config: dict[str, Any] | None = None,
    ) -> Any:
        """Resolve this reference to its current value."""
        try:
            value = resolve_value(self.source, vault_config, op_config)
            self.last_error = None
            return value
        except Exception as e:
            self.last_error = str(e)
            logger.error(f"Failed to resolve {self.ref_type} reference '{self.source}': {e}")
            raise


class ExternalRefTracker:
    """Tracks and manages external configuration references."""

    def __init__(self) -> None:
        self.refs: list[ExternalRef] = []
        self._template_config: dict[str, Any] | None = None
        self._resolved_config: dict[str, Any] | None = None

    def set_template(self, site_config: dict[str, Any], user_config: dict[str, Any]) -> None:
        """Set the template configuration and scan for references."""
        self._template_config = {
            "site": copy.deepcopy(site_config),
            "user": copy.deepcopy(user_config),
        }

        # Scan both configs for external references using the unified function
        self.refs = []

        # Convert find_references results to ExternalRef objects
        user_refs = find_references(user_config, ["user"])
        for path, source, ref_type in user_refs:
            self.refs.append(ExternalRef(path, source, ref_type))

        # Note: We could also scan site_config if it supports external refs in the future

        logger.info(f"Found {len(self.refs)} external references in configuration")
        for ref in self.refs:
            logger.debug(f"  {ref.ref_type}: {ref.source} at {'.'.join(map(str, ref.path))}")

    def resolve_all(
        self,
        vault_config: dict[str, Any] | None = None,
        op_config: dict[str, Any] | None = None,
        project_name: str | None = None,
        profile_name: str | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Resolve external references and return updated configs.

        Uses selective interpolation if project_name and profile_name are provided,
        which only resolves references for the active profile and top-level config.
        This prevents errors from undefined environment variables in inactive profiles.

        Args:
            vault_config: Optional vault configuration. If not provided, will try to extract from template.
            op_config: Optional 1Password configuration. If not provided, will try to extract from template.
            project_name: Optional project name for selective interpolation. If provided with profile_name,
                         only resolves refs for this project/profile and top-level config.
            profile_name: Optional profile name for selective interpolation.

        Returns:
            Tuple of (site_config, user_config) with resolved values
        """
        if not self._template_config:
            raise RuntimeError("No template configuration set")

        # If vault_config not provided, try to get it from the template
        if vault_config is None and "user" in self._template_config:
            vault_config = self._template_config["user"].get("vault")

        # If op_config not provided, try to get it from the template
        if op_config is None and "user" in self._template_config:
            op_config = self._template_config["user"].get("onepassword")

        # Deep copy the template
        resolved = copy.deepcopy(self._template_config)

        # Determine which refs to resolve based on selective interpolation
        refs_to_resolve = self.refs
        if project_name is not None and profile_name is not None:
            # Selective interpolation: only resolve refs for active profile + top-level
            refs_to_resolve = self._filter_refs_for_selective_interpolation(
                project_name, profile_name
            )
            logger.debug(
                f"Selective interpolation: resolving {len(refs_to_resolve)}/{len(self.refs)} refs "
                f"for project={project_name}, profile={profile_name}"
            )

        # Resolve each reference
        resolution_errors = []
        for ref in refs_to_resolve:
            try:
                value = ref.resolve(vault_config, op_config)
                ref.last_resolved = value

                # Apply the resolved value
                self._apply_value(resolved, ref.path, value)

            except Exception as e:
                resolution_errors.append(f"{ref.source}: {e}")

        if resolution_errors:
            error_msg = "Failed to resolve some external references:\n" + "\n".join(
                resolution_errors
            )
            logger.error(error_msg)
            raise ValueError(error_msg)

        self._resolved_config = resolved
        return resolved["site"], resolved["user"]

    def _apply_value(self, config: dict[str, Any], path: list[str | int], value: Any) -> None:
        """Apply a resolved value at the specified path in the config."""
        current: Any = config

        # Navigate to the parent of the target
        for key in path[:-1]:
            if isinstance(current, dict) and isinstance(key, str):  # noqa: SIM114
                current = current[key]
            elif isinstance(current, list) and isinstance(key, int):
                current = current[key]
            else:
                raise TypeError(f"Invalid path segment {key} for type {type(current)}")

        # Set the value
        final_key = path[-1]
        if isinstance(current, dict) and isinstance(final_key, str):  # noqa: SIM114
            current[final_key] = value
        elif isinstance(current, list) and isinstance(final_key, int):
            current[final_key] = value
        else:
            raise TypeError(f"Invalid final key {final_key} for type {type(current)}")

    def _filter_refs_for_selective_interpolation(
        self, project_name: str, profile_name: str
    ) -> list[ExternalRef]:
        """Filter refs to only include those for active profile and top-level config.

        Uses should_interpolate_path() for the interpolation decision logic.

        Args:
            project_name: Active project name
            profile_name: Active profile name

        Returns:
            List of ExternalRefs that should be resolved
        """
        refs_to_resolve = []

        for ref in self.refs:
            if should_interpolate_path(ref.path, project_name, profile_name):
                refs_to_resolve.append(ref)
            else:
                # Skip this ref (inactive profile)
                logger.debug(f"Skipping ref in inactive profile: {'.'.join(map(str, ref.path))}")

        return refs_to_resolve
