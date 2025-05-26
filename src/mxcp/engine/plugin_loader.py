from typing import Dict, Any, List
import importlib
import logging
import duckdb
import sys
import os
from mxcp.config.types import SiteConfig, UserConfig
from mxcp.plugins import MXCPBasePlugin

logger = logging.getLogger(__name__)

def _load_plugin(module_path: str, name: str, config: Dict[str, str], conn: duckdb.DuckDBPyConnection) -> MXCPBasePlugin:
    """Load and instantiate a plugin.
    
    Args:
        module_path: The Python module path containing the plugin
        name: The name of the plugin instance
        config: The resolved configuration for the plugin
        conn: The DuckDB connection object
        
    Returns:
        An instantiated MXCPBasePlugin
        
    Raises:
        ImportError: If the module cannot be imported
        AttributeError: If the module does not contain an MXCPBasePlugin class
    """
    try:
        # Add current directory to Python path if not already there
        current_dir = os.getcwd()
        if current_dir not in sys.path:
            sys.path.insert(0, current_dir)
            
        module = importlib.import_module(module_path)
        plugin_class = getattr(module, "MXCPPlugin")
        if not issubclass(plugin_class, MXCPBasePlugin):
            raise AttributeError(f"Plugin class in {module_path} must inherit from MXCPBasePlugin")
        return plugin_class(name, config, conn)
    except ImportError as e:
        raise ImportError(f"Failed to import plugin module {module_path}: {e}")
    except AttributeError as e:
        raise AttributeError(f"Module {module_path} must contain an MXCPPlugin class: {e}")

def load_plugins(site_config: SiteConfig, user_config: UserConfig, project: str, profile: str, conn: duckdb.DuckDBPyConnection) -> Dict[str, MXCPBasePlugin]:
    """Load all plugins specified in the site config.
    
    Args:
        site_config: The site configuration containing plugin definitions
        user_config: The user configuration containing plugin configurations
        project: The current project name
        profile: The current profile name
        conn: The DuckDB connection object
        
    Returns:
        Dictionary mapping plugin names to their instances
        
    Raises:
        ValueError: If a plugin configuration is not found
    """
    plugins: Dict[str, MXCPBasePlugin] = {}
    
    if "plugin" not in site_config:
        return plugins
        
    # Get the profile's plugin configuration
    profile_config = user_config["projects"][project]["profiles"][profile]
    plugin_config = profile_config["plugin"]["config"]
    
    for plugin_def in site_config["plugin"]:
        name = plugin_def["name"]
        module = plugin_def["module"]
        config_name = plugin_def.get("config")
        
        # Get the plugin's configuration from the user config if specified
        if config_name is not None:
            if config_name not in plugin_config:
                raise ValueError(f"Plugin configuration '{config_name}' not found in user config for profile {profile}")
            plugin_config_dict = plugin_config[config_name]
        else:
            plugin_config_dict = {}
        
        # Load and instantiate the plugin
        plugin = _load_plugin(module, name, plugin_config_dict, conn)
        plugins[name] = plugin
        logger.info(f"Loaded plugin {name} from {module}")
        
    return plugins 