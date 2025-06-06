import logging
from typing import Optional
from mxcp.config.types import SiteConfig, UserConfig
from mxcp.engine.duckdb_session import DuckDBSession

from pygls.server import LanguageServer
from pygls.protocol import LanguageServerProtocol
from lsprotocol.types import (
    InitializeParams,
    InitializedParams,
    ServerCapabilities,
    TextDocumentSyncOptions,
    TextDocumentSyncKind,
    CompletionOptions,
    SemanticTokensOptions,
    SemanticTokensLegend,
    TEXT_DOCUMENT_SEMANTIC_TOKENS_FULL,
)

from .features.completion import register_completion
from .features.semantic_tokens import register_semantic_tokens
from .features.diagnostics import register_diagnostics
from .utils.duckdb_connector import DuckDBConnector
from .utils.document_event_coordinator import DocumentEventCoordinator

logger = logging.getLogger(__name__)


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
    """LSP Server implementation for MXCP that provides language server features"""
    
    def __init__(self, user_config: UserConfig, site_config: SiteConfig, profile: Optional[str] = None, 
                 readonly: Optional[bool] = None, port: Optional[int] = None):
        """Initialize the MXCP LSP Server.
        
        Args:
            user_config: User configuration loaded from mxcp-config.yml
            site_config: Site configuration loaded from mxcp-site.yml  
            profile: Optional profile name to override the default profile
            readonly: Whether to open DuckDB connection in read-only mode
            port: Port number for LSP server (if applicable)
        """
        self.user_config = user_config
        self.site_config = site_config
        self.profile = profile
        self.readonly = readonly
        self.port = port or 3000  # Default LSP port
        self.session: Optional[DuckDBSession] = None
        self.duck_db_connector: Optional[DuckDBConnector] = None
        
        # Create the language server instance with patched protocol
        self.ls = LanguageServer('mxcp-lsp', 'v0.1.0', protocol_cls=PatchedLanguageServerProtocol)
        
        # Document event coordinator
        self.document_coordinator = DocumentEventCoordinator()
        
        # Register LSP handlers first
        self._register_handlers()
        
        # Try to initialize DuckDB and register features early
        # This allows features to be available during capability generation
        self._initialize_server_features()
        
        logger.info(f"Initializing MXCP LSP Server on port {self.port}")
        if profile:
            logger.info(f"Using profile: {profile}")
        if readonly:
            logger.info("Running in read-only mode")
    
    def _setup_duckdb_session(self):
        """Create DuckDB session with the provided configurations."""
        self.session = DuckDBSession(
            user_config=self.user_config,
            site_config=self.site_config,
            profile=self.profile,
            readonly=self.readonly
        )
        logger.info("DuckDB session created successfully")
        return self.session.connect()
    
    def _setup_duckdb_connector(self):
        """Create DuckDB connector - requires valid session or fails."""
        if not self.session:
            raise RuntimeError("Cannot create DuckDB connector: no session available")
        
        self.duck_db_connector = DuckDBConnector(session=self.session)
        logger.info("DuckDB connector initialized successfully")
    
    def _initialize_duckdb_session(self):
        """Initialize the DuckDB session and connector."""
        try:
            self._setup_duckdb_session()
            self._setup_duckdb_connector()
            logger.info("DuckDB initialization completed successfully")
        except Exception as e:
            logger.error(f"Failed to initialize DuckDB: {e}")
            raise RuntimeError(f"LSP server cannot start without DuckDB connection: {e}")
    
    def _initialize_server_features(self):
        """Initialize server features early during server setup."""
        try:
            # Try to initialize DuckDB session during server setup
            self._initialize_duckdb_session()
            
            # Register features during server setup so they're available for capability generation
            self._register_features()
            logger.info("LSP: Server features initialized during setup")
            
        except Exception as e:
            logger.warning(f"LSP: Could not initialize features during setup: {e}")
            logger.warning("LSP: Features will be initialized during client initialize request")
    

    
    def _register_handlers(self):
        """Register LSP protocol handlers"""
        
        # Don't override the initialize handler - let pygls handle it automatically
        # Since features are registered during server setup, pygls will generate the correct capabilities

        @self.ls.feature("initialized")
        def initialized(params: InitializedParams):
            """Handle the initialized notification."""
            logger.info("LSP: Server initialized successfully")

        @self.ls.feature("shutdown")
        def shutdown(params=None):
            """Handle LSP shutdown request"""
            logger.info("LSP: Handling shutdown request")
            self._cleanup_resources()
            return None

        @self.ls.feature("exit")
        def exit_handler(params=None):
            """Handle exit notification."""
            logger.info("LSP: Server exiting")
    
    def _register_features(self):
        """Register LSP features with the server using the new feature definition logic"""
        if not self.duck_db_connector:
            raise RuntimeError("Cannot register features: DuckDB connector not initialized")
        
        logger.info("LSP: Registering features...")
        features_registered = 0
        
        # Register completion feature
        try:
            register_completion(self.ls, self.duck_db_connector)
            logger.info("LSP: Completion feature registered")
            features_registered += 1
        except Exception as e:
            logger.error(f"Failed to register completion feature: {e}")
        
        # Register diagnostics feature first (it registers document events)
        # Diagnostics registers its own document event handlers directly following pygls best practices
        diagnostics_service = None
        try:
            diagnostics_service = register_diagnostics(self.ls, self.duck_db_connector)
            logger.info("LSP: Diagnostics feature registered")
            features_registered += 1
        except Exception as e:
            logger.error(f"Failed to register diagnostics feature: {e}")
        
        # Register semantic tokens feature
        try:
            semantic_tokens_service, semantic_tokens_handler = register_semantic_tokens(
                self.ls, self.duck_db_connector
            )
            if diagnostics_service:
                diagnostics_service.add_document_handler(semantic_tokens_handler)
            logger.info("LSP: Semantic tokens feature registered")
            features_registered += 1
        except Exception as e:
            logger.error(f"Failed to register semantic tokens feature: {e}")
        
        expected_features = 3  # completion, diagnostics, semantic_tokens
        logger.info(f"LSP: Features registration completed - {features_registered}/{expected_features} features registered")
        
        if features_registered == 0:
            raise RuntimeError("No LSP features could be registered")
    
    def _cleanup_resources(self):
        """Clean up server resources."""
        if self.duck_db_connector:
            self.duck_db_connector.close()
        
        if self.session:
            self.session.close()
            logger.info("DuckDB session closed")
    
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