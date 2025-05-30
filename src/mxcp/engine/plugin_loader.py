from typing import Dict, Any, List, Optional, TYPE_CHECKING
import importlib
import logging
import duckdb
import sys
import os
from mxcp.config.types import SiteConfig, UserConfig
from mxcp.plugins import MXCPBasePlugin
import inspect

if TYPE_CHECKING:
    from mxcp.auth.providers import UserContext

logger = logging.getLogger(__name__)

def _load_plugin(module_path: str, config: Dict[str, str], user_context: Optional['UserContext'] = None) -> MXCPBasePlugin:
    """Load and instantiate a plugin.
    
    Args:
        module_path: The Python module path containing the plugin
        config: The resolved configuration for the plugin
        user_context: Optional authenticated user context
        
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
        
        # Check if the plugin constructor supports user_context parameter
        constructor_sig = inspect.signature(plugin_class.__init__)
        supports_user_context = 'user_context' in constructor_sig.parameters
        
        if supports_user_context:
            logger.debug(f"Plugin {module_path} supports user context")
            return plugin_class(config, user_context=user_context)
        else:
            logger.debug(f"Plugin {module_path} does not support user context (backward compatibility mode)")
            return plugin_class(config)
            
    except ImportError as e:
        raise ImportError(f"Failed to import plugin module {module_path}: {e}")
    except AttributeError as e:
        raise AttributeError(f"Module {module_path} must contain an MXCPPlugin class: {e}")

def load_plugins(site_config: SiteConfig, user_config: UserConfig, project: str, profile: str, conn: duckdb.DuckDBPyConnection, user_context: Optional['UserContext'] = None) -> Dict[str, MXCPBasePlugin]:
    """Load all plugins specified in the site config.
    
    Args:
        site_config: The site configuration containing plugin definitions
        user_config: The user configuration containing plugin configurations
        project: The current project name
        profile: The current profile name
        conn: The DuckDB connection object
        user_context: Optional authenticated user context
        
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
        
        # Load and instantiate the plugin with user context
        plugin = _load_plugin(module, plugin_config_dict, user_context)
        plugins[name] = plugin
        
        if user_context:
            logger.info(f"Loaded plugin {name} from {module} with user context for {user_context.username}")
        else:
            logger.info(f"Loaded plugin {name} from {module}")
        
        udfs = plugin.udfs()
        
        for udf in udfs:
            method_name = udf['name']
            db_name = f"{method_name}_{name}"
            conn.create_function(db_name, udf['method'], udf['args'], udf['return_type'])
    return plugins 