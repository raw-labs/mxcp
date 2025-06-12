"""Document event handlers for semantic tokens."""

import logging
from typing import Optional

from lsprotocol import types
from pygls.server import LanguageServer

from .semantic_tokens_classifier import SemanticTokensParser
from mxcp.lsp.utils.yaml_parser import YamlParser


logger = logging.getLogger(__name__)


class DocumentEventHandler:
    """Handles document open and change events for semantic token parsing."""

    def __init__(self, server: LanguageServer, parser: SemanticTokensParser):
        """Initialize with server and parser instances."""
        self._server = server
        self._parser = parser

    def handle_document_open(self, params: types.DidOpenTextDocumentParams) -> None:
        """
        Handle document open event.
        
        Args:
            params: Document open parameters
        """
        try:
            document_uri = params.text_document.uri
            document = self._server.workspace.get_text_document(document_uri)
            
            self._parse_document_if_needed(document.source, document_uri)
            
        except Exception as e:
            logger.error(f"Error handling document open for {params.text_document.uri}: {e}")

    def handle_document_change(self, params: types.DidChangeTextDocumentParams) -> None:
        """
        Handle document change event.
        
        Args:
            params: Document change parameters
        """
        try:
            document_uri = params.text_document.uri
            document = self._server.workspace.get_text_document(document_uri)
            
            self._parse_document_if_needed(document.source, document_uri)
            
        except Exception as e:
            logger.error(f"Error handling document change for {params.text_document.uri}: {e}")

    def _parse_document_if_needed(self, source: str, document_uri: str) -> None:
        """Parse document if it should provide LSP functionality."""
        try:
            yaml_parser = YamlParser(source)
            if yaml_parser.should_provide_lsp():
                self._parser.parse(yaml_parser.code, document_uri)
                logger.debug(f"Parsed document: {document_uri}")
                
        except Exception as e:
            logger.warning(f"Error parsing document {document_uri}: {e}")

    def _get_yaml_parser(self, source: str) -> Optional[YamlParser]:
        """Get YAML parser for source, handling errors gracefully."""
        try:
            return YamlParser(source)
        except Exception as e:
            logger.warning(f"Error creating YAML parser: {e}")
            return None 