"""Types specific to DuckDB executor plugin.

This module contains data structures that are only relevant to the DuckDB executor,
keeping them separate from the core executor interfaces.
"""

from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field


@dataclass
class ExtensionDefinition:
    """Definition of a DuckDB extension to load.
    
    Attributes:
        name: Extension name
        repo: Optional repository name (e.g., 'community', 'core_nightly')
    """
    name: str
    repo: Optional[str] = None


@dataclass
class PluginDefinition:
    """Definition of a plugin to load.
    
    Attributes:
        name: Plugin name
        module: Python module path
        config: Optional config key name
    """
    name: str
    module: str
    config: Optional[str] = None


@dataclass
class PluginConfig:
    """Configuration for plugins.
    
    Attributes:
        plugins_path: Path to plugins directory
        config: Dictionary of plugin configurations
    """
    plugins_path: str
    config: Dict[str, Dict[str, str]]


@dataclass
class SecretDefinition:
    """Definition of a secret for injection.
    
    Attributes:
        name: Secret name
        type: Secret type (e.g., 'S3', 'HTTP')
        parameters: Secret parameters
    """
    name: str
    type: str
    parameters: Dict[str, Any]


@dataclass
class DatabaseConfig:
    """Configuration for DuckDB database.
    
    Attributes:
        path: Database file path
        readonly: Whether database is readonly
        extensions: List of extensions to load
    """
    path: str
    readonly: bool = False
    extensions: List[ExtensionDefinition] = field(default_factory=list) 