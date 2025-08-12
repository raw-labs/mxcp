# -*- coding: utf-8 -*-
"""Utility classes for audit operations."""

from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Optional


@dataclass
class TimeRange:
    """Represents a time range for audit queries."""

    start: Optional[datetime] = None
    end: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Optional[str]]:
        """Convert to dictionary with ISO timestamps."""
        return {
            "start_time": self.start.isoformat() if self.start else None,
            "end_time": self.end.isoformat() if self.end else None,
        }


# AuditManager removed - use AuditLogger directly for simpler, more direct operations
