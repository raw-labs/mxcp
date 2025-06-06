import logging
from typing import Optional
from mxcp.config.types import SiteConfig, UserConfig
from mxcp.engine.duckdb_session import DuckDBSession

from pygls.server import LanguageServer
from pygls.protocol import LanguageServerProtocol
from lsprotocol.types import (
    InitializedParams,
    ServerCapabilities,
    TEXT_DOCUMENT_SEMANTIC_TOKENS_FULL,
)

from .features.completion import register_completion
from .features.semantic_tokens import register_semantic_tokens
from .features.diagnostics import register_diagnostics
from .utils.duckdb_connector import DuckDBConnector
from .utils.document_event_coordinator import DocumentEventCoordinator

logger = logging.getLogger(__name__)


class ServerInitializationState:
    """Tracks the initialization state of the LSP server components."""
    
    def __init__(self):
        self.duckdb_session_ready = False
        self.duckdb_connector_ready = False
        self.features_registered = False
        self.initialization_errors = []
    
    def add_error(self, component: str, error: Exception):
        """Add an initialization error for tracking."""
        self.initialization_errors.append((component, str(error)))
        logger.error(f"Initialization error in {component}: {error}")
    
    def is_ready_for_features(self) -> bool:
        """Check if all prerequisites for feature registration are met."""
        return self.duckdb_session_ready and self.duckdb_connector_ready
    
    def get_error_summary(self) -> str:
        """Get a summary of initialization errors."""
        if not self.initialization_errors:
            return "No initialization errors"
        
        return f"Initialization errors: {'; '.join([f'{comp}: {err}' for comp, err in self.initialization_errors])}"


class PatchedLanguageServerProtocol(LanguageServerProtocol):
    """A patched version of the language server protocol to handle semantic tokens capabilities."""
    
    def __init__(self, *args, **kwargs):
        self._server_capabilities = ServerCapabilities()
        super().__init__(*args, **kwargs)
    
    @property
    def server_capabilities(self):
        return self._server_capabilities
    
    @server_capabilities.setter
    def server_capabilities(self, value: ServerCapabilities):
        # Check if semantic tokens full feature is registered and set the capability
        if TEXT_DOCUMENT_SEMANTIC_TOKENS_FULL in self.fm.features:
            opts = self.fm.feature_options.get(TEXT_DOCUMENT_SEMANTIC_TOKENS_FULL, None)
            if opts:
                value.semantic_tokens_provider = opts
        self._server_capabilities = value


class MXCPLSPServer:
    """
    LSP Server implementation for MXCP that provides language server features.
    
    This server provides SQL language support for MXCP YAML files, including:
    - Code completion for SQL queries
    - Diagnostics for syntax validation  
    - Semantic tokens for syntax highlighting
    
    The server manages DuckDB connections and coordinates document events
    across multiple LSP features.
    """
    
    def __init__(self, user_config: UserConfig, site_config: SiteConfig, profile: Optional[str] = None, 
                 readonly: Optional[bool] = None, port: Optional[int] = None):
        """
        Initialize the MXCP LSP Server.
        
        Args:
            user_config: User configuration loaded from mxcp-config.yml
            site_config: Site configuration loaded from mxcp-site.yml  
            profile: Optional profile name to override the default profile
            readonly: Whether to open DuckDB connection in read-only mode
            port: Port number for LSP server (if applicable)
        """
        # Configuration
        self.user_config = user_config
        self.site_config = site_config
        self.profile = profile
        self.readonly = readonly
        self.port = port or 3000
        
        # Core components
        self.session: Optional[DuckDBSession] = None
        self.duck_db_connector: Optional[DuckDBConnector] = None
        self.ls = LanguageServer('mxcp-lsp', 'v0.1.0', protocol_cls=PatchedLanguageServerProtocol)
        self.document_coordinator = DocumentEventCoordinator()
        
        # Initialization state tracking
        self.init_state = ServerInitializationState()
        
        # Setup server components
        self._setup_server()
        
        logger.info(f"MXCP LSP Server initialized on port {self.port}")
        if profile:
            logger.info(f"Using profile: {profile}")
        if readonly:
            logger.info("Running in read-only mode")
        logger.info(self.init_state.get_error_summary())

    def _setup_server(self):
        """
        Set up the server components in the correct order.
        
        This method orchestrates the initialization process with proper
        error handling and state tracking.
        """
        # Step 1: Register LSP protocol handlers (always succeeds)
        self._register_handlers()
        
        # Step 2: Initialize database components
        self._initialize_database_components()
        
        # Step 3: Register features if database is ready
        if self.init_state.is_ready_for_features():
            self._initialize_features()
        else:
            logger.warning("Database components not ready - features will be registered later")

    def _initialize_database_components(self):
        """Initialize DuckDB session and connector with proper error handling."""
        try:
            self._setup_duckdb_session()
            self.init_state.duckdb_session_ready = True
        except Exception as e:
            self.init_state.add_error("DuckDB Session", e)
            return
        
        try:
            self._setup_duckdb_connector()
            self.init_state.duckdb_connector_ready = True
        except Exception as e:
            self.init_state.add_error("DuckDB Connector", e)

    def _setup_duckdb_session(self):
        """Create DuckDB session with the provided configurations."""
        self.session = DuckDBSession(
            user_config=self.user_config,
            site_config=self.site_config,
            profile=self.profile,
            readonly=self.readonly
        )
        self.session.connect()
        logger.info("DuckDB session created successfully")

    def _setup_duckdb_connector(self):
        """Create DuckDB connector - requires valid session."""
        if not self.session:
            raise RuntimeError("Cannot create DuckDB connector: no session available")
        
        self.duck_db_connector = DuckDBConnector(session=self.session)
        logger.info("DuckDB connector initialized successfully")

    def _initialize_features(self):
        """Initialize and register LSP features."""
        if not self.duck_db_connector:
            raise RuntimeError("Cannot register features: DuckDB connector not initialized")
        
        try:
            self._register_features()
            self.init_state.features_registered = True
            logger.info("LSP features initialized successfully")
        except Exception as e:
            self.init_state.add_error("Feature Registration", e)

    def _register_handlers(self):
        """Register LSP protocol handlers."""
        
        @self.ls.feature("initialized")
        def initialized(params: InitializedParams):
            """Handle the initialized notification."""
            logger.info("LSP: Server initialized successfully")
            
            # Attempt late initialization if features weren't registered during setup
            if not self.init_state.features_registered and not self.init_state.is_ready_for_features():
                logger.info("Attempting late feature initialization...")
                self._initialize_database_components()
                if self.init_state.is_ready_for_features():
                    self._initialize_features()

        @self.ls.feature("shutdown")
        def shutdown(params=None):
            """Handle LSP shutdown request."""
            logger.info("LSP: Handling shutdown request")
            self._cleanup_resources()
            return None

        @self.ls.feature("exit")
        def exit_handler(params=None):
            """Handle exit notification."""
            logger.info("LSP: Server exiting")

    def _register_features(self):
        """
        Register LSP features with the server.
        
        Features are registered in a specific order to handle dependencies:
        1. Completion - Independent feature
        2. Diagnostics - Establishes document event handling
        3. Semantic tokens - Depends on diagnostics for document events
        
        Raises:
            RuntimeError: If no features could be registered
        """
        if not self.duck_db_connector:
            raise RuntimeError("Cannot register features: DuckDB connector not initialized")
        
        logger.info("LSP: Registering features...")
        
        # Track registration results
        feature_results = {
            'completion': False,
            'diagnostics': False, 
            'semantic_tokens': False
        }
        diagnostics_service = None
        
        # Register completion feature (independent)
        try:
            register_completion(self.ls, self.duck_db_connector)
            feature_results['completion'] = True
            logger.info("LSP: Completion feature registered")
        except Exception as e:
            self.init_state.add_error("Completion Feature", e)
        
        # Register diagnostics feature (establishes document events)
        try:
            diagnostics_service = register_diagnostics(self.ls, self.duck_db_connector)
            feature_results['diagnostics'] = True
            logger.info("LSP: Diagnostics feature registered")
        except Exception as e:
            self.init_state.add_error("Diagnostics Feature", e)
        
        # Register semantic tokens feature (depends on diagnostics)
        try:
            semantic_tokens_service, semantic_tokens_handler = register_semantic_tokens(
                self.ls, self.duck_db_connector
            )
            if diagnostics_service:
                diagnostics_service.add_document_handler(semantic_tokens_handler)
            feature_results['semantic_tokens'] = True
            logger.info("LSP: Semantic tokens feature registered")
        except Exception as e:
            self.init_state.add_error("Semantic Tokens Feature", e)
        
        # Report registration results
        registered_count = sum(feature_results.values())
        total_features = len(feature_results)
        
        logger.info(f"LSP: Feature registration completed - {registered_count}/{total_features} features registered")
        
        if registered_count == 0:
            raise RuntimeError("No LSP features could be registered - server cannot provide language support")
    
    def _cleanup_resources(self):
        """
        Clean up server resources in the correct order.
        
        Resources are cleaned up in reverse order of initialization to
        ensure proper dependency management and avoid resource leaks.
        """
        logger.info("Cleaning up LSP server resources...")
        
        # Clear document handlers first
        try:
            if hasattr(self, 'document_coordinator') and self.document_coordinator:
                self.document_coordinator.clear_handlers()
        except Exception as e:
            logger.error(f"Error clearing document handlers: {e}")
        
        # Close DuckDB connector
        try:
            if self.duck_db_connector:
                self.duck_db_connector.close()
                self.duck_db_connector = None
        except Exception as e:
            logger.error(f"Error closing DuckDB connector: {e}")
        
        # Close DuckDB session
        try:
            if self.session:
                self.session.close()
                self.session = None
                logger.info("DuckDB session closed")
        except Exception as e:
            logger.error(f"Error closing DuckDB session: {e}")
        
        logger.info("LSP server resource cleanup completed")
    
    def start(self, host: str = "localhost", use_tcp: bool = False):
        """Start the LSP server
        
        Args:
            host: Host to bind to when using TCP (default: localhost)
            use_tcp: Whether to use TCP instead of stdio (default: False for backwards compatibility)
        """
        logger.info("Starting MXCP LSP Server...")
        
        try:
            if use_tcp:
                logger.info(f"Starting LSP TCP server on {host}:{self.port}...")
                self.ls.start_tcp(host, self.port)
                logger.info("LSP TCP server finished")
            else:
                # Start the language server on stdio (original behavior)
                logger.info("Starting LSP IO server...")
                self.ls.start_io()
                logger.info("LSP IO server finished")
        except KeyboardInterrupt:
            logger.info("Received shutdown signal")
        except BrokenPipeError:
            logger.info("Broken pipe - client disconnected")
        except EOFError:
            logger.info("EOF - no more input from client")
        except Exception as e:
            logger.error(f"Error in LSP server: {e}")
            import traceback
            logger.error(traceback.format_exc())
        finally:
            self.shutdown()
    
    def shutdown(self):
        """Shutdown the LSP server and cleanup resources"""
        logger.info("Shutting down MXCP LSP Server...")
        self._cleanup_resources() 