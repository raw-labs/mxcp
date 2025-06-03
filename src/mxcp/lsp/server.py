import logging
from typing import Optional
from mxcp.config.types import SiteConfig, UserConfig
from mxcp.engine.duckdb_session import DuckDBSession

from pygls.server import LanguageServer
from lsprotocol.types import (
    InitializeParams,
    InitializedParams,
    ServerCapabilities,
    TextDocumentSyncOptions,
    TextDocumentSyncKind,
)

from .features.completion import register_completion
from .features.semantic_tokens import register_semantic_tokens
from .features.diagnostics import register_diagnostics
from .utils.duckdb_connector import DuckDBConnector
from .utils.document_event_coordinator import DocumentEventCoordinator

logger = logging.getLogger(__name__)


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
        
        # Create the language server instance
        self.ls = LanguageServer('mxcp-lsp', 'v0.1.0')
        
        # Document event coordinator
        self.document_coordinator = DocumentEventCoordinator()
        
        # Register LSP handlers
        self._register_handlers()
        
        logger.info(f"Initializing MXCP LSP Server on port {self.port}")
        if profile:
            logger.info(f"Using profile: {profile}")
        if readonly:
            logger.info("Running in read-only mode")
    
    def _initialize_duckdb_session(self):
        """Initialize the DuckDB session with configs"""
        try:
            self.session = DuckDBSession(
                user_config=self.user_config,
                site_config=self.site_config,
                profile=self.profile,
                readonly=self.readonly
            )
            
            # Create DuckDB connector that uses the MXCP session
            self.duck_db_connector = DuckDBConnector(session=self.session)
            
            logger.info("DuckDB session initialized successfully")
            return self.session.connect()
        except Exception as e:
            logger.error(f"Failed to initialize DuckDB session: {e}")
            # Create fallback connector without session
            self.duck_db_connector = DuckDBConnector()
            logger.warning("Using fallback DuckDB connector")
            raise
    
    def _register_handlers(self):
        """Register LSP protocol handlers"""
        
        @self.ls.feature("initialize")
        def initialize(params: InitializeParams):
            """Handle LSP initialize request"""
            logger.info("LSP: Handling initialize request")
            
            # Initialize DuckDB session when client initializes
            self._initialize_duckdb_session()
            
            # Register features with the new logic
            self._register_features()
            
            return {
                "capabilities": ServerCapabilities(
                    # Text document sync - essential for document events
                    text_document_sync=TextDocumentSyncOptions(
                        open_close=True,
                        change=TextDocumentSyncKind.Full,
                    ),
                    # Note: Other capabilities are declared by the individual features
                    # when they register with @server.feature()
                ),
                "serverInfo": {"name": "MXCP LSP Server", "version": "0.1.0"},
            }

        @self.ls.feature("initialized")
        def initialized(params: InitializedParams):
            """Handle the initialized notification."""
            logger.info("LSP: Server initialized successfully")

        @self.ls.feature("shutdown")
        def shutdown(params=None):
            """Handle LSP shutdown request"""
            logger.info("LSP: Handling shutdown request")
            if self.session:
                self.session.close()
                logger.info("DuckDB session closed")
            return None

        @self.ls.feature("exit")
        def exit_handler(params=None):
            """Handle exit notification."""
            logger.info("LSP: Server exiting")
    
    def _register_features(self):
        """Register LSP features with the server using the new feature definition logic"""
        if not self.duck_db_connector:
            logger.error("Cannot register features: DuckDB connector not initialized")
            return
        
        try:
            logger.info("LSP: Registering features...")
            
            # Register completion feature
            register_completion(self.ls, self.duck_db_connector)
            logger.info("LSP: Completion feature registered")
            
            # Register semantic tokens feature
            semantic_tokens_service, semantic_tokens_handler = register_semantic_tokens(
                self.ls, self.duck_db_connector
            )
            self.document_coordinator.register_handler(semantic_tokens_handler)
            logger.info("LSP: Semantic tokens feature registered")
            
            # Register diagnostics feature
            diagnostics_service = register_diagnostics(self.ls, self.duck_db_connector)
            self.document_coordinator.register_handler(diagnostics_service)
            logger.info("LSP: Diagnostics feature registered")
            
            # Register document events with the server (only once)
            self.document_coordinator.register_with_server(self.ls)
            logger.info("LSP: Document event coordinator registered")
                
        except Exception as e:
            logger.error(f"Error registering LSP features: {e}")
            raise
    
    def start(self):
        """Start the LSP server"""
        logger.info("Starting MXCP LSP Server...")
        
        try:
            # Start the language server on stdio
            # Use the synchronous version to avoid event loop conflicts
            self.ls.start_io()
        except KeyboardInterrupt:
            logger.info("Received shutdown signal")
        finally:
            self.shutdown()
    
    def shutdown(self):
        """Shutdown the LSP server and cleanup resources"""
        logger.info("Shutting down MXCP LSP Server...")
        
        if self.duck_db_connector:
            self.duck_db_connector.close()
        
        if self.session:
            self.session.close()
            logger.info("DuckDB session closed") 