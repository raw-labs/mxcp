import logging
import asyncio
from typing import Dict, Any, Optional, List
from mxcp.config.types import SiteConfig, UserConfig
from mxcp.engine.duckdb_session import DuckDBSession
import json

from pygls.server import LanguageServer
from pygls.protocol import LanguageServerProtocol
from lsprotocol.types import (
    TEXT_DOCUMENT_COMPLETION,
    TEXT_DOCUMENT_HOVER,
    TEXT_DOCUMENT_DEFINITION,
    CompletionItem,
    CompletionList,
    CompletionParams,
    CompletionItemKind,
    Hover,
    HoverParams,
    DefinitionParams,
    Location,
    Position,
    Range,
    MarkupContent,
    MarkupKind,
    InitializeParams,
    ServerCapabilities,
    CompletionOptions,
    InitializeResultServerInfoType,
)

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
        
        # Create the language server instance
        self.ls = LanguageServer('mxcp-lsp', 'v0.1.0')
        
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
            conn = self.session.connect()
            logger.info("DuckDB session initialized successfully")
            return conn
        except Exception as e:
            logger.error(f"Failed to initialize DuckDB session: {e}")
            raise
    
    def _register_handlers(self):
        """Register LSP protocol handlers"""
        
        @self.ls.feature("initialize")
        def initialize(params: InitializeParams):
            """Handle LSP initialize request"""
            logger.info("LSP: Handling initialize request")
            
            # Initialize DuckDB session when client initializes
            self._initialize_duckdb_session()
            
            return {
                "capabilities": ServerCapabilities(
                    text_document_sync=1,  # Full document sync
                    completion_provider=CompletionOptions(
                        trigger_characters=["."],
                        resolve_provider=True
                    ),
                    hover_provider=True,
                    definition_provider=True,
                ),
                "serverInfo": InitializeResultServerInfoType(
                    name="MXCP LSP Server",
                    version="0.1.0"
                )
            }
        
        @self.ls.feature(TEXT_DOCUMENT_COMPLETION)
        def completion(params: CompletionParams):
            """Handle LSP completion request"""
            logger.info("LSP: Handling completion request")
            
            completion_items = [
                CompletionItem(
                    label="SELECT",
                    kind=CompletionItemKind.Keyword,
                    detail="SQL SELECT statement",
                    documentation="Retrieve data from database tables"
                ),
                CompletionItem(
                    label="FROM",
                    kind=CompletionItemKind.Keyword,
                    detail="SQL FROM clause",
                    documentation="Specify the table to select from"
                ),
                CompletionItem(
                    label="WHERE",
                    kind=CompletionItemKind.Keyword,
                    detail="SQL WHERE clause",
                    documentation="Filter rows based on conditions"
                ),
            ]
            
            # Add table names from DuckDB schema
            if self.session and self.session.conn:
                try:
                    tables_result = self.session.conn.execute(
                        "SELECT table_name FROM information_schema.tables WHERE table_schema = 'main'"
                    ).fetchall()
                    
                    for table in tables_result:
                        completion_items.append(CompletionItem(
                            label=table[0],
                            kind=CompletionItemKind.Module,
                            detail=f"Table: {table[0]}",
                            documentation=f"Database table {table[0]}"
                        ))
                except Exception as e:
                    logger.warning(f"Failed to get table completions: {e}")
            
            return CompletionList(is_incomplete=False, items=completion_items)
        
        @self.ls.feature(TEXT_DOCUMENT_HOVER)
        def hover(params: HoverParams):
            """Handle LSP hover request"""
            logger.info("LSP: Handling hover request")
            
            return Hover(
                contents=MarkupContent(
                    kind=MarkupKind.Markdown,
                    value="**MXCP LSP Server**\n\nProvides SQL completion and schema information from your DuckDB database."
                )
            )
        
        @self.ls.feature(TEXT_DOCUMENT_DEFINITION)
        def definition(params: DefinitionParams):
            """Handle LSP go-to-definition request"""
            logger.info("LSP: Handling definition request")
            # Return empty list for now - could be enhanced to jump to endpoint definitions
            return []
        
        @self.ls.feature("shutdown")
        def shutdown():
            """Handle LSP shutdown request"""
            logger.info("LSP: Handling shutdown request")
            if self.session:
                self.session.close()
                logger.info("DuckDB session closed")
    
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
        
        if self.session:
            self.session.close()
            logger.info("DuckDB session closed") 