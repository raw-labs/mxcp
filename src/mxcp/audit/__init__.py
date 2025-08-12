# -*- coding: utf-8 -*-
"""High-level audit interface for MXCP.

This package provides a simplified interface for audit operations,
built on top of mxcp.sdk.audit. It includes utilities for CLI commands,
configuration parsing, and common audit operations.
"""

from .exporters import ExportFormat, export_to_csv, export_to_duckdb
from .manager import TimeRange
from .utils import format_audit_record, parse_time_since

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
]