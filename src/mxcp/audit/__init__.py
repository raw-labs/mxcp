# -*- coding: utf-8 -*-
"""High-level audit interface for MXCP.

This package provides a simplified interface for audit operations,
built on top of mxcp.sdk.audit. It includes utilities for CLI commands,
configuration parsing, and common audit operations.
"""

from .manager import (
    TimeRange
)

from .exporters import (
    export_to_csv,
    export_to_duckdb,
    ExportFormat
)

from .utils import (
    parse_time_since,
    format_audit_record
)

# Re-export core SDK types for convenience
from mxcp.sdk.audit import (
    AuditRecord,
    AuditSchema,
    AuditLogger,
    RedactionStrategy,
    EvidenceLevel
)

__all__ = [
    # High-level interface
    "TimeRange",
    
    # Export utilities
    "export_to_csv",
    "export_to_duckdb",
    "ExportFormat",
    
    # Utility functions
    "parse_time_since",
    "format_audit_record",
    
    # Re-exported SDK types
    "AuditRecord",
    "AuditSchema", 
    "AuditLogger",
    "RedactionStrategy",
    "EvidenceLevel"
]