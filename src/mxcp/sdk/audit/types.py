# -*- coding: utf-8 -*-
"""Type definitions for the MXCP SDK audit module.

This module contains all type definitions and dataclasses used by the audit system.
"""
from typing import Dict, Any, Optional, Literal, List
from datetime import datetime
from dataclasses import dataclass, asdict


# Type aliases
CallerType = Literal["cli", "http", "stdio"]
EventType = Literal["tool", "resource", "prompt"]
PolicyDecision = Literal["allow", "deny", "warn", "n/a"]
Status = Literal["success", "error"]


@dataclass
class LogEvent:
    """Represents an audit log event.
    
    This is the core data structure for audit logging, capturing all relevant
    information about tool, resource, and prompt executions.
    """
    timestamp: datetime
    caller: CallerType
    type: EventType
    name: str
    input_json: str  # JSON string with redacted sensitive data
    duration_ms: int
    policy_decision: PolicyDecision
    reason: Optional[str]
    status: Status
    error: Optional[str]
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "caller": self.caller,
            "type": self.type,
            "name": self.name,
            "input_json": self.input_json,
            "duration_ms": self.duration_ms,
            "policy_decision": self.policy_decision,
            "reason": self.reason,
            "status": self.status,
            "error": self.error
        } 