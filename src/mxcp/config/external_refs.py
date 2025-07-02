"""
External configuration reference tracking and resolution.

This module provides functionality to track and refresh external configuration
values (vault://, file://, environment variables) without reloading the entire
configuration structure.
"""
import time
import copy
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple, Union
from pathlib import Path

from mxcp.config.references import (
    find_references,
    resolve_value,
    FILE_URL_PATTERN,
)

logger = logging.getLogger(__name__)


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
            value = resolve_value(self.source, vault_config)
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
    
    def set_template(self, site_config: Dict[str, Any], user_config: Dict[str, Any]):
        """Set the template configuration and scan for references."""
        self._template_config = {
            "site": copy.deepcopy(site_config),
            "user": copy.deepcopy(user_config)
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