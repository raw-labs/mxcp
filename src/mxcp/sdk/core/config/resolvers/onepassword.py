"""
1Password resolver.

This module provides the OnePasswordResolver class for resolving 1Password
references like op://vault/item/field using the OnePassword SDK.
"""

import logging
import os
import re
from typing import Any, Dict, List, Optional

from .base import ResolverPlugin

logger = logging.getLogger(__name__)


class OnePasswordResolver(ResolverPlugin):
    """Resolver for 1Password references like op://vault/item/field using the OnePassword SDK."""

    OP_URL_PATTERN = re.compile(r"op://([^/]+)/([^/]+)/([^/?]+)(?:\?attribute=(otp))?$")

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        self._client = None
        self._original_token = None
        self._token_was_set = False

    @property
    def name(self) -> str:
        return "onepassword"

    @property
    def url_patterns(self) -> List[str]:
        return [r"op://([^/]+)/([^/]+)/([^/?]+)(?:\?attribute=(otp))?$"]

    def can_resolve(self, reference: str) -> bool:
        return reference.startswith("op://")

    def validate_config(self) -> bool:
        if not self.config.get("enabled", False):
            return False

        token_env = self.config.get("token_env", "OP_SERVICE_ACCOUNT_TOKEN")
        if not os.environ.get(token_env):
            logger.error(f"1Password token environment variable not found: {token_env}")
            return False

        # Check if SDK is available
        try:
            import onepassword  # type: ignore
        except ImportError:
            logger.error(
                "onepassword-sdk library is not available. Install with: pip install 'mxcp[onepassword]'"
            )
            return False

        return True

    def resolve(self, reference: str) -> str:
        match = self.OP_URL_PATTERN.match(reference)
        if not match:
            raise ValueError(f"Invalid 1Password reference: {reference}")

        vault_name = match.group(1)
        item_name = match.group(2)
        field_name = match.group(3)
        attribute = match.group(4)  # 'otp' or None

        # Build the secret reference - new SDK format
        if attribute == "otp":
            secret_ref = f"op://{vault_name}/{item_name}/{field_name}?attribute=totp"
        else:
            secret_ref = f"op://{vault_name}/{item_name}/{field_name}"

        # Get the configured token
        token_env = self.config.get("token_env", "OP_SERVICE_ACCOUNT_TOKEN")
        op_token = os.environ.get(token_env)
        if not op_token:
            raise ValueError(
                f"1Password service account token not found in environment variable '{token_env}'"
            )

        # Set up the SDK token environment properly
        self._setup_sdk_token(op_token)

        try:
            # Initialize 1Password client if needed
            if not self._client:
                self._init_client()

            # Ensure client is properly initialized
            if not self._client:
                raise ValueError("Failed to initialize 1Password client")

            # Resolve the secret - following the same pattern as original references.py
            secret_value = str(self._client.secrets.resolve(secret_ref))
            return secret_value

        except Exception as e:
            raise ValueError(f"Failed to resolve 1Password reference '{reference}': {e}") from e
        finally:
            # Clean up environment changes
            self._restore_sdk_token()

    def cleanup(self) -> None:
        """Clean up the 1Password client and restore environment."""
        self._client = None
        self._restore_sdk_token()

    def _init_client(self):
        """Initialize the 1Password client."""
        try:
            import onepassword  # type: ignore
        except ImportError:
            raise ImportError(
                "onepassword-sdk library is required for 1Password integration. Install with: pip install 'mxcp[onepassword]'"
            )

        self._client = onepassword.Client()

    def _setup_sdk_token(self, op_token: str) -> None:
        """Set up the OP_SERVICE_ACCOUNT_TOKEN environment variable for the SDK."""
        # Store the original state
        self._original_token = os.environ.get("OP_SERVICE_ACCOUNT_TOKEN")
        self._token_was_set = self._original_token is not None

        # Only set the token if it's not already set to the correct value
        if self._original_token != op_token:
            os.environ["OP_SERVICE_ACCOUNT_TOKEN"] = op_token

    def _restore_sdk_token(self) -> None:
        """Restore the original OP_SERVICE_ACCOUNT_TOKEN environment variable."""
        if self._original_token is not None:
            # Check if we need to restore the original value
            current_token = os.environ.get("OP_SERVICE_ACCOUNT_TOKEN")
            if current_token != self._original_token:
                if self._token_was_set:
                    os.environ["OP_SERVICE_ACCOUNT_TOKEN"] = self._original_token
                else:
                    # Remove the variable if it wasn't originally set
                    os.environ.pop("OP_SERVICE_ACCOUNT_TOKEN", None)

        # Reset tracking variables
        self._original_token = None
        self._token_was_set = False
