"""
LSP server implementation for MXCP.

This package provides a comprehensive Language Server Protocol implementation
for MXCP YAML files, offering SQL language support including completion,
diagnostics, and semantic tokens.

Key Components:
- MXCPLSPServer: Production-ready LSP server with comprehensive features
- Feature modules: Modular LSP features (completion, diagnostics, semantic tokens)
- Utility modules: YAML parsing, database connectivity, and coordinate transformation

Usage Example:
    from mxcp.lsp import MXCPLSPServer
    from mxcp.config.loader import load_configs
    
    # Load MXCP configurations
    user_config, site_config = load_configs()
    
    # Create and start LSP server
    server = MXCPLSPServer(
        user_config=user_config,
        site_config=site_config,
        profile="development",
        readonly=False
    )
    
    # Start server (stdio mode for IDE integration)
    server.start()
    
    # Or start in TCP mode for testing
    server.start(use_tcp=True, host="localhost")

Architecture Features:
- Clear initialization flow with state tracking
- Robust error handling and resource cleanup
- Comprehensive documentation and error codes
- Thread-safe document event coordination
- Security-hardened YAML processing and database connections
"""

# Main MXCP LSP server with improved maintainability
from .server import MXCPLSPServer, ServerInitializationState



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
    SQLErrorType,
    DuckDBConnector,
    CoordinateTransformer,
)

__all__ = [
    # Main server
    "MXCPLSPServer",
    "ServerInitializationState",
    
    # Features
    "register_completion",
    "register_diagnostics", 
    "register_semantic_tokens",
    
    # Utilities
    "YamlParser",
    "DocumentEventCoordinator",
    "Parameter",
    "SQLValidation",
    "SQLErrorType",
    "DuckDBConnector",
    "CoordinateTransformer",
] 