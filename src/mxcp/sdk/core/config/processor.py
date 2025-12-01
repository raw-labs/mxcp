"""
Core configuration processor for two-stage configuration handling.

This module provides the ResolverEngine class that:
1. Loads resolver configuration (vault, 1password, etc.)
2. Processes other YAML configuration files with reference resolution
3. Tracks and manages external references
"""

import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import yaml

from .loader import load_resolver_config
from .models import OnePasswordConfigModel, ResolverConfigModel, VaultConfigModel
from .plugins import ResolverPlugin, ResolverRegistry
from .resolvers import EnvResolver, FileResolver, OnePasswordResolver, VaultResolver

logger = logging.getLogger(__name__)


@dataclass
class ResolvedReference:
    """
    Represents a resolved external reference with full tracking information.

    This dataclass captures all information about a reference resolution,
    including the original value, resolved value, resolver used, timing,
    and any errors that occurred during resolution.

    Attributes:
        path: Path to the value in the configuration as a list of keys/indices.
              For example, ['database', 'host'] for config['database']['host'].
        original_value: The original reference string before resolution
                       (e.g., "vault://secret/db#password", "${DB_HOST}").
        resolved_value: The value after resolution. If resolution failed,
                       this will be the same as original_value.
        resolver_name: Name of the resolver that handled this reference
                      (e.g., "vault", "env", "file", "onepassword").
        resolved_at: Unix timestamp when the resolution occurred.
        error: Error message if resolution failed, None if successful.

    Example:
        ```python
        ref = ResolvedReference(
            path=['database', 'password'],
            original_value='vault://secret/db#password',
            resolved_value='secret123',
            resolver_name='vault',
            resolved_at=1640995200.0,
            error=None
        )
        ```
    """

    path: list[str | int]  # Path to the value in the config dict
    original_value: str  # Original reference string (e.g., "vault://secret/db#password")
    resolved_value: str  # Resolved value
    resolver_name: str  # Name of resolver used
    resolved_at: float  # Timestamp when resolved
    error: str | None = None  # Error message if resolution failed


class ResolverEngine:
    """
    Main engine for configuration processing with reference resolution.

    ResolverEngine implements a modern plugin-based configuration system that supports
    external reference resolution from multiple sources including environment variables,
    files, HashiCorp Vault, and 1Password. It follows a two-stage approach:

    1. **Load resolver configuration** (vault settings, 1password settings, etc.)
    2. **Process application configuration** with reference resolution and tracking

    ## Key Features

    - **Plugin Architecture**: Extensible resolver system for different reference types
    - **Reference Tracking**: Track all resolved references for debugging and monitoring
    - **Context Manager Support**: Automatic resource cleanup with 'with' statements
    - **Validation Support**: Optional JSON schema validation of resolved configurations
    - **Error Handling**: Graceful handling of resolution failures with detailed tracking

    ## Built-in Resolvers

    - **Environment Variables**: `${VAR_NAME}` - resolves to environment variable values
    - **File References**: `file://path/to/file` - reads content from filesystem
    - **Vault References**: `vault://secret/path#key` - retrieves secrets from HashiCorp Vault
    - **1Password References**: `op://vault/item/field` - retrieves secrets from 1Password

    ## Configuration Format

    Resolver configuration uses the following YAML structure:

    ```yaml
    config:
      vault:
        enabled: true
        address: "https://vault.example.com"
        token_env: "VAULT_TOKEN"
      onepassword:
        enabled: true
        token_env: "OP_SERVICE_ACCOUNT_TOKEN"
    ```

    ## Usage Examples

    ### Basic Usage

    ```python
    from mxcp.sdk.core.config import ResolverEngine

    # Create engine with default configuration
    engine = ResolverEngine()

    # Process a configuration with references
    config = {
        'database': {
            'host': '${DB_HOST}',
            'password': 'vault://secret/db#password'
        }
    }

    resolved = engine.process_config(config)
    print(resolved['database']['host'])  # Resolved value
    ```

    ### With Custom Configuration

    ```python
    # Load configuration from file
    engine = ResolverEngine.from_config_file("config.yaml")

    # Or create from dictionary
    config_dict = {
        'config': {
            'vault': {
                'enabled': True,
                'address': 'https://vault.example.com',
                'token_env': 'VAULT_TOKEN'
            }
        }
    }
    engine = ResolverEngine.from_dict(config_dict)
    ```

    ### Context Manager (Recommended)

    ```python
    # Automatic cleanup with context manager
    with ResolverEngine.from_config_file("config.yaml") as engine:
        resolved = engine.process_file("app.yaml")
        # Automatic cleanup on exit
    ```

    ### Reference Tracking

    ```python
    engine = ResolverEngine()
    resolved = engine.process_config(config, track_references=True)

    # Get tracking information
    references = engine.get_resolved_references()
    failed_refs = engine.get_failed_references()
    summary = engine.get_reference_summary()

    for ref in references:
        print(f"Path: {ref.path}")
        print(f"Original: {ref.original_value}")
        print(f"Resolved: {ref.resolved_value}")
        print(f"Resolver: {ref.resolver_name}")
    ```

    ### Custom Resolvers

    ```python
    from mxcp.sdk.core.config import ResolverPlugin

    class CustomResolver(ResolverPlugin):
        @property
        def name(self) -> str:
            return "custom"

        @property
        def url_patterns(self) -> List[str]:
            return [r'custom://.*']

        def can_resolve(self, reference: str) -> bool:
            return reference.startswith('custom://')

        def resolve(self, reference: str) -> str:
            # Custom resolution logic
            return "custom_value"

    engine = ResolverEngine()
    engine.register_resolver(CustomResolver())
    ```

    ## Error Handling

    The engine gracefully handles resolution failures:

    - Failed references are tracked but don't raise exceptions
    - Original values are preserved when resolution fails
    - Detailed error information is available via `get_failed_references()`
    - Warning logs are emitted for failed resolutions

    ## Thread Safety

    ResolverEngine instances are not thread-safe. Create separate instances
    for concurrent use or implement appropriate locking.

    ## Resource Management

    Some resolvers (Vault, 1Password) may create external clients. Always use
    context managers or call `cleanup()` explicitly to ensure proper resource cleanup:

    ```python
    # Preferred: Context manager
    with ResolverEngine() as engine:
        result = engine.process_config(config)

    # Alternative: Explicit cleanup
    engine = ResolverEngine()
    try:
        result = engine.process_config(config)
    finally:
        engine.cleanup()
    ```
    """

    def __init__(self, resolver_config: ResolverConfigModel | None = None):
        """
        Initialize the ResolverEngine.

        Args:
            resolver_config: Optional resolver configuration. If None, uses default config.
        """
        self.resolver_config = resolver_config or ResolverConfigModel()
        self.registry = ResolverRegistry()
        self._resolved_references: list[ResolvedReference] = []
        self._current_config_path: list[str | int] = []
        self._initialize_resolvers()

    @classmethod
    def from_config_file(cls, config_path: str | Path | None = None) -> "ResolverEngine":
        """
        Create a ResolverEngine from a configuration file.

        Args:
            config_path: Path to the resolver configuration file.
                        If None, looks for 'mxcp-config.yml' in current directory.

        Returns:
            ResolverEngine instance
        """
        path_to_load = None
        if config_path:
            path_to_load = Path(config_path)
        config = load_resolver_config(path_to_load)
        return cls(config)

    @classmethod
    def from_dict(cls, config_dict: dict[str, Any]) -> "ResolverEngine":
        """
        Create a ResolverEngine from a configuration dictionary.

        Args:
            config_dict: Dictionary containing resolver configuration

        Returns:
            ResolverEngine instance
        """
        # Convert dict to ResolverConfig
        config_section = config_dict.get("config", {})

        vault_config = None
        onepassword_config = None

        if "vault" in config_section:
            vault_config = VaultConfigModel.model_validate(config_section["vault"])
        if "onepassword" in config_section:
            onepassword_config = OnePasswordConfigModel.model_validate(
                config_section["onepassword"]
            )

        resolver_config = ResolverConfigModel(vault=vault_config, onepassword=onepassword_config)
        return cls(resolver_config)

    def _initialize_resolvers(self) -> None:
        """Initialize the built-in resolvers based on configuration."""
        # Environment variable resolver - always enabled by default
        self.registry.register(EnvResolver())

        # File resolver - always enabled by default
        self.registry.register(FileResolver())

        # Vault resolver - only if configured
        if self.resolver_config and self.resolver_config.vault:
            vault_config = self.resolver_config.vault
            if vault_config.enabled:
                self.registry.register(VaultResolver(vault_config.model_dump()))

        # 1Password resolver - only if configured
        if self.resolver_config and self.resolver_config.onepassword:
            op_config = self.resolver_config.onepassword
            if op_config.enabled:
                self.registry.register(OnePasswordResolver(op_config.model_dump()))

        logger.debug(f"Initialized {len(self.registry.list_resolvers())} resolvers")

    def register_resolver(self, resolver: ResolverPlugin) -> None:
        """
        Register a custom resolver plugin.

        Args:
            resolver: The resolver plugin to register
        """
        self.registry.register(resolver)
        logger.debug(f"Registered custom resolver: {resolver.name}")

    def list_resolvers(self) -> list[str]:
        """
        List all registered resolver names.

        Returns:
            List of resolver names
        """
        return self.registry.list_resolvers()

    def process_file(
        self,
        file_path: str | Path,
        track_references: bool = True,
    ) -> dict[str, Any]:
        """
        Process a YAML configuration file with reference resolution.

        Args:
            file_path: Path to the YAML file to process
            track_references: Whether to track resolved references

        Returns:
            Processed configuration dictionary
        """
        file_path = Path(file_path)

        if not file_path.exists():
            raise FileNotFoundError(f"Configuration file not found: {file_path}")

        try:
            with open(file_path) as f:
                config_data = yaml.safe_load(f)
        except yaml.YAMLError as e:
            raise ValueError(f"Invalid YAML in {file_path}: {e}") from e

        if config_data is None:
            config_data = {}

        return self.process_config(config_data, track_references)

    def process_config(
        self,
        config_data: dict[str, Any],
        track_references: bool = True,
    ) -> dict[str, Any]:
        """
        Process a configuration dictionary with reference resolution.

        Args:
            config_data: Configuration dictionary to process
            track_references: Whether to track resolved references

        Returns:
            Processed configuration dictionary
        """
        # Clear previous references if tracking new ones
        if track_references:
            self._resolved_references.clear()

        # Resolve all references
        resolved_config = self._resolve_references(config_data, track_references)

        return cast(dict[str, Any], resolved_config)

    def _resolve_references(self, config: Any, track_references: bool = True) -> Any:
        """Recursively resolve references in configuration."""
        if isinstance(config, dict):
            resolved_dict = {}
            for key, value in config.items():
                self._current_config_path.append(key)
                resolved_dict[key] = self._resolve_references(value, track_references)
                self._current_config_path.pop()
            return resolved_dict
        elif isinstance(config, list):
            resolved_list = []
            for i, item in enumerate(config):
                self._current_config_path.append(i)
                resolved_list.append(self._resolve_references(item, track_references))
                self._current_config_path.pop()
            return resolved_list
        elif isinstance(config, str):
            return self._resolve_string_references(config, track_references)
        else:
            return config

    def _resolve_string_references(self, value: str, track_references: bool = True) -> str:
        """Resolve references in a string value."""
        if not self._has_references(value):
            return value

        # For now, resolve entire string as single reference
        # TODO: Support interpolation of multiple references in one string
        try:
            resolver = self.registry.find_resolver_for_reference(value)
            if not resolver:
                logger.warning(f"No resolver found for reference '{value}'")
                return value

            resolved_value = resolver.resolve(value)

            # Track the reference if requested
            if track_references:
                ref = ResolvedReference(
                    path=self._current_config_path.copy(),
                    original_value=value,
                    resolved_value=resolved_value,
                    resolver_name=resolver.name,
                    resolved_at=time.time(),
                )
                self._resolved_references.append(ref)

            return resolved_value

        except Exception as e:
            error_msg = f"Failed to resolve reference '{value}': {e}"

            # Track the error if requested
            if track_references:
                ref = ResolvedReference(
                    path=self._current_config_path.copy(),
                    original_value=value,
                    resolved_value=value,  # Keep original value
                    resolver_name="unknown",
                    resolved_at=time.time(),
                    error=error_msg,
                )
                self._resolved_references.append(ref)

            logger.warning(error_msg)
            return value

    def _has_references(self, value: str) -> bool:
        """Check if a string contains any references using the registry."""
        return self.registry.find_resolver_for_reference(value) is not None

    def get_resolver_config(self) -> ResolverConfigModel | None:
        """Get the current resolver configuration."""
        return self.resolver_config

    def cleanup(self) -> None:
        """Clean up all resolver resources."""
        self.registry.cleanup_all()

    def __enter__(self) -> "ResolverEngine":
        """Context manager entry."""
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Context manager exit - calls cleanup."""
        self.cleanup()

    def get_resolved_references(self) -> list[ResolvedReference]:
        """
        Get all resolved references from the last processing operation.

        Returns:
            List of ResolvedReference objects
        """
        return self._resolved_references.copy()

    def get_references_by_type(self, ref_type: str) -> list[ResolvedReference]:
        """
        Get resolved references filtered by resolver type.

        Args:
            ref_type: The resolver type to filter by (e.g., 'vault', 'env', 'file')

        Returns:
            List of ResolvedReference objects for the specified type
        """
        return [ref for ref in self._resolved_references if ref.resolver_name == ref_type]

    def get_failed_references(self) -> list[ResolvedReference]:
        """
        Get all references that failed to resolve.

        Returns:
            List of ResolvedReference objects with errors
        """
        return [ref for ref in self._resolved_references if ref.error is not None]

    def find_references_in_config(
        self, config: dict[str, Any]
    ) -> list[tuple[list[str | int], str, str]]:
        """
        Find all external references in a configuration without resolving them.

        Args:
            config: Configuration dictionary to scan

        Returns:
            List of tuples (path, original_value, resolver_type)
        """
        references = []

        def _scan_config(obj: Any, path: list[str | int]) -> None:
            if isinstance(obj, dict):
                for key, value in obj.items():
                    _scan_config(value, path + [key])
            elif isinstance(obj, list):
                for i, item in enumerate(obj):
                    _scan_config(item, path + [i])
            elif isinstance(obj, str):
                resolver = self.registry.find_resolver_for_reference(obj)
                if resolver:
                    references.append((path.copy(), obj, resolver.name))

        _scan_config(config, [])
        return references

    def get_reference_summary(self) -> dict[str, Any]:
        """
        Get a summary of all resolved references.

        Returns:
            Dictionary with reference statistics and details
        """
        total_refs = len(self._resolved_references)
        successful_refs = len([ref for ref in self._resolved_references if ref.error is None])
        failed_refs = total_refs - successful_refs

        # Group by resolver type
        by_type = {}
        for ref in self._resolved_references:
            resolver_name = ref.resolver_name
            if resolver_name not in by_type:
                by_type[resolver_name] = {"total": 0, "successful": 0, "failed": 0}
            by_type[resolver_name]["total"] += 1
            if ref.error is None:
                by_type[resolver_name]["successful"] += 1
            else:
                by_type[resolver_name]["failed"] += 1

        return {
            "total_references": total_refs,
            "successful_references": successful_refs,
            "failed_references": failed_refs,
            "by_resolver_type": by_type,
            "registered_resolvers": self.list_resolvers(),
        }
