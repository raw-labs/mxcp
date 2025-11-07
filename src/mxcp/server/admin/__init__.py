"""
Admin API for local MXCP management.

This module provides a FastAPI-based REST interface over Unix domain socket
for local administration of MXCP instances. It enables operations like:
- Querying server status and health
- Triggering configuration reloads
- Retrieving configuration metadata

Security is enforced through file system permissions (owner-only access).
"""

from .runner import AdminAPIRunner

__all__ = ["AdminAPIRunner"]

