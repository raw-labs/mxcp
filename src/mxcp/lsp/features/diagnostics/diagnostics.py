"""Main diagnostics functionality for the LSP server."""

import logging
from typing import Dict, List, Tuple

from lsprotocol import types
from pygls.server import LanguageServer

from mxcp.lsp.utils.duckdb_connector import DuckDBConnector
from mxcp.lsp.utils.yaml_parser import YamlParser


logger = logging.getLogger(__name__)


class DiagnosticsService:
    """Main service class for diagnostics functionality."""

    def __init__(self, duck_db_connector: DuckDBConnector):
        """Initialize the diagnostics service."""
        self._duck_db_connector = duck_db_connector
        self._diagnostics: Dict[str, Tuple[int, List[types.Diagnostic]]] = {}
        self._server: LanguageServer = None

    def set_server(self, server: LanguageServer) -> None:
        """Set the server instance for publishing diagnostics."""
        self._server = server

    def handle_document_open(self, params: types.DidOpenTextDocumentParams) -> None:
        """Handle document open events."""
        document = self._server.workspace.get_text_document(params.text_document.uri)
        self.parse_document(
            params.text_document.uri,
            document.source,
            params.text_document.version
        )
        self.publish_diagnostics(params.text_document.uri)

    def handle_document_change(self, params: types.DidChangeTextDocumentParams) -> None:
        """Handle document change events."""
        document = self._server.workspace.get_text_document(params.text_document.uri)
        self.parse_document(
            params.text_document.uri,
            document.source,
            params.text_document.version
        )
        self.publish_diagnostics(params.text_document.uri)

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
                # Convert the error position to document coordinates
                # The error position is relative to the SQL code, we need to adjust it
                # to be relative to the YAML document
                adjusted_position = self._adjust_position_to_document(
                    validation.error_position, yaml_parser.code_span
                )
                
                # Determine severity based on error type
                severity = types.DiagnosticSeverity.Error
                if validation.error_type in ["SYNTAX_ERROR", "PARSER_ERROR"]:
                    severity = types.DiagnosticSeverity.Error
                elif validation.error_type in ["SEMANTIC_ERROR"]:
                    severity = types.DiagnosticSeverity.Warning
                
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

    def _adjust_position_to_document(
        self, 
        sql_position: types.Position, 
        code_span: Tuple[types.Position, types.Position]
    ) -> types.Position:
        """
        Adjust a position from SQL code coordinates to document coordinates.
        
        Args:
            sql_position: Position within the SQL code
            code_span: Start and end positions of the SQL code in the document
            
        Returns:
            Position adjusted to document coordinates
        """
        # Add the SQL code's start position to the error position
        adjusted_line = code_span[0].line + sql_position.line
        
        # For block scalars (like `code: |`), all lines have the same base indentation
        # The code_span[0].character gives us the indentation level after the YAML structure
        if sql_position.line == 0:
            # First line: add both the YAML indentation and the SQL position
            adjusted_character = code_span[0].character + sql_position.character
        else:
            # Subsequent lines: add the YAML base indentation and the SQL position
            # The base indentation is the same for all lines in a block scalar
            adjusted_character = code_span[0].character + sql_position.character
        
        return types.Position(line=adjusted_line, character=adjusted_character)

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
        self._server.publish_diagnostics(document_uri, diagnostics)


def register_diagnostics(
    server: LanguageServer, 
    duck_db_connector: DuckDBConnector
) -> DiagnosticsService:
    """
    Register diagnostics functionality with the LSP server.
    
    Args:
        server: The language server instance
        duck_db_connector: DuckDB connector for SQL validation
        
    Returns:
        The diagnostics service instance
    """
    try:
        service = DiagnosticsService(duck_db_connector)
        service.set_server(server)
        
        logger.info("Diagnostics functionality registered successfully")
        return service
        
    except Exception as e:
        logger.error(f"Error registering diagnostics functionality: {e}")
        raise 