from lsprotocol import types
from mxcp.lsp.utils import YamlParser, DuckDBConnector
from pygls.server import LanguageServer
from lsprotocol import types
import logging

logger = logging.getLogger(__name__)


def register_completion(server: LanguageServer, duck_db_connector: DuckDBConnector):
    @server.feature(types.TEXT_DOCUMENT_COMPLETION)
    def completions(params: types.CompletionParams):
        logger.debug(f"Completion request received for {params.text_document.uri} at position {params.position}")
        
        try:
            document = server.workspace.get_text_document(params.text_document.uri)
            yaml_parser = YamlParser(document.source)
            
            logger.debug(f"Checking if should provide LSP for position {params.position}")
            should_provide = yaml_parser.should_provide_lsp(
                types.Position(params.position.line, params.position.character)
            )
            logger.debug(f"Should provide LSP: {should_provide}")
            
            if not should_provide:
                logger.debug("Not providing LSP for this position - returning empty completion list")
                return types.CompletionList(is_incomplete=False, items=[])
            
            logger.debug(f"Getting completions for SQL code: {yaml_parser.code[:50]}...")
            completions_result = duck_db_connector.get_completions(
                yaml_parser.code, yaml_parser.get_parameters()
            )
            logger.debug(f"Returning {len(completions_result.items) if hasattr(completions_result, 'items') else 'unknown'} completion items")
            return completions_result
            
        except Exception as e:
            logger.error(f"Error in completion handler: {e}")
            return types.CompletionList(is_incomplete=False, items=[]) 