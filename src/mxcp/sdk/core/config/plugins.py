"""
Plugin system for extensible configuration resolvers.

This module provides the base classes and registry system for implementing
different types of configuration resolvers (vault, 1password, custom, etc.)
"""

import re
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Type, Union
import logging

logger = logging.getLogger(__name__)


class ResolverPlugin(ABC):
    """
    Abstract base class for configuration resolver plugins.
    
    ResolverPlugin provides the foundation for implementing custom resolvers
    that can handle different types of external references in configuration files.
    The plugin system allows for extensible configuration resolution beyond the
    built-in resolvers.
    
    ## Implementation Requirements
    
    All resolver plugins must implement the following abstract methods:
    
    - `name`: Return a unique identifier for the resolver
    - `url_patterns`: Return regex patterns that this resolver can handle
    - `can_resolve`: Check if this resolver can handle a specific reference
    - `resolve`: Perform the actual resolution of a reference to its value
    
    ## Optional Methods
    
    - `validate_config`: Validate the resolver's configuration (default: returns True)
    - `cleanup`: Clean up any resources like clients or connections (default: no-op)
    
    ## Context Manager Support
    
    ResolverPlugin implements context manager protocol for automatic cleanup:
    
    ```python
    with MyResolver() as resolver:
        value = resolver.resolve("my://reference")
        # Automatic cleanup on exit
    ```
    
    ## Implementation Example
    
    ```python
    import re
    from typing import List
    from mxcp.sdk.core.config import ResolverPlugin
    
    class DatabaseResolver(ResolverPlugin):
        '''Resolver for database connection strings like db://connection_name'''
        
        DB_PATTERN = re.compile(r'db://([a-zA-Z0-9_-]+)')
        
        def __init__(self, config=None):
            super().__init__(config)
            self._db_client = None
        
        @property
        def name(self) -> str:
            return "database"
        
        @property
        def url_patterns(self) -> List[str]:
            return [r'db://[a-zA-Z0-9_-]+']
        
        def can_resolve(self, reference: str) -> bool:
            return reference.startswith('db://') and self.DB_PATTERN.match(reference)
        
        def validate_config(self) -> bool:
            # Check if database configuration is valid
            if not self.config.get('enabled', False):
                return False
            return 'host' in self.config and 'port' in self.config
        
        def resolve(self, reference: str) -> str:
            match = self.DB_PATTERN.match(reference)
            if not match:
                raise ValueError(f"Invalid database reference: {reference}")
            
            connection_name = match.group(1)
            
            # Initialize client if needed
            if not self._db_client:
                self._init_client()
            
            # Resolve connection string from database
            return self._db_client.get_connection_string(connection_name)
        
        def cleanup(self) -> None:
            # Clean up database client
            if self._db_client:
                self._db_client.close()
                self._db_client = None
        
        def _init_client(self):
            # Initialize database client with config
            host = self.config['host']
            port = self.config['port']
            self._db_client = DatabaseClient(host, port)
    ```
    
    ## Configuration Access
    
    Resolvers receive configuration through the `config` attribute:
    
    ```python
    def __init__(self, config=None):
        super().__init__(config)
        # config is available as self.config
        self.enabled = self.config.get('enabled', True)
        self.api_key = self.config.get('api_key')
    ```
    
    ## Error Handling
    
    Resolvers should raise descriptive exceptions when resolution fails:
    
    ```python
    def resolve(self, reference: str) -> str:
        try:
            return self._fetch_value(reference)
        except ConnectionError as e:
            raise ValueError(f"Failed to connect to service: {e}") from e
        except KeyError as e:
            raise ValueError(f"Reference not found: {reference}") from e
    ```
    
    ## Resource Management
    
    For resolvers that create external clients or connections:
    
    1. Initialize clients lazily (on first use)
    2. Store clients as instance variables
    3. Implement `cleanup()` to close connections
    4. Make cleanup idempotent (safe to call multiple times)
    
    ## Thread Safety
    
    Resolver instances may be used concurrently. Implement appropriate
    locking if your resolver maintains mutable state or uses non-thread-safe clients.
    
    ## Registration
    
    Register custom resolvers with the ResolverEngine:
    
    ```python
    engine = ResolverEngine()
    engine.register_resolver(DatabaseResolver(config))
    ```
    
    Or through the global registry:
    
    ```python
    from mxcp.sdk.core.config.plugins import register_resolver
    register_resolver(DatabaseResolver(config))
    ```
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize the resolver plugin with configuration."""
        self.config = config or {}
        self.enabled = self.config.get('enabled', True)
        self._initialized = False
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Return the name of this resolver plugin."""
        pass
    
    @property
    @abstractmethod
    def url_patterns(self) -> List[str]:
        """Return regex patterns that this resolver can handle."""
        pass
    
    @abstractmethod
    def can_resolve(self, reference: str) -> bool:
        """Check if this resolver can handle the given reference."""
        pass
    
    @abstractmethod
    def resolve(self, reference: str) -> str:
        """Resolve the reference to its actual value."""
        pass
    
    def validate_config(self) -> bool:
        """Validate the resolver configuration. Override if needed."""
        return True
    
    def cleanup(self) -> None:
        """
        Clean up any resources (clients, connections, etc.) used by this resolver.
        Override this method if your resolver creates external clients or connections.
        This method should be idempotent - safe to call multiple times.
        """
        pass
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - calls cleanup."""
        self.cleanup()


class ResolverRegistry:
    """Registry for managing resolver plugins."""
    
    def __init__(self):
        self._resolvers: Dict[str, ResolverPlugin] = {}
        self._patterns: List[tuple[re.Pattern, str]] = []
    
    def register(self, resolver: ResolverPlugin) -> None:
        """Register a resolver plugin."""
        if not resolver.enabled:
            logger.debug(f"Resolver {resolver.name} is disabled, skipping registration")
            return
            
        if not resolver.validate_config():
            logger.warning(f"Resolver {resolver.name} has invalid configuration, skipping registration")
            return
        
        self._resolvers[resolver.name] = resolver
        
        # Compile and store patterns
        for pattern in resolver.url_patterns:
            compiled_pattern = re.compile(pattern)
            self._patterns.append((compiled_pattern, resolver.name))
        
        logger.debug(f"Registered resolver: {resolver.name}")
    
    def get_resolver(self, name: str) -> Optional[ResolverPlugin]:
        """Get a resolver by name."""
        return self._resolvers.get(name)
    
    def find_resolver_for_reference(self, reference: str) -> Optional[ResolverPlugin]:
        """Find the appropriate resolver for a reference."""
        # First try pattern matching
        for pattern, resolver_name in self._patterns:
            if pattern.match(reference):
                resolver = self._resolvers.get(resolver_name)
                if resolver and resolver.can_resolve(reference):
                    return resolver
        
        # Fallback to asking each resolver directly
        for resolver in self._resolvers.values():
            if resolver.can_resolve(reference):
                return resolver
        
        return None
    
    def list_resolvers(self) -> List[str]:
        """List all registered resolver names."""
        return list(self._resolvers.keys())
    
    def resolve_reference(self, reference: str) -> str:
        """Resolve a reference using the appropriate resolver."""
        resolver = self.find_resolver_for_reference(reference)
        if not resolver:
            raise ValueError(f"No resolver found for reference: {reference}")
        
        return resolver.resolve(reference)
    
    def cleanup_all(self) -> None:
        """Clean up all registered resolvers."""
        for resolver in self._resolvers.values():
            try:
                resolver.cleanup()
            except Exception as e:
                logger.warning(f"Error cleaning up resolver {resolver.name}: {e}")
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - calls cleanup on all resolvers."""
        self.cleanup_all()


# Global registry instance
_global_registry = ResolverRegistry()


def get_global_registry() -> ResolverRegistry:
    """Get the global resolver registry."""
    return _global_registry


def register_resolver(resolver: ResolverPlugin) -> None:
    """Register a resolver with the global registry."""
    _global_registry.register(resolver)


def resolve_reference(reference: str) -> str:
    """Resolve a reference using the global registry."""
    return _global_registry.resolve_reference(reference) 