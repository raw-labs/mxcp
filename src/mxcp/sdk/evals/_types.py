"""Types for MXCP SDK Evals module.

This module contains type definitions for LLM models, tool definitions,
and other data structures used in the evaluation framework.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union

from mxcp.endpoints._types import TypeDefinition


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
ModelConfigType = Union[ClaudeConfig, OpenAIConfig]


@dataclass
class ParameterDefinition:
    """Definition of a tool parameter."""

    name: str
    type: str
    description: str = ""
    default: Optional[Any] = None
    required: bool = True


@dataclass
class ToolDefinition:
    """Definition of a tool available to the LLM.

    This contains all the metadata needed to describe a tool in prompts,
    but doesn't include execution logic (which is handled externally).
    """

    name: str
    description: str = ""
    parameters: List[ParameterDefinition] = field(default_factory=list)
    return_type: Optional[TypeDefinition] = None
    annotations: Dict[str, Any] = field(default_factory=dict)
    tags: List[str] = field(default_factory=list)

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
            return_type_str = self.return_type.get("type", "any")
            return_description = self.return_type.get("description", "")
            return_line = f"Returns: {return_type_str}"
            if return_description:
                return_line += f" - {return_description}"
            lines.append(return_line)

        # Format tags
        if self.tags:
            lines.append(f"Tags: {', '.join(self.tags)}")

        return "\n".join(lines)
