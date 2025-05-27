from typing import Dict, Any
import logging
import duckdb

logger = logging.getLogger(__name__)

class MXCPBasePlugin:
    """Base class for MXCP plugins.
    
    Plugins must inherit from this class and be named MXCPBasePlugin in their module.
    The plugin will be instantiated with its name, configuration, and DuckDB connection.
    """
    
    def __init__(self, name: str, config: Dict[str, str], conn: duckdb.DuckDBPyConnection):
        """Initialize the plugin.
        
        Args:
            name: The name of the plugin instance from mxcp-site.yml
            config: The resolved configuration from ~/.mxcp/config.yml
            conn: The DuckDB connection object
        """
        self.name = name
        self.config = config
        self.conn = conn
        logger.debug(f"Initialized plugin {name} with config: {config}")
        
    def __str__(self) -> str:
        return f"MXCPBasePlugin(name={self.name})" 