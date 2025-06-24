"""
MXCP Runtime module for Python endpoints.

This module provides access to runtime services for Python endpoints.
"""
from typing import Optional, Dict, Any, List, Callable, TYPE_CHECKING
import threading
from contextvars import ContextVar
import logging

if TYPE_CHECKING:
    from mxcp.engine.duckdb_session import DuckDBSession
    from mxcp.config.user_config import UserConfig
    from mxcp.config.site_config import SiteConfig
    from mxcp.plugins import MXCPBasePlugin

logger = logging.getLogger(__name__)

# Context variables for thread-safe access
_session_context: ContextVar[Optional['DuckDBSession']] = ContextVar('session', default=None)
_user_config_context: ContextVar[Optional['UserConfig']] = ContextVar('user_config', default=None)
_site_config_context: ContextVar[Optional['SiteConfig']] = ContextVar('site_config', default=None)
_plugins_context: ContextVar[Optional[Dict[str, 'MXCPBasePlugin']]] = ContextVar('plugins', default=None)
_lock_context: ContextVar[Optional[threading.Lock]] = ContextVar('lock', default=None)


class DatabaseProxy:
    """Proxy for database operations with automatic locking"""
    
    def execute(self, query: str, params: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """Execute a SQL query and return results as list of dicts"""
        session = _session_context.get()
        if not session:
            raise RuntimeError("No database session available in runtime context")
            
        lock = _lock_context.get()
        if lock:
            with lock:
                return session.execute_query_to_dict(query, params)
        else:
            return session.execute_query_to_dict(query, params)
    
    @property
    def connection(self):
        """Get the raw DuckDB connection (use with caution in server mode)"""
        session = _session_context.get()
        if not session:
            raise RuntimeError("No database session available in runtime context")
        return session.conn


class ConfigProxy:
    """Proxy for configuration access"""
    
    def get_secret(self, key: str) -> Optional[Dict[str, Any]]:
        """Get a secret's parameters from the user configuration.
        
        Returns the entire parameters dict which can contain:
        - Simple string values: {"key": "value"}
        - Nested maps: {"EXTRA_HTTP_HEADERS": {"Header": "Value"}}
        - Any combination of the above
        """
        user_config = _user_config_context.get()
        if not user_config:
            return None
            
        # Get current project and profile from site config
        site_config = _site_config_context.get()
        if not site_config:
            return None
            
        project = site_config.get("project")
        profile = site_config.get("profile")
        
        try:
            project_config = user_config["projects"][project]
            profile_config = project_config["profiles"][profile]
            secrets = profile_config.get("secrets", [])
            
            # Secrets is now an array of secret objects
            for secret in secrets:
                if secret.get("name") == key:
                    # Return the entire parameters dict for any secret type
                    return secret.get("parameters", {})
                    
            return None
        except (KeyError, TypeError):
            return None
    
    def get_setting(self, key: str, default: Any = None) -> Any:
        """Get a configuration setting from site config"""
        site_config = _site_config_context.get()
        if not site_config:
            return default
        return site_config.get(key, default)
    
    @property
    def user_config(self) -> Optional['UserConfig']:
        """Get the full user configuration"""
        return _user_config_context.get()
    
    @property
    def site_config(self) -> Optional['SiteConfig']:
        """Get the full site configuration"""
        return _site_config_context.get()


class PluginsProxy:
    """Proxy for plugin access"""
    
    def get(self, name: str) -> Optional['MXCPBasePlugin']:
        """Get a plugin by name"""
        plugins = _plugins_context.get()
        if not plugins:
            return None
        return plugins.get(name)
    
    def list(self) -> List[str]:
        """List available plugin names"""
        plugins = _plugins_context.get()
        return list(plugins.keys()) if plugins else []


# Create singleton proxies
db = DatabaseProxy()
config = ConfigProxy()
plugins = PluginsProxy()

# Lifecycle hooks
_init_hooks: List[Callable] = []
_shutdown_hooks: List[Callable] = []


def on_init(func: Callable) -> Callable:
    """
    Register a function to be called on initialization.
    
    Example:
        @on_init
        def setup():
            print("Initializing my module")
    """
    _init_hooks.append(func)
    return func


def on_shutdown(func: Callable) -> Callable:
    """
    Register a function to be called on shutdown.
    
    Example:
        @on_shutdown
        def cleanup():
            print("Cleaning up resources")
    """
    _shutdown_hooks.append(func)
    return func


# Internal functions for setting context
def _set_runtime_context(
    session: 'DuckDBSession',
    user_config: 'UserConfig', 
    site_config: 'SiteConfig',
    plugins: Dict[str, 'MXCPBasePlugin'],
    db_lock: Optional[threading.Lock] = None
):
    """Set the runtime context (called internally by MXCP)"""
    _session_context.set(session)
    _user_config_context.set(user_config)
    _site_config_context.set(site_config)
    _plugins_context.set(plugins)
    _lock_context.set(db_lock)


def _clear_runtime_context():
    """Clear the runtime context (called internally by MXCP)"""
    _session_context.set(None)
    _user_config_context.set(None)
    _site_config_context.set(None)
    _plugins_context.set(None)
    _lock_context.set(None)


def _run_init_hooks():
    """Run initialization hooks"""
    for hook in _init_hooks:
        try:
            logger.info(f"Running init hook: {hook.__name__}")
            hook()
        except Exception as e:
            logger.error(f"Error in init hook {hook.__name__}: {e}")


def _run_shutdown_hooks():
    """Run shutdown hooks"""
    for hook in _shutdown_hooks:
        try:
            logger.info(f"Running shutdown hook: {hook.__name__}")
            hook()
        except Exception as e:
            logger.error(f"Error in shutdown hook {hook.__name__}: {e}") 