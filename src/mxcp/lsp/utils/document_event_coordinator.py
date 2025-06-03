"""
Document Event Coordinator - Manages document events for multiple LSP features.

This coordinator ensures that document events (open, change) are registered only once
and then distributed to all features that need them.
"""

import logging
from typing import List, Callable, Protocol

from lsprotocol import types
from pygls.server import LanguageServer


logger = logging.getLogger(__name__)


class DocumentEventHandler(Protocol):
    """Protocol for document event handlers."""
    
    def handle_document_open(self, params: types.DidOpenTextDocumentParams) -> None:
        """Handle document open event."""
        ...
    
    def handle_document_change(self, params: types.DidChangeTextDocumentParams) -> None:
        """Handle document change event."""
        ...


class DocumentEventCoordinator:
    """Coordinates document events between multiple LSP features."""
    
    def __init__(self):
        """Initialize the document event coordinator."""
        self._handlers: List[DocumentEventHandler] = []
        self._registered = False
    
    def register_handler(self, handler: DocumentEventHandler) -> None:
        """
        Register a document event handler.
        
        Args:
            handler: Handler that implements DocumentEventHandler protocol
        """
        self._handlers.append(handler)
        logger.info(f"Registered document event handler: {type(handler).__name__}")
    
    def register_with_server(self, server: LanguageServer) -> None:
        """
        Register document events with the LSP server.
        
        This should only be called once after all handlers are registered.
        
        Args:
            server: The language server instance
        """
        if self._registered:
            logger.warning("Document events already registered with server")
            return
        
        @server.feature(types.TEXT_DOCUMENT_DID_OPEN)
        def did_open(params: types.DidOpenTextDocumentParams):
            """Handle document open events and distribute to all handlers."""
            for handler in self._handlers:
                try:
                    handler.handle_document_open(params)
                except Exception as e:
                    logger.error(f"Error in document open handler {type(handler).__name__}: {e}")

        @server.feature(types.TEXT_DOCUMENT_DID_CHANGE)
        def did_change(params: types.DidChangeTextDocumentParams):
            """Handle document change events and distribute to all handlers."""
            for handler in self._handlers:
                try:
                    handler.handle_document_change(params)
                except Exception as e:
                    logger.error(f"Error in document change handler {type(handler).__name__}: {e}")
        
        self._registered = True
        logger.info(f"Document events registered with server for {len(self._handlers)} handlers") 