"""Audit schema definitions for MXCP application.

This module defines the audit schemas used by the MXCP CLI and server.
These are application-specific schemas, not part of the SDK.
"""

from mxcp.sdk.audit import AuditSchemaModel, EvidenceLevel, FieldDefinitionModel

# Single schema for all endpoint executions
ENDPOINT_EXECUTION_SCHEMA = AuditSchemaModel(
    schema_name="mxcp.endpoints",
    version=1,
    description="Audit schema for all endpoint executions (tools, resources, prompts)",
    retention_days=90,
    evidence_level=EvidenceLevel.DETAILED,
    fields=[
        FieldDefinitionModel(
            name="operation_type", type="string"
        ),  # "tool", "resource", or "prompt"
        FieldDefinitionModel(name="operation_name", type="string"),  # The specific endpoint name
        FieldDefinitionModel(name="input_data", type="object", sensitive=True),
        FieldDefinitionModel(name="output_data", type="object", required=False),
        FieldDefinitionModel(name="error", type="string", required=False),
        FieldDefinitionModel(
            name="policy_decision", type="string", required=False
        ),  # "allow", "deny", "warn", "n/a"
        FieldDefinitionModel(name="policy_reason", type="string", required=False),
    ],
    # Extract key fields for easier querying and business reporting
    extract_fields=[
        "operation_type",  # Tool, resource, or prompt
        "operation_name",  # The specific endpoint
        "operation_status",  # Success or error
        "policy_decision",  # Allow, deny, warn, n/a
    ],
    indexes=["operation_type", "operation_name", "timestamp", "user_id"],
)
