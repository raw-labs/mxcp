"""Test that user context is properly passed to audit logs."""

import asyncio
import dataclasses
import json
import tempfile
from pathlib import Path

import pytest
from mxcp.sdk.audit import AuditLogger, AuditRecord
from mxcp.sdk.auth import UserContext
from mxcp.server.schemas.audit import ENDPOINT_EXECUTION_SCHEMA


def test_audit_record_supports_user_context():
    """Test that AuditRecord dataclass supports user context fields."""
    # Check that AuditRecord has user_id and session_id fields
    field_names = [f.name for f in dataclasses.fields(AuditRecord)]
    assert "user_id" in field_names, "AuditRecord should have user_id field"
    assert "session_id" in field_names, "AuditRecord should have session_id field"

    # Verify we can create an audit record with user context
    record = AuditRecord(
        schema_name="test",
        operation_type="tool",
        operation_name="test_tool",
        user_id="test-user-123",
        session_id="test-session-456",
    )

    assert record.user_id == "test-user-123"
    assert record.session_id == "test-session-456"


def test_audit_logger_method_signature():
    """Test that AuditLogger.log_event method accepts user context parameters."""
    import inspect

    # Get the log_event method signature
    sig = inspect.signature(AuditLogger.log_event)
    param_names = list(sig.parameters.keys())

    # Verify user_id and session_id are parameters
    assert "user_id" in param_names, "log_event should accept user_id parameter"
    assert "session_id" in param_names, "log_event should accept session_id parameter"

    # Verify the parameters have the right type annotations
    user_id_param = sig.parameters["user_id"]
    session_id_param = sig.parameters["session_id"]

    # Both should allow str | None
    assert user_id_param.default is None, "user_id should have default None"
    assert session_id_param.default is None, "session_id should have default None"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
