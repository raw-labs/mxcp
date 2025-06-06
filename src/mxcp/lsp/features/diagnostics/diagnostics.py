"""Main diagnostics functionality for the LSP server."""

import logging
from typing import Dict, List, Tuple, Optional

from lsprotocol import types
from pygls.server import LanguageServer

from mxcp.lsp.utils.duckdb_connector import DuckDBConnector
from mxcp.lsp.utils.yaml_parser import YamlParser
from mxcp.lsp.utils.coordinate_transformer import CoordinateTransformer


logger = logging.getLogger(__name__)


class DiagnosticsService:
    """Main service class for diagnostics functionality."""

    def __init__(self, duck_db_connector: DuckDBConnector):
        """Initialize the diagnostics service."""
        self._duck_db_connector = duck_db_connector
        self._diagnostics: Dict[str, Tuple[int, List[types.Diagnostic]]] = {}
        self._server: LanguageServer = None
        self._additional_handlers: List = []

    def set_server(self, server: LanguageServer) -> None:
        """Set the server instance for publishing diagnostics."""
        self._server = server

    def add_document_handler(self, handler) -> None:
        """Add an additional document event handler (e.g., for semantic tokens)."""
        self._additional_handlers.append(handler)

    def handle_document_open(self, params: types.DidOpenTextDocumentParams) -> None:
        """Handle document open events."""
        document = self._server.workspace.get_text_document(params.text_document.uri)
        self.parse_document(
            params.text_document.uri,
            document.source,
            params.text_document.version
        )
        self.publish_diagnostics(params.text_document.uri)
        
        # Call additional handlers
        for handler in self._additional_handlers:
            try:
                handler.handle_document_open(params)
            except Exception as e:
                logger.error(f"Error in additional document open handler: {e}")

    def handle_document_change(self, params: types.DidChangeTextDocumentParams) -> None:
        """Handle document change events."""
        document = self._server.workspace.get_text_document(params.text_document.uri)
        self.parse_document(
            params.text_document.uri,
            document.source,
            params.text_document.version
        )
        self.publish_diagnostics(params.text_document.uri)
        
        # Call additional handlers
        for handler in self._additional_handlers:
            try:
                handler.handle_document_change(params)
            except Exception as e:
                logger.error(f"Error in additional document change handler: {e}")

    def handle_document_close(self, params: types.DidCloseTextDocumentParams) -> None:
        """Handle document close events by clearing diagnostics."""
        # Clear diagnostics when document is closed
        self._diagnostics.pop(params.text_document.uri, None)
        # Send empty diagnostics to clear them in the client
        if self._server:
            self._server.publish_diagnostics(params.text_document.uri, [])

    def parse_document(self, document_uri: str, document_source: str, document_version: int) -> None:
        """
        Parse a document and generate diagnostics.
        
        Args:
            document_uri: URI of the document
            document_source: Source code of the document
            document_version: Version of the document
        """
        try:
            yaml_parser = YamlParser(document_source)
            
            if not yaml_parser.should_provide_lsp():
                # Clear diagnostics for documents that don't need LSP
                self._diagnostics[document_uri] = (document_version, [])
                return
            
            # Get the SQL code from the YAML
            sql_code = yaml_parser.code
            if not sql_code:
                self._diagnostics[document_uri] = (document_version, [])
                return
            
            # Validate the SQL code
            validation = self._duck_db_connector.validate_sql(sql_code)
            diagnostics = []
            
            if validation.is_error():
                # Convert the error position to document coordinates using the transformer
                adjusted_position = CoordinateTransformer.sql_to_document_position(
                    validation.error_position, 
                    yaml_parser.code_span
                )
                
                # Determine severity based on error type
                severity = self._get_diagnostic_severity(validation.error_type)
                
                diagnostic = types.Diagnostic(
                    message=validation.error_message,
                    severity=severity,
                    range=types.Range(
                        start=adjusted_position,
                        end=types.Position(
                            line=adjusted_position.line,
                            character=adjusted_position.character + 1
                        )
                    ),
                    source="mxcp-lsp"
                )
                diagnostics.append(diagnostic)
            
            self._diagnostics[document_uri] = (document_version, diagnostics)
            
        except Exception as e:
            logger.error(f"Error parsing document {document_uri}: {e}")
            self._diagnostics[document_uri] = (document_version, [])

    def _get_diagnostic_severity(self, error_type: str) -> types.DiagnosticSeverity:
        """
        Determine diagnostic severity based on error type.
        
        Args:
            error_type: Type of SQL validation error
            
        Returns:
            Appropriate diagnostic severity
        """
        if error_type in ["SYNTAX_ERROR", "PARSER_ERROR"]:
            return types.DiagnosticSeverity.Error
        elif error_type in ["SEMANTIC_ERROR"]:
            return types.DiagnosticSeverity.Warning
        else:
            return types.DiagnosticSeverity.Error

    def get_diagnostics(self, document_uri: str) -> Tuple[int, List[types.Diagnostic]]:
        """
        Get diagnostics for a document.
        
        Args:
            document_uri: URI of the document
            
        Returns:
            Tuple of (version, diagnostics)
        """
        return self._diagnostics.get(document_uri, (0, []))

    def publish_diagnostics(self, document_uri: str) -> None:
        """
        Publish diagnostics for a document.
        
        Args:
            document_uri: URI of the document
        """
        if not self._server:
            logger.error("Server not set - cannot publish diagnostics")
            return
            
        version, diagnostics = self.get_diagnostics(document_uri)
        # Use publish_diagnostics with proper parameters matching pygls examples
        self._server.publish_diagnostics(
            uri=document_uri,
            diagnostics=diagnostics,
            version=version
        )


def register_diagnostics(
    server: LanguageServer, 
    duck_db_connector: DuckDBConnector
) -> DiagnosticsService:
    """
    Register diagnostics functionality with the LSP server.
    
    Following the pygls publish diagnostics example pattern.
    
    Args:
        server: The language server instance
        duck_db_connector: DuckDB connector for SQL validation
        
    Returns:
        The diagnostics service instance
    """
    try:
        service = DiagnosticsService(duck_db_connector)
        service.set_server(server)
        
        # Register document lifecycle events for diagnostics
        # This follows the pattern from the pygls publish diagnostics example
        
        @server.feature(types.TEXT_DOCUMENT_DID_OPEN)
        def did_open(ls: LanguageServer, params: types.DidOpenTextDocumentParams):
            """Parse each document when it is opened"""
            service.handle_document_open(params)

        @server.feature(types.TEXT_DOCUMENT_DID_CHANGE)
        def did_change(ls: LanguageServer, params: types.DidChangeTextDocumentParams):
            """Parse each document when it is changed"""
            service.handle_document_change(params)

        @server.feature(types.TEXT_DOCUMENT_DID_CLOSE)
        def did_close(ls: LanguageServer, params: types.DidCloseTextDocumentParams):
            """Clear diagnostics when document is closed"""
            service.handle_document_close(params)
        
        logger.info("Diagnostics functionality registered successfully")
        return service
        
    except Exception as e:
        logger.error(f"Error registering diagnostics functionality: {e}")
        raise 