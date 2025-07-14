"""
Type definitions for MXCP Site operations.

This module defines clean input and output types for all site operations,
following the existing CLI patterns with individual parameters.
"""

from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass
from pathlib import Path
from enum import Enum


class EndpointType(Enum):
    """Types of endpoints supported by MXCP."""
    TOOL = "tool"
    RESOURCE = "resource"
    PROMPT = "prompt"


class SeverityLevel(Enum):
    """Severity levels for linting and validation."""
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class TestStatus(Enum):
    """Status of test execution."""
    PASSED = "passed"
    FAILED = "failed"
    ERROR = "error"
    SKIPPED = "skipped"


class ValidationStatus(Enum):
    """Status of validation."""
    OK = "ok"
    ERROR = "error"


@dataclass
class EndpointInfo:
    """Information about an endpoint."""
    name: str
    type: EndpointType
    path: Path
    description: Optional[str] = None
    tags: Optional[List[str]] = None
    enabled: bool = True


# Type aliases for common parameter types
EndpointIdentifier = Union[str, EndpointInfo]
Parameters = Dict[str, Any]
UserContext = Dict[str, Any] 