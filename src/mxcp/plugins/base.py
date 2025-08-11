import inspect
import logging
from typing import get_type_hints, get_origin, get_args, Any, List, Dict, Union, Optional, Annotated, Type, TypeVar, Callable, cast, TYPE_CHECKING
from datetime import date, time, datetime, timedelta
from decimal import Decimal
from functools import wraps
from duckdb import DuckDBPyConnection
from mxcp.config.user_config import UserConfig
from mxcp.config.site_config import SiteConfig

if TYPE_CHECKING:
    from mxcp.sdk.auth.providers import UserContext

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

T = TypeVar('T')

# Global registry for active plugin instances and shutdown hooks
_active_plugins: List['MXCPBasePlugin'] = []
_plugin_shutdown_hooks: List[Callable] = []

def get_active_plugins() -> List['MXCPBasePlugin']:
    """Returns a list of all active plugin instances."""
    return _active_plugins

def register_plugin(plugin: 'MXCPBasePlugin'):
    """Adds a plugin instance to the global registry."""
    logger.debug(f"Registering active plugin: {plugin.__class__.__name__}")
    _active_plugins.append(plugin)

def clear_plugin_registry():
    """Clears all active plugins and shutdown hooks from the registry."""
    logger.debug("Clearing plugin registry.")
    _active_plugins.clear()
    _plugin_shutdown_hooks.clear()

def on_shutdown(func: Callable) -> Callable:
    """
    Decorator to register a function to be called on plugin shutdown.
    
    This is useful for cleaning up resources like database connections or temporary files.
    The decorated function should take no arguments.
    
    Example:
        class MyPlugin(MXCPBasePlugin):
            def __init__(self, config):
                super().__init__(config)
                self.client = httpx.Client()
                
            @on_shutdown
            def close_client(self):
                self.client.close()
    """
    logger.debug(f"Registering plugin shutdown hook: {func.__name__}")
    _plugin_shutdown_hooks.append(func)
    return func

def run_plugin_shutdown_hooks():
    """
    Executes all registered plugin shutdown hooks and calls the shutdown() method on all active plugins.
    
    This function iterates through all registered hooks and instances, calling them
    to ensure a graceful shutdown. It logs errors but continues execution to ensure
    all hooks are attempted.
    """
    logger.info(f"Running {len(_plugin_shutdown_hooks)} plugin shutdown hooks...")
    for hook in reversed(_plugin_shutdown_hooks):
        try:
            hook()
        except Exception as e:
            logger.error(f"Error executing plugin shutdown hook {hook.__name__}: {e}", exc_info=True)
            
    logger.info(f"Calling shutdown() on {len(_active_plugins)} active plugins...")
    for plugin in reversed(_active_plugins):
        try:
            plugin.shutdown()
        except Exception as e:
            logger.error(f"Error calling shutdown() on plugin {plugin.__class__.__name__}: {e}", exc_info=True)
            
    # Clear the registry after running all shutdown logic
    clear_plugin_registry()
    logger.info("Plugin shutdown process complete.")

def udf(func: Callable[..., T]) -> Callable[..., T]:
    """Decorator to mark a method as a UDF (User Defined Function).
    
    This decorator marks a method to be exposed as a UDF in DuckDB.
    Methods without this decorator will not be exposed as UDFs.
    
    The decorated function must have type hints for all parameters and return value.
    
    Example:
        @udf
        def my_function(x: int) -> int:
            return x * 2
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        return func(*args, **kwargs)
    wrapper._is_udf = True
    wrapper.__doc__ = func.__doc__ or f"UDF: {func.__name__}"
    return wrapper

class MXCPBasePlugin:
    """Base class for MXCP plugins that provides UDF generation from type annotations.
    
    This class serves as the foundation for all MXCP plugins, providing functionality
    to automatically generate DuckDB UDFs (User Defined Functions) from Python methods
    with type annotations.
    
    Example:
        class MyPlugin(MXCPBasePlugin):
            def __init__(self, config: Dict[str, Any]):
                super().__init__(config)
                
            @udf
            def add_numbers(self, a: int, b: int) -> int:
                return a + b
    """
    
    def __init__(self, config: Dict[str, Any], user_context: Optional['UserContext'] = None):
        """Initialize the plugin with configuration and optional user context.
        
        Args:
            config: Plugin configuration dictionary
            user_context: Optional authenticated user context containing user info and tokens
        """
        self._config = config
        self._user_context = user_context
        # Register the instance as active
        register_plugin(self)

    @property
    def user_context(self) -> Optional['UserContext']:
        """Get the authenticated user context.
        
        Returns:
            UserContext if user is authenticated, None otherwise
        """
        return self._user_context

    def get_user_token(self) -> Optional[str]:
        """Get the user's external OAuth token (e.g., GitHub token).
        
        Returns:
            External OAuth token if user is authenticated, None otherwise
        """
        return self._user_context.external_token if self._user_context else None

    def get_username(self) -> Optional[str]:
        """Get the authenticated user's username.
        
        Returns:
            Username if user is authenticated, None otherwise
        """
        return self._user_context.username if self._user_context else None

    def get_user_email(self) -> Optional[str]:
        """Get the authenticated user's email.
        
        Returns:
            Email if user is authenticated and email is available, None otherwise
        """
        return self._user_context.email if self._user_context else None

    def get_user_provider(self) -> Optional[str]:
        """Get the OAuth provider name (e.g., 'github', 'atlassian').
        
        Returns:
            Provider name if user is authenticated, None otherwise
        """
        return self._user_context.provider if self._user_context else None
        
    def is_authenticated(self) -> bool:
        """Check if a user is currently authenticated.
        
        Returns:
            True if user is authenticated, False otherwise
        """
        return self._user_context is not None

    def _get_duckdb_type(self, python_type) -> str:
        """Map a Python type to a DuckDB type string.
        
        Supports:
            • primitives: int, float, bool, str
            • datetime: date, time, datetime, timedelta
            • containers: list[T], dict[K,V]
            • Optional[T]
            • user-defined STRUCTs (dataclasses / classes with __annotations__)
        """
        # Handle Any type - not supported
        if python_type is Any:
            raise ValueError("Type 'Any' is not supported in UDF type annotations. Please specify a concrete type.")
            
        # Handle Annotated and Optional
        origin = get_origin(python_type)
        if origin is Annotated:
            python_type = get_args(python_type)[0]
            origin = get_origin(python_type)
            
        # Handle Optional/Union
        if origin is Union:
            non_none = [t for t in get_args(python_type) if t is not type(None)]
            if len(non_none) == 1:
                return self._get_duckdb_type(non_none[0])
                
        # Handle containers
        if origin is list:
            inner_type, = get_args(python_type)
            return f"{self._get_duckdb_type(inner_type)}[]"
            
        if origin is dict:
            key_type, value_type = get_args(python_type)
            return f"MAP({self._get_duckdb_type(key_type)}, {self._get_duckdb_type(value_type)})"
            
        # Handle basic types
        type_map = {
            str: "VARCHAR",
            int: "INTEGER",
            float: "DOUBLE",
            bool: "BOOLEAN",
            Decimal: "DECIMAL",
            date: "DATE",
            time: "TIME",
            datetime: "TIMESTAMP",
            timedelta: "INTERVAL",
            bytes: "BLOB"
        }
        
        if python_type in type_map:
            return type_map[python_type]
            
        # Handle STRUCTs
        if hasattr(python_type, "__annotations__"):
            fields = []
            for name, field_type in python_type.__annotations__.items():
                duck_type = self._get_duckdb_type(field_type)
                fields.append(f"{name} {duck_type}")
            return f"STRUCT({', '.join(fields)})"
            
        # Unknown types are not supported
        raise ValueError(f"Type '{python_type}' is not supported in UDF type annotations")

    def udfs(self):
        """Generate UDF definitions from type annotations.
        
        Only methods decorated with @udf will be included.
        
        Returns:
            List of UDF definitions with name, method, argument types, and return type.
        """
        udfs = []
        logger.info(f"Processing methods for {self.__class__.__name__}")
        
        for name, class_method in inspect.getmembers(self.__class__, predicate=inspect.isfunction):
            if not getattr(class_method, '_is_udf', False):
                continue
                
            type_hints = get_type_hints(class_method)
            if not type_hints:
                logger.warning(f"Skipping {name}: no type hints found")
                continue
                
            return_type = type_hints.get('return', Any)
            if return_type == Any:
                logger.warning(f"Skipping {name}: no return type annotation")
                continue
                
            # Get argument types (excluding 'self')
            sig = inspect.signature(class_method)
            arg_types = []
            for param_name, param in sig.parameters.items():
                if param_name == 'self':
                    continue
                param_type = type_hints.get(param_name, Any)
                arg_types.append(self._get_duckdb_type(param_type))
            
            # Get the bound method from the instance
            bound_method = getattr(self, name)
            
            udf_def = {
                'name': name,
                'method': bound_method,
                'args': arg_types,
                'return_type': self._get_duckdb_type(return_type)
            }
            logger.info(f"Adding UDF: {name} with args {arg_types} and return type {udf_def['return_type']}")
            udfs.append(udf_def)
            
        logger.info(f"Total UDFs registered: {len(udfs)}")
        return udfs

    @classmethod
    def find_plugins(cls, module: str) -> List[Type['MXCPBasePlugin']]:
        """Find all subclasses of MXCPBasePlugin in a module.
        
        Args:
            module: Module name to search in
            
        Returns:
            List of plugin classes
        """
        import importlib
        import inspect
        
        mod = importlib.import_module(module)
        return [
            obj for name, obj in inspect.getmembers(mod)
            if inspect.isclass(obj) and issubclass(obj, cls) and obj != cls
        ]

    def shutdown(self):
        """
        Clean up plugin resources. Overwrite this method in your plugin
        for custom shutdown logic. This is called automatically during a reload or
        server shutdown.
        
        Example:
            def shutdown(self):
                print(f"Shutting down {self.__class__.__name__}")
                if hasattr(self, 'client'):
                    self.client.close()
        """
        pass
