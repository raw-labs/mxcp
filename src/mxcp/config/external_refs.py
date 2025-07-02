"""
External configuration reference tracking and resolution.

This module provides functionality to track and refresh external configuration
values (vault://, file://, environment variables) without reloading the entire
configuration structure.
"""
import os
import re
import time
import copy
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple, Union
from pathlib import Path

logger = logging.getLogger(__name__)

# Regular expressions for external references
ENV_VAR_PATTERN = re.compile(r'\${([A-Za-z0-9_]+)}')
VAULT_URL_PATTERN = re.compile(r'vault://([^#]+)(?:#(.+))?')
FILE_URL_PATTERN = re.compile(r'file://(.+)')


@dataclass
class ExternalRef:
    """Represents an external configuration reference."""
    path: List[Union[str, int]]  # Path to the value in the config dict
    source: str                   # Original reference string (e.g., "vault://secret/db#password")
    ref_type: str                 # Type: "vault", "file", or "env"
    last_resolved: Optional[Any] = None
    last_checked: float = 0.0
    last_error: Optional[str] = None
    
    def resolve(self, vault_config: Optional[Dict[str, Any]] = None) -> Any:
        """Resolve this reference to its current value."""
        try:
            if self.ref_type == "vault":
                from mxcp.config.user_config import _resolve_vault_url
                value = _resolve_vault_url(self.source, vault_config)
            elif self.ref_type == "file":
                from mxcp.config.user_config import _resolve_file_url
                value = _resolve_file_url(self.source)
            elif self.ref_type == "env":
                # Extract env var name
                match = ENV_VAR_PATTERN.search(self.source)
                if not match:
                    raise ValueError(f"Invalid env var pattern: {self.source}")
                env_var = match.group(1)
                if env_var not in os.environ:
                    raise ValueError(f"Environment variable {env_var} is not set")
                # Handle full string interpolation
                value = self.source
                for env_match in ENV_VAR_PATTERN.findall(self.source):
                    if env_match not in os.environ:
                        raise ValueError(f"Environment variable {env_match} is not set")
                    value = value.replace(f"${{{env_match}}}", os.environ[env_match])
            else:
                raise ValueError(f"Unknown reference type: {self.ref_type}")
            
            self.last_error = None
            return value
            
        except Exception as e:
            self.last_error = str(e)
            logger.error(f"Failed to resolve {self.ref_type} reference '{self.source}': {e}")
            raise


class ExternalRefTracker:
    """Tracks and manages external configuration references."""
    
    def __init__(self):
        self.refs: List[ExternalRef] = []
        self._template_config: Optional[Dict[str, Any]] = None
        self._resolved_config: Optional[Dict[str, Any]] = None
    
    def scan_config(self, config: Dict[str, Any], path: Optional[List[Union[str, int]]] = None) -> List[ExternalRef]:
        """Recursively scan configuration for external references."""
        refs = []
        path = path or []
        
        if isinstance(config, dict):
            for key, value in config.items():
                current_path = path + [key]
                refs.extend(self._scan_value(value, current_path))
        elif isinstance(config, list):
            for i, item in enumerate(config):
                current_path = path + [i]
                refs.extend(self._scan_value(item, current_path))
        
        return refs
    
    def _scan_value(self, value: Any, path: List[Union[str, int]]) -> List[ExternalRef]:
        """Scan a single value for external references."""
        refs = []
        
        if isinstance(value, str):
            # Check for external references
            if value.startswith("vault://"):
                refs.append(ExternalRef(path, value, "vault"))
            elif value.startswith("file://"):
                refs.append(ExternalRef(path, value, "file"))
            elif ENV_VAR_PATTERN.search(value):
                refs.append(ExternalRef(path, value, "env"))
        elif isinstance(value, dict):
            refs.extend(self.scan_config(value, path))
        elif isinstance(value, list):
            for i, item in enumerate(value):
                refs.extend(self._scan_value(item, path + [i]))
        
        return refs
    
    def set_template(self, site_config: Dict[str, Any], user_config: Dict[str, Any]):
        """Set the template configuration and scan for references."""
        self._template_config = {
            "site": copy.deepcopy(site_config),
            "user": copy.deepcopy(user_config)
        }
        
        # Scan both configs for external references
        self.refs = []
        self.refs.extend(self.scan_config(user_config, ["user"]))
        # Note: We could also scan site_config if it supports external refs in the future
        
        logger.info(f"Found {len(self.refs)} external references in configuration")
        for ref in self.refs:
            logger.debug(f"  {ref.ref_type}: {ref.source} at {'.'.join(map(str, ref.path))}")
    
    def resolve_all(self, vault_config: Optional[Dict[str, Any]] = None) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """Resolve all external references and return updated configs.
        
        Args:
            vault_config: Optional vault configuration. If not provided, will try to extract from template.
            
        Returns:
            Tuple of (site_config, user_config) with resolved values
        """
        if not self._template_config:
            raise RuntimeError("No template configuration set")
        
        # If vault_config not provided, try to get it from the template
        if vault_config is None and 'user' in self._template_config:
            vault_config = self._template_config['user'].get('vault')
        
        # Deep copy the template
        resolved = copy.deepcopy(self._template_config)
        
        # Resolve each reference
        resolution_errors = []
        for ref in self.refs:
            try:
                value = ref.resolve(vault_config)
                ref.last_resolved = value
                ref.last_checked = time.time()
                
                # Apply the resolved value
                self._apply_value(resolved, ref.path, value)
                
            except Exception as e:
                resolution_errors.append(f"{ref.source}: {e}")
        
        if resolution_errors:
            error_msg = "Failed to resolve some external references:\n" + "\n".join(resolution_errors)
            logger.error(error_msg)
            raise ValueError(error_msg)
        
        self._resolved_config = resolved
        return resolved["site"], resolved["user"]
    
    def _apply_value(self, config: Dict[str, Any], path: List[Union[str, int]], value: Any):
        """Apply a resolved value at the specified path in the config."""
        current = config
        
        # Navigate to the parent of the target
        for key in path[:-1]:
            current = current[key]
        
        # Set the value
        current[path[-1]] = value
    
    def check_for_changes(self) -> List[ExternalRef]:
        """Check if any file-based references have changed."""
        changed = []
        
        for ref in self.refs:
            if ref.ref_type == "file" and ref.last_resolved is not None:
                try:
                    # Extract file path from the source
                    match = FILE_URL_PATTERN.match(ref.source)
                    if match:
                        file_path_str = match.group(1)
                        if file_path_str.startswith('/'):
                            file_path = Path(file_path_str)
                        else:
                            file_path = Path.cwd() / file_path_str
                        
                        if file_path.exists():
                            mtime = file_path.stat().st_mtime
                            # Check if file was modified since last check
                            if mtime > ref.last_checked:
                                changed.append(ref)
                                
                except Exception as e:
                    logger.warning(f"Error checking file {ref.source}: {e}")
        
        return changed
    
    def has_changes(self, old_config: Dict[str, Any], new_config: Dict[str, Any]) -> bool:
        """Check if resolved configurations are different."""
        return old_config != new_config 