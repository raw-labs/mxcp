"""Types for MXCP SDK Evals module.

This module contains type definitions for LLM models, tool definitions,
and other data structures used in the evaluation framework.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional, TypedDict

from mxcp.sdk.validator import TypeSchema


# LLM Model configuration types
@dataclass
class ModelConfig(ABC):
    """Base class for LLM model configurations."""

    name: str
    api_key: str

    @abstractmethod
    def get_type(self) -> str:
        """Get the type identifier for this model."""
        pass


@dataclass
class ClaudeConfig(ModelConfig):
    """Configuration for Claude models."""

    base_url: str = "https://api.anthropic.com"
    timeout: int = 30

    def get_type(self) -> str:
        return "claude"


@dataclass
class OpenAIConfig(ModelConfig):
    """Configuration for OpenAI models."""

    base_url: str = "https://api.openai.com/v1"
    timeout: int = 30

    def get_type(self) -> str:
        return "openai"


# Union type for all supported model configurations
ModelConfigType = ClaudeConfig | OpenAIConfig


@dataclass
class ParameterDefinition:
    """Definition of a tool parameter."""

    name: str
    type: str
    description: str = ""
    default: Any | None = None
    required: bool = True


@dataclass
class ToolDefinition:
    """Definition of a tool available to the LLM.

    This contains all the metadata needed to describe a tool in prompts,
    but doesn't include execution logic (which is handled externally).
    """

    name: str
    description: str = ""
    parameters: list[ParameterDefinition] = field(default_factory=list)
    return_type: TypeSchema | None = None
    annotations: dict[str, Any] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)

    def to_prompt_format(self) -> str:
        """Format this tool definition for inclusion in LLM prompts."""
        lines = []
        lines.append(f"Tool: {self.name}")

        if self.description:
            lines.append(f"Description: {self.description}")

        # Format parameters
        if self.parameters:
            lines.append("Parameters:")
            for param in self.parameters:
                param_line = f"  - {param.name} ({param.type})"
                if param.default is not None:
                    param_line += f" [default: {param.default}]"
                if param.description:
                    param_line += f": {param.description}"
                lines.append(param_line)
        else:
            lines.append("Parameters: None")

        # Format return type
        if self.return_type:
            return_line = f"Returns: {self.return_type.type}"
            if self.return_type.description:
                return_line += f" - {self.return_type.description}"
            lines.append(return_line)
            
            # Add more context about the return type for the LLM
            if self.return_type.format:
                lines.append(f"  Format: {self.return_type.format}")
            if self.return_type.min_length is not None:
                lines.append(f"  Min length: {self.return_type.min_length}")
            if self.return_type.max_length is not None:
                lines.append(f"  Max length: {self.return_type.max_length}")
            if self.return_type.minimum is not None:
                lines.append(f"  Minimum value: {self.return_type.minimum}")
            if self.return_type.maximum is not None:
                lines.append(f"  Maximum value: {self.return_type.maximum}")
            if self.return_type.enum:
                lines.append(f"  Allowed values: {', '.join(str(v) for v in self.return_type.enum)}")

        # Format tags
        if self.tags:
            lines.append(f"Tags: {', '.join(self.tags)}")

        return "\n".join(lines)
