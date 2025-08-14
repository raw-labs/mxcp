"""Audit schema definitions for MXCP application.

This module defines the audit schemas used by the MXCP CLI and server.
These are application-specific schemas, not part of the SDK.
"""

from mxcp.sdk.audit import AuditSchema, EvidenceLevel, FieldDefinition

# Single schema for all endpoint executions
ENDPOINT_EXECUTION_SCHEMA = AuditSchema(
    schema_name="mxcp.endpoints",
    version=1,
    description="Audit schema for all endpoint executions (tools, resources, prompts)",
    retention_days=90,
    evidence_level=EvidenceLevel.DETAILED,
    fields=[
        FieldDefinition("operation_type", "string"),  # "tool", "resource", or "prompt"
        FieldDefinition("operation_name", "string"),  # The specific endpoint name
        FieldDefinition("input_data", "object", sensitive=True),
        FieldDefinition("output_data", "object", required=False),
        FieldDefinition("error", "string", required=False),
        FieldDefinition(
            "policy_decision", "string", required=False
        ),  # "allow", "deny", "warn", "n/a"
        FieldDefinition("policy_reason", "string", required=False),
    ],
    indexes=["operation_type", "operation_name", "timestamp", "user_id"],
)
