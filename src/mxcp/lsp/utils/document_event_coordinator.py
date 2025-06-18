"""
Document Event Coordinator - Centralized document event handling for LSP features.

This coordinator implements a publisher-subscriber pattern for document events,
ensuring that events are registered once with the LSP server and then distributed
to all interested features.

Architecture:
- Single registration point for document events with the LSP server
- Multiple feature handlers can subscribe to receive events
- Error isolation - if one handler fails, others continue to work
- Clean separation between event registration and event handling

Usage Pattern:
1. Create coordinator instance
2. Features register their handlers with coordinator
3. Coordinator registers with LSP server (once)
4. LSP server sends events to coordinator
5. Coordinator distributes events to all registered handlers
"""

import logging
from typing import List, Callable, Protocol, Set
from threading import Lock

from lsprotocol import types
from pygls.server import LanguageServer


logger = logging.getLogger(__name__)


class DocumentEventHandler(Protocol):
    """
    Protocol defining the interface for document event handlers.
    
    Features implementing this protocol can receive document events
    through the coordinator. All methods are optional - handlers only
    need to implement methods for events they care about.
    """
    
    def handle_document_open(self, params: types.DidOpenTextDocumentParams) -> None:
        """
        Handle document open event.
        
        Called when a document is opened in the editor.
        
        Args:
            params: Document open parameters from LSP
        """
        ...
    
    def handle_document_change(self, params: types.DidChangeTextDocumentParams) -> None:
        """
        Handle document change event.
        
        Called when a document's content changes in the editor.
        
        Args:
            params: Document change parameters from LSP
        """
        ...
    
    def handle_document_close(self, params: types.DidCloseTextDocumentParams) -> None:
        """
        Handle document close event.
        
        Called when a document is closed in the editor.
        
        Args:
            params: Document close parameters from LSP
        """
        ...


class DocumentEventCoordinator:
    """
    Coordinates document events between the LSP server and multiple feature handlers.
    
    This class implements the coordinator pattern to:
    - Avoid duplicate event registrations
    - Provide error isolation between handlers  
    - Simplify feature implementation
    - Enable dynamic handler registration
    
    Thread Safety:
    - Handler registration is thread-safe
    - Event distribution is thread-safe
    - Multiple features can register handlers concurrently
    """
    
    def __init__(self):
        """Initialize the document event coordinator."""
        self._handlers: List[DocumentEventHandler] = []
        self._registered_with_server = False
        self._handler_lock = Lock()
        self._registration_lock = Lock()
    
    def register_handler(self, handler: DocumentEventHandler) -> None:
        """
        Register a document event handler.
        
        Handlers are called in the order they were registered.
        Registration is thread-safe and can be called from multiple features.
        
        Args:
            handler: Handler that implements DocumentEventHandler protocol
            
        Raises:
            ValueError: If handler is None or already registered
        """
        if handler is None:
            raise ValueError("Handler cannot be None")
        
        with self._handler_lock:
            if handler in self._handlers:
                logger.warning(f"Handler {type(handler).__name__} is already registered")
                return
            
            self._handlers.append(handler)
            logger.info(f"Registered document event handler: {type(handler).__name__}")
    
    def unregister_handler(self, handler: DocumentEventHandler) -> bool:
        """
        Unregister a document event handler.
        
        Args:
            handler: Handler to remove
            
        Returns:
            True if handler was found and removed, False otherwise
        """
        with self._handler_lock:
            try:
                self._handlers.remove(handler)
                logger.info(f"Unregistered document event handler: {type(handler).__name__}")
                return True
            except ValueError:
                logger.warning(f"Handler {type(handler).__name__} was not registered")
                return False
    
    def get_handler_count(self) -> int:
        """Get the number of registered handlers."""
        with self._handler_lock:
            return len(self._handlers)
    
    def register_with_server(self, server: LanguageServer) -> None:
        """
        Register document events with the LSP server.
        
        This should only be called once after all handlers are registered.
        Subsequent calls are ignored with a warning.
        
        Args:
            server: The language server instance
            
        Raises:
            ValueError: If server is None
            RuntimeError: If no handlers are registered
        """
        if server is None:
            raise ValueError("Server cannot be None")
        
        with self._registration_lock:
            if self._registered_with_server:
                logger.warning("Document events already registered with server")
                return
            
            if self.get_handler_count() == 0:
                raise RuntimeError("Cannot register with server: no handlers registered")
            
            self._register_server_events(server)
            self._registered_with_server = True
            
            logger.info(f"Document events registered with server for {self.get_handler_count()} handlers")
    
    def _register_server_events(self, server: LanguageServer) -> None:
        """Register the actual LSP event handlers with the server."""
        
        @server.feature(types.TEXT_DOCUMENT_DID_OPEN)
        def did_open(params: types.DidOpenTextDocumentParams):
            """Handle document open events and distribute to all handlers."""
            self._distribute_event("handle_document_open", params)

        @server.feature(types.TEXT_DOCUMENT_DID_CHANGE)
        def did_change(params: types.DidChangeTextDocumentParams):
            """Handle document change events and distribute to all handlers."""
            self._distribute_event("handle_document_change", params)
        
        @server.feature(types.TEXT_DOCUMENT_DID_CLOSE)
        def did_close(params: types.DidCloseTextDocumentParams):
            """Handle document close events and distribute to all handlers."""
            self._distribute_event("handle_document_close", params)
    
    def _distribute_event(self, method_name: str, params) -> None:
        """
        Distribute an event to all registered handlers.
        
        Errors in individual handlers are caught and logged but don't
        affect other handlers or the overall event processing.
        
        Args:
            method_name: Name of the handler method to call
            params: Event parameters to pass to handlers
        """
        with self._handler_lock:
            handlers_copy = self._handlers.copy()
        
        for handler in handlers_copy:
            try:
                method = getattr(handler, method_name, None)
                if method and callable(method):
                    method(params)
            except Exception as e:
                logger.error(f"Error in {method_name} handler {type(handler).__name__}: {e}")
    
    def clear_handlers(self) -> None:
        """
        Clear all registered handlers.
        
        This is primarily used for cleanup during server shutdown.
        """
        with self._handler_lock:
            handler_count = len(self._handlers)
            self._handlers.clear()
            logger.info(f"Cleared {handler_count} document event handlers") 