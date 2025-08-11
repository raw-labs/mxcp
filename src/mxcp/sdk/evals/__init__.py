"""MXCP SDK Evals module.

This module provides the core LLM execution framework for evaluation and testing,
designed to be reusable across different contexts and applications.

The main components are:
- LLMExecutor: Core LLM orchestration with tool calling support
- ToolExecutor: Protocol for external tool execution strategies
- Tool definition types for describing available tools to the LLM
"""

from ._types import ClaudeConfig, ModelConfigType, OpenAIConfig, ParameterDefinition, ToolDefinition
from .executor import LLMExecutor, ToolExecutor

__all__ = [
    "LLMExecutor",
    "ToolExecutor",
    "ToolDefinition",
    "ParameterDefinition",
    "ModelConfigType",
    "ClaudeConfig",
    "OpenAIConfig",
]
