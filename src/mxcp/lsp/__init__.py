"""LSP server implementation for MXCP."""

# Main MXCP LSP server with full raw-lsp functionality
from .server import MXCPLSPServer

# Legacy server for backwards compatibility
from .server_old import MXCPLSPServerOld

# LSP features
from .features import (
    register_completion,
    register_diagnostics,
    register_semantic_tokens,
)

# LSP utilities
from .utils import (
    YamlParser,
    DocumentEventCoordinator,
    Parameter,
    SQLValidation,
    DuckDBConnector,
)

__all__ = [
    # Main server (recommended)
    "MXCPLSPServer",
    
    # Legacy server (backwards compatibility)
    "MXCPLSPServerOld",
    
    # Features
    "register_completion",
    "register_diagnostics", 
    "register_semantic_tokens",
    
    # Utilities
    "YamlParser",
    "DocumentEventCoordinator",
    "Parameter",
    "SQLValidation", 
    "DuckDBConnector",
] 