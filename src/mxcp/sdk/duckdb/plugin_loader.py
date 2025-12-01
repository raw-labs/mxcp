"""
Plugin loader for DuckDB.

This module handles plugin loading for DuckDB sessions.
"""

import importlib
import logging
import os
import sys
from typing import cast

import duckdb
from duckdb import func

from mxcp.plugins import MXCPBasePlugin

from .models import PluginConfigModel, PluginDefinitionModel

logger = logging.getLogger(__name__)


def _load_plugin(module_path: str, config: dict[str, str], plugins_path: str) -> MXCPBasePlugin:
    """Load and instantiate a plugin.

    Args:
        module_path: The Python module path containing the plugin
        config: The resolved configuration for the plugin
        plugins_path: Path to plugins directory
        context: Optional execution context with user context

    Returns:
        An instantiated MXCPBasePlugin

    Raises:
        ImportError: If the module cannot be imported
        AttributeError: If the module does not contain an MXCPBasePlugin class
    """
    try:
        # Add plugins directory to Python path if not already there
        current_dir = os.getcwd()
        plugins_dir = os.path.join(current_dir, plugins_path)
        if os.path.exists(plugins_dir) and plugins_dir not in sys.path:
            sys.path.insert(0, plugins_dir)
            logger.debug(f"Added {plugins_dir} to Python path for plugins")

        module = importlib.import_module(module_path)
        plugin_class = module.MXCPPlugin
        if not issubclass(plugin_class, MXCPBasePlugin):
            raise AttributeError(f"Plugin class in {module_path} must inherit from MXCPBasePlugin")

        # Instantiate plugin with configuration only (simplified interface)
        logger.debug(f"Loading plugin {module_path} with configuration")
        return cast(MXCPBasePlugin, plugin_class(config))

    except ImportError as e:
        raise ImportError(f"Failed to import plugin module {module_path}: {e}") from e
    except AttributeError as e:
        raise AttributeError(f"Module {module_path} must contain an MXCPPlugin class: {e}") from e


def load_plugins(
    plugins_list: list[PluginDefinitionModel],
    plugin_config: PluginConfigModel,
    conn: duckdb.DuckDBPyConnection,
) -> dict[str, MXCPBasePlugin]:
    """Load all plugins specified in the plugin definitions.

    Args:
        plugins_list: List of plugin definitions to load
        plugin_config: Plugin configuration with paths and config
        conn: The DuckDB connection object

    Returns:
        Dictionary mapping plugin names to their instances

    Raises:
        ValueError: If a plugin configuration is not found
    """
    plugins: dict[str, MXCPBasePlugin] = {}

    for plugin_def in plugins_list:
        name = plugin_def.name
        module = plugin_def.module
        config_name = plugin_def.config

        # Get the plugin's configuration from the user config if specified
        if config_name is not None:
            if config_name not in plugin_config.config:
                raise ValueError(f"Plugin configuration '{config_name}' not found in plugin config")
            plugin_config_dict = plugin_config.config[config_name]
        else:
            plugin_config_dict = {}

        # Load and instantiate the plugin
        plugin = _load_plugin(module, plugin_config_dict, plugin_config.plugins_path)
        plugins[name] = plugin

        logger.info(f"Loaded plugin {name} from {module}")

        udfs = plugin.udfs()

        for udf in udfs:
            method_name = udf["name"]
            db_name = f"{method_name}_{name}"
            conn.create_function(
                db_name, udf["method"], udf["args"], udf["return_type"], null_handling=func.SPECIAL
            )
    return plugins
