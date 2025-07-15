# -*- coding: utf-8 -*-
"""Tests for the MXCP SDK audit logger functionality."""
import pytest
import tempfile
import time
import json
from pathlib import Path

from mxcp.sdk.audit import AuditLogger


class TestAuditLoggerSensitiveRedaction:
    """Test sensitive field redaction in audit logging."""
    
    def test_schema_based_redaction(self):
        """Test redaction based on endpoint schema."""
        # Reset singleton instance
        AuditLogger._instance = None
        
        with tempfile.NamedTemporaryFile(suffix='.jsonl', delete=False) as f:
            log_path = Path(f.name)
        
        try:
            logger = AuditLogger(log_path, enabled=True)
            
            endpoint_def = {
                "parameters": [
                    {"name": "username", "type": "string"},
                    {"name": "password", "type": "string", "sensitive": True},
                    {"name": "query", "type": "string"}
                ]
            }
            
            logger.log_event(
                caller="cli",
                event_type="tool",
                name="test_tool",
                input_params={
                    "username": "john",
                    "password": "secret123",
                    "query": "SELECT * FROM users"
                },
                duration_ms=100,
                endpoint_def=endpoint_def
            )
            
            time.sleep(0.5)
            logger.shutdown()
            
            # Read and verify log
            with open(log_path, 'r') as f:
                log_entry = json.loads(f.readline())
                input_data = json.loads(log_entry['input_json'])
                
                assert input_data['username'] == "john"
                assert input_data['password'] == "[REDACTED]"
                assert input_data['query'] == "SELECT * FROM users"
                
        finally:
            log_path.unlink(missing_ok=True)
            AuditLogger._instance = None  # Clean up singleton
    
    def test_nested_schema_redaction(self):
        """Test redaction of nested sensitive fields."""
        # Reset singleton instance
        AuditLogger._instance = None
        
        with tempfile.NamedTemporaryFile(suffix='.jsonl', delete=False) as f:
            log_path = Path(f.name)
        
        try:
            logger = AuditLogger(log_path, enabled=True)
            
            endpoint_def = {
                "parameters": [
                    {
                        "name": "config",
                        "type": "object",
                        "properties": {
                            "host": {"type": "string"},
                            "credentials": {
                                "type": "object",
                                "properties": {
                                    "username": {"type": "string"},
                                    "api_key": {"type": "string", "sensitive": True}
                                }
                            }
                        }
                    }
                ]
            }
            
            logger.log_event(
                caller="http",
                event_type="tool",
                name="connect",
                input_params={
                    "config": {
                        "host": "example.com",
                        "credentials": {
                            "username": "admin",
                            "api_key": "sk-12345"
                        }
                    }
                },
                duration_ms=50,
                endpoint_def=endpoint_def
            )
            
            time.sleep(0.5)  # Increased wait time
            logger.shutdown()
            
            with open(log_path, 'r') as f:
                content = f.read()
                assert content, "Log file is empty"
                log_entry = json.loads(content.strip())
                input_data = json.loads(log_entry['input_json'])
                
                assert input_data['config']['host'] == "example.com"
                assert input_data['config']['credentials']['username'] == "admin"
                assert input_data['config']['credentials']['api_key'] == "[REDACTED]"
                
        finally:
            log_path.unlink(missing_ok=True)
            AuditLogger._instance = None  # Clean up singleton
    
    def test_no_redaction_without_schema(self):
        """Test that no redaction happens without schema."""
        # Reset singleton instance
        AuditLogger._instance = None
        
        with tempfile.NamedTemporaryFile(suffix='.jsonl', delete=False) as f:
            log_path = Path(f.name)
        
        try:
            logger = AuditLogger(log_path, enabled=True)
            
            # No endpoint_def provided
            logger.log_event(
                caller="stdio",
                event_type="resource",
                name="user_data",
                input_params={
                    "user_id": "123",
                    "api_key": "secret",
                    "password": "hidden",
                    "data": "public"
                },
                duration_ms=25
            )
            
            time.sleep(0.5)  # Increased wait time
            logger.shutdown()
            
            with open(log_path, 'r') as f:
                content = f.read()
                assert content, "Log file is empty"
                log_entry = json.loads(content.strip())
                input_data = json.loads(log_entry['input_json'])
                
                # Without schema, nothing should be redacted
                assert input_data['user_id'] == "123"
                assert input_data['api_key'] == "secret"
                assert input_data['password'] == "hidden"
                assert input_data['data'] == "public"
                
        finally:
            log_path.unlink(missing_ok=True)
            AuditLogger._instance = None  # Clean up singleton
    
    def test_scalar_types_redaction(self):
        """Test redaction of scalar types marked as sensitive."""
        # Reset singleton instance
        AuditLogger._instance = None
        
        with tempfile.NamedTemporaryFile(suffix='.jsonl', delete=False) as f:
            log_path = Path(f.name)
        
        try:
            logger = AuditLogger(log_path, enabled=True)
            
            endpoint_def = {
                "parameters": [
                    {"name": "public_info", "type": "string"},
                    {"name": "secret_key", "type": "string", "sensitive": True},
                    {"name": "balance", "type": "number", "sensitive": True},
                    {"name": "user_id", "type": "integer", "sensitive": True},
                    {"name": "is_admin", "type": "boolean", "sensitive": True}
                ]
            }
            
            logger.log_event(
                caller="cli",
                event_type="tool",
                name="test_scalars",
                input_params={
                    "public_info": "This is public",
                    "secret_key": "sk-123456",
                    "balance": 1234.56,
                    "user_id": 42,
                    "is_admin": True
                },
                duration_ms=100,
                endpoint_def=endpoint_def
            )
            
            time.sleep(0.5)
            logger.shutdown()
            
            # Read and verify log
            with open(log_path, 'r') as f:
                log_entry = json.loads(f.readline())
                input_data = json.loads(log_entry['input_json'])
                
                # Public info should remain
                assert input_data['public_info'] == "This is public"
                
                # All sensitive scalars should be redacted
                assert input_data['secret_key'] == "[REDACTED]"
                assert input_data['balance'] == "[REDACTED]"
                assert input_data['user_id'] == "[REDACTED]"
                assert input_data['is_admin'] == "[REDACTED]"
                
        finally:
            log_path.unlink(missing_ok=True)
            AuditLogger._instance = None  # Clean up singleton 