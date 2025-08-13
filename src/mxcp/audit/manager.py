"""Utility classes for audit operations."""

from dataclasses import dataclass
from datetime import datetime


@dataclass
class TimeRange:
    """Represents a time range for audit queries."""

    start: datetime | None = None
    end: datetime | None = None

    def to_dict(self) -> dict[str, str | None]:
        """Convert to dictionary with ISO timestamps."""
        return {
            "start_time": self.start.isoformat() if self.start else None,
            "end_time": self.end.isoformat() if self.end else None,
        }


# AuditManager removed - use AuditLogger directly for simpler, more direct operations
