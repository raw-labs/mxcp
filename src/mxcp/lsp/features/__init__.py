"""LSP features for MXCP."""

from .completion.completion import register_completion
from .diagnostics.diagnostics import register_diagnostics  
from .semantic_tokens.semantic_tokens import register_semantic_tokens

__all__ = [
    "register_completion",
    "register_diagnostics", 
    "register_semantic_tokens",
] 