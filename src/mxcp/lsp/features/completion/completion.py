from lsprotocol import types
from mxcp.lsp.utils import YamlParser, DuckDBConnector
from pygls.server import LanguageServer
from typing import Optional, Union
import logging

logger = logging.getLogger(__name__)


def register_completion(server: LanguageServer, duck_db_connector: DuckDBConnector):
    """
    Register completion functionality with the LSP server.
    
    Following pygls best practices for completion registration.
    
    Args:
        server: The language server instance
        duck_db_connector: DuckDB connector for completions
    """
    
    # Register with completion options following pygls examples
    completion_options = types.CompletionOptions(
        trigger_characters=['.', ' '],
        resolve_provider=False,
    )
    
    @server.feature(types.TEXT_DOCUMENT_COMPLETION, completion_options)
    def completions(ls: LanguageServer, params: types.CompletionParams) -> Optional[Union[types.CompletionList, list[types.CompletionItem]]]:
        """
        Provide completions for the given text document position.
        
        Following the LSP specification and pygls examples for completion handling.
        
        Args:
            ls: Language server instance
            params: Completion parameters
            
        Returns:
            CompletionList or list of CompletionItems, or None if not applicable
        """
        logger.debug(f"Completion request received for {params.text_document.uri} at position {params.position}")
        
        try:
            document = ls.workspace.get_text_document(params.text_document.uri)
            yaml_parser = YamlParser(document.source)
            
            logger.debug(f"Checking if should provide LSP for position {params.position}")
            should_provide = yaml_parser.should_provide_lsp(
                types.Position(params.position.line, params.position.character)
            )
            logger.debug(f"Should provide LSP: {should_provide}")
            
            if not should_provide:
                logger.debug("Not providing LSP for this position - returning None")
                return None
            
            logger.debug(f"Getting completions for SQL code: {yaml_parser.code[:50]}...")
            completions_result = duck_db_connector.get_completions(
                yaml_parser.code, yaml_parser.get_parameters()
            )
            
            if completions_result is None:
                logger.debug("No completions available")
                return None
            
            # Ensure we return a proper CompletionList following LSP spec
            if isinstance(completions_result, types.CompletionList):
                logger.debug(f"Returning CompletionList with {len(completions_result.items)} items")
                return completions_result
            elif isinstance(completions_result, list):
                logger.debug(f"Returning {len(completions_result)} completion items as CompletionList")
                return types.CompletionList(is_incomplete=False, items=completions_result)
            else:
                logger.warning(f"Unexpected completion result type: {type(completions_result)}")
                return None
            
        except Exception as e:
            logger.error(f"Error in completion handler: {e}")
            return None 