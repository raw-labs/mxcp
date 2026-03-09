"""CapabilityMapper translates IdP claims into MXCP capabilities."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class CapabilityMapper:
    """Maps IdP claims to MXCP capabilities using claim-path-based config.

    Claim paths point into the raw token/userinfo JSON:
    - Top-level keys: "scope", "email_verified"
    - Dot-separated nested paths: "realm_access.roles"
    - URI-namespaced keys: "https://mycompany.com/roles"

    URI keys (exact match) take precedence over dot traversal.
    """

    def __init__(self, claim_mappings: dict[str, dict[str, list[str]]]) -> None:
        self._mappings = claim_mappings

    def derive(self, raw_profile: dict[str, Any]) -> set[str]:
        """Derive capabilities from a raw claims profile."""
        capabilities: set[str] = set()
        for claim_path, value_map in self._mappings.items():
            claim_value = self._resolve_path(raw_profile, claim_path)
            if claim_value is None:
                logger.debug("Claim path '%s' not found in profile", claim_path)
                continue
            for value in self._normalize_claim_value(claim_value):
                if value in value_map:
                    capabilities.update(value_map[value])
        return capabilities

    def _resolve_path(self, profile: dict[str, Any], path: str) -> Any:
        """Resolve a claim path in the profile dict.

        Tries exact key match first (handles URI keys like
        "https://mycompany.com/roles"), then dot-separated traversal.
        """
        if path in profile:
            return profile[path]
        parts = path.split(".")
        current: Any = profile
        for part in parts:
            if not isinstance(current, dict) or part not in current:
                return None
            current = current[part]
        return current

    @staticmethod
    def _normalize_claim_value(value: Any) -> list[str]:
        """Normalize a claim value to a list of strings for matching."""
        if isinstance(value, list):
            return [CapabilityMapper._scalar_to_str(v) for v in value]
        if isinstance(value, str) and " " in value:
            return value.split()
        return [CapabilityMapper._scalar_to_str(value)]

    @staticmethod
    def _scalar_to_str(value: Any) -> str:
        """Convert a scalar to its string form, using lowercase for booleans."""
        if isinstance(value, bool):
            return str(value).lower()
        return str(value)
