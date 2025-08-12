"""
Environment variable resolver.

This module provides the EnvResolver class for resolving environment variable
references like ${VAR_NAME}.
"""

import logging
import os
import re
from typing import Any, Dict, List, Optional

from ..plugins import ResolverPlugin

logger = logging.getLogger(__name__)


class EnvResolver(ResolverPlugin):
    """Resolver for environment variable references like ${VAR_NAME}."""

    ENV_VAR_PATTERN = re.compile(r"\${([A-Za-z0-9_]+)}")

    @property
    def name(self) -> str:
        return "env"

    @property
    def url_patterns(self) -> List[str]:
        return [r"\${[A-Za-z0-9_]+}"]

    def can_resolve(self, reference: str) -> bool:
        return self.ENV_VAR_PATTERN.match(reference) is not None

    def resolve(self, reference: str) -> str:
        match = self.ENV_VAR_PATTERN.match(reference)
        if not match:
            raise ValueError(f"Invalid environment variable reference: {reference}")

        var_name = match.group(1)
        value = os.environ.get(var_name)
        if value is None:
            raise ValueError(f"Environment variable not found: {var_name}")

        return value
