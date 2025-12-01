"""Type definitions for the MXCP SDK audit module.

This module re-exports the Pydantic models from models.py for public API.
"""

from typing import Literal

from .models import (
    AuditBackend,
    AuditRecordModel,
    AuditSchemaModel,
    CallerType,
    EvidenceLevel,
    EventType,
    FieldDefinitionModel,
    FieldRedactionModel,
    IntegrityResultModel,
    PolicyDecision,
    RedactionFunc,
    RedactionStrategy,
    Status,
)

__all__ = [
    # Type aliases
    "CallerType",
    "EventType",
    "PolicyDecision",
    "Status",
    "RedactionFunc",
    # Enums
    "EvidenceLevel",
    "RedactionStrategy",
    # Models
    "FieldDefinitionModel",
    "FieldRedactionModel",
    "AuditSchemaModel",
    "IntegrityResultModel",
    "AuditRecordModel",
    # Protocol
    "AuditBackend",
]
