"""Core types for MXCP SDK policy enforcement.

This module defines the core types used in policy enforcement without any
dependencies on configuration parsing or other MXCP modules.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional


class PolicyAction(Enum):
    """Available policy actions for controlling access and data filtering."""
    DENY = "deny"
    FILTER_FIELDS = "filter_fields" 
    MASK_FIELDS = "mask_fields"
    FILTER_SENSITIVE_FIELDS = "filter_sensitive_fields"


@dataclass
class PolicyDefinition:
    """Definition of a single policy rule.
    
    Attributes:
        condition: CEL expression that determines when this policy applies
        action: The action to take when the condition is met
        reason: Optional human-readable reason for the action (used for DENY)
        fields: Optional list of field names (used for FILTER_FIELDS and MASK_FIELDS)
    """
    condition: str
    action: PolicyAction
    reason: Optional[str] = None
    fields: Optional[List[str]] = None


@dataclass
class PolicySet:
    """Set of policies for input and output validation.
    
    Attributes:
        input_policies: Policies applied to input parameters before execution
        output_policies: Policies applied to output data after execution
    """
    input_policies: List[PolicyDefinition]
    output_policies: List[PolicyDefinition]


class PolicyEnforcementError(Exception):
    """Raised when a policy denies access to a resource.
    
    Attributes:
        reason: Human-readable reason for the denial
    """
    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason) 