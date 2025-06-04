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
    
    def _register_handlers(self):
        """Register LSP protocol handlers"""
        
        @self.ls.feature("initialize")
        def initialize(params: InitializeParams):
            """Handle LSP initialize request"""
            logger.info("LSP: Handling initialize request")
            
            # Initialize DuckDB session during startup - fail if this fails
            self._initialize_duckdb_session()
            
            # Register features during startup
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