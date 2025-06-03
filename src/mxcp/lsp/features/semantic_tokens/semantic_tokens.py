"""Main semantic tokens functionality for the LSP server."""

import logging
from typing import List

from lsprotocol import types
from pygls.server import LanguageServer

from .document_handler import DocumentEventHandler
from .position_calculator import PositionCalculator
from .semantic_tokens_classifier import (
    SemanticTokensParser,
    TokenModifier,
)
from .semantic_tokens_config import SemanticTokensConfig
from mxcp.lsp.utils.duckdb_connector import DuckDBConnector
from mxcp.lsp.utils.yaml_parser import YamlParser


logger = logging.getLogger(__name__)


class SemanticTokensService:
    """Main service class for semantic tokens functionality."""

    def __init__(self, duck_db_connector: DuckDBConnector):
        """Initialize the semantic tokens service."""
        self._config = SemanticTokensConfig()
        self._parser = SemanticTokensParser(duck_db_connector)
        self._position_calculator = PositionCalculator(duck_db_connector)

    def get_semantic_tokens_full(self, params: types.SemanticTokensParams) -> types.SemanticTokens:
        """
        Return the semantic tokens for the entire document.
        
        This method maintains the exact same behavior as the original implementation.
        
        Args:
            params: Semantic tokens parameters
            
        Returns:
            SemanticTokens object with token data
        """
        logger.debug(f"Semantic tokens request received for {params.text_document.uri}")
        
        try:
            document_uri = params.text_document.uri
            
            # This will be set by the register function
            if not hasattr(self, '_server'):
                logger.error("Server not set - register_semantic_tokens must be called first")
                return types.SemanticTokens(data=[])
            
            document = self._server.workspace.get_text_document(document_uri)
            yaml_parser = YamlParser(document.source)
            
            logger.debug(f"Checking if should provide LSP for semantic tokens")
            should_provide = yaml_parser.should_provide_lsp()
            logger.debug(f"Should provide LSP: {should_provide}")
            
            if not should_provide:
                logger.debug("Not providing LSP for this document - returning empty semantic tokens")
                return types.SemanticTokens(data=[])
            
            # Get or parse tokens
            logger.debug(f"Getting tokens for SQL code: {yaml_parser.code[:50]}...")
            tokens = self._get_or_parse_tokens(yaml_parser, document_uri)
            logger.debug(f"Found {len(tokens)} tokens")
            
            # Calculate relative positions
            data = self._position_calculator.calculate_relative_positions(
                tokens, yaml_parser.code_span
            )
            
            logger.debug(f"Returning semantic tokens with {len(data)} data points")
            return types.SemanticTokens(data=data)
            
        except Exception as e:
            logger.error(f"Error generating semantic tokens for {params.text_document.uri}: {e}")
            return types.SemanticTokens(data=[])

    def _get_or_parse_tokens(self, yaml_parser: YamlParser, document_uri: str) -> List:
        """Get cached tokens or parse if not available."""
        tokens = self._parser.get_tokens_for_uri(document_uri)
        
        if not tokens:
            self._parser.parse(yaml_parser.code, document_uri)
            tokens = self._parser.get_tokens_for_uri(document_uri)
        
        return tokens

    def _set_server(self, server: LanguageServer) -> None:
        """Set the server instance (called by register function)."""
        self._server = server


def register_semantic_tokens(
    server: LanguageServer, 
    duck_db_connector: DuckDBConnector
) -> tuple[SemanticTokensService, DocumentEventHandler]:
    """
    Register semantic tokens functionality with the LSP server.
    
    Args:
        server: The language server instance
        duck_db_connector: DuckDB connector for token parsing
        
    Returns:
        Tuple of (semantic tokens service, document event handler)
    """
    try:
        service = SemanticTokensService(duck_db_connector)
        service._set_server(server)
        
        parser = service._parser
        document_handler = DocumentEventHandler(server, parser)

        # Register semantic tokens feature
        @server.feature(
            types.TEXT_DOCUMENT_SEMANTIC_TOKENS_FULL,
            types.SemanticTokensLegend(
                token_types=SemanticTokensConfig.TOKEN_TYPES,
                token_modifiers=[m.name for m in TokenModifier],
            ),
        )
        def semantic_tokens_full(params: types.SemanticTokensParams):
            """Return the semantic tokens for the entire document."""
            return service.get_semantic_tokens_full(params)
        
        logger.info("Semantic tokens functionality registered successfully")
        return service, document_handler
        
    except Exception as e:
        logger.error(f"Error registering semantic tokens functionality: {e}")
        raise 