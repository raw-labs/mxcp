"""Test core audit types, schemas, and data structures."""
from datetime import datetime, timezone
from mxcp.sdk.audit import (
    AuditRecord,
    AuditSchema,
    FieldDefinition,
    FieldRedaction,
    EvidenceLevel,
    RedactionStrategy,
    CallerType,
    EventType,
    Status,
)


def test_audit_record_creation():
    """Test AuditRecord creation and validation."""
    record = AuditRecord(
        schema_name="test_schema",
        schema_version=1,
        operation_type="tool",
        operation_name="test_tool",
        caller_type="cli",
        input_data={"param": "value"},
        duration_ms=100,
        user_id="user123",
        operation_status="success"
    )
    
    assert record.schema_name == "test_schema"
    assert record.schema_version == 1
    assert record.operation_type == "tool"
    assert record.operation_name == "test_tool"
    assert record.caller_type == "cli"
    assert record.input_data == {"param": "value"}
    assert record.duration_ms == 100
    assert record.user_id == "user123"
    assert record.operation_status == "success"
    assert isinstance(record.timestamp, datetime)
    assert record.record_id is not None


def test_audit_record_with_output_data():
    """Test AuditRecord with output data."""
    record = AuditRecord(
        schema_name="test_schema",
        operation_type="tool",
        operation_name="test_tool",
        caller_type="cli",
        input_data={"param": "value"},
        output_data={"result": "success"},
        duration_ms=100,
        operation_status="success"
    )
    
    assert record.output_data == {"result": "success"}


def test_audit_record_minimal():
    """Test AuditRecord with minimal required fields."""
    record = AuditRecord(
        schema_name="test_schema",
        operation_type="tool",
        operation_name="test_tool",
        caller_type="cli",
        input_data={},
        duration_ms=0,
        operation_status="success"
    )
    
    assert record.schema_name == "test_schema"
    assert record.operation_type == "tool"
    assert record.operation_name == "test_tool"


def test_field_definition():
    """Test FieldDefinition creation."""
    field = FieldDefinition(
        name="email",
        type="string",
        required=True,
        description="User email address",
        sensitive=True
    )
    
    assert field.name == "email"
    assert field.type == "string"
    assert field.required is True
    assert field.description == "User email address"
    assert field.sensitive is True


def test_field_definition_defaults():
    """Test FieldDefinition with default values."""
    field = FieldDefinition(name="id", type="string")
    
    assert field.name == "id"
    assert field.type == "string"
    assert field.required is True  # Default
    assert field.description is None  # Default
    assert field.sensitive is False  # Default


def test_field_redaction():
    """Test FieldRedaction creation."""
    redaction = FieldRedaction(
        field_path="user.email",
        strategy=RedactionStrategy.EMAIL,
        options={"preserve_domain": True}
    )
    
    assert redaction.field_path == "user.email"
    assert redaction.strategy == RedactionStrategy.EMAIL
    assert redaction.options == {"preserve_domain": True}


def test_field_redaction_no_options():
    """Test FieldRedaction without options."""
    redaction = FieldRedaction(
        field_path="password",
        strategy=RedactionStrategy.FULL
    )
    
    assert redaction.field_path == "password"
    assert redaction.strategy == RedactionStrategy.FULL
    assert redaction.options is None


def test_audit_schema_creation():
    """Test AuditSchema creation."""
    schema = AuditSchema(
        schema_name="user_events",
        version=1,
        description="User authentication events",
        retention_days=365,
        evidence_level=EvidenceLevel.REGULATORY,
        fields=[
            FieldDefinition("event_type", "string"),
            FieldDefinition("user_id", "string"),
            FieldDefinition("ip_address", "string", sensitive=True)
        ],
        field_redactions=[
            FieldRedaction("ip_address", RedactionStrategy.PARTIAL)
        ],
        extract_fields=["event_type", "user_id"],
        indexes=["event_type", "timestamp", "user_id"]
    )
    
    assert schema.schema_name == "user_events"
    assert schema.version == 1
    assert schema.description == "User authentication events"
    assert schema.retention_days == 365
    assert schema.evidence_level == EvidenceLevel.REGULATORY
    assert len(schema.fields) == 3
    assert len(schema.field_redactions) == 1
    assert schema.extract_fields == ["event_type", "user_id"]
    assert schema.indexes == ["event_type", "timestamp", "user_id"]
    assert schema.active is True  # Default
    assert isinstance(schema.created_at, datetime)


def test_audit_schema_minimal():
    """Test AuditSchema with minimal required fields."""
    schema = AuditSchema(
        schema_name="simple_events",
        version=1,
        description="Simple event schema"
    )
    
    assert schema.schema_name == "simple_events"
    assert schema.version == 1
    assert schema.description == "Simple event schema"
    assert schema.retention_days is None  # Default
    assert schema.evidence_level == EvidenceLevel.BASIC  # Default
    assert schema.fields == []  # Default
    assert schema.field_redactions == []  # Default
    assert schema.extract_fields == []  # Default
    assert schema.indexes == []  # Default


def test_audit_schema_get_schema_id():
    """Test AuditSchema.get_schema_id() method."""
    schema = AuditSchema(
        schema_name="test_schema",
        version=2,
        description="Test schema"
    )
    
    assert schema.get_schema_id() == "test_schema:v2"


def test_evidence_level_enum():
    """Test EvidenceLevel enum values."""
    assert EvidenceLevel.BASIC.value == "basic"
    assert EvidenceLevel.DETAILED.value == "detailed"
    assert EvidenceLevel.REGULATORY.value == "regulatory"
    assert EvidenceLevel.FORENSIC.value == "forensic"


def test_redaction_strategy_enum():
    """Test RedactionStrategy enum values."""
    assert RedactionStrategy.FULL.value == "full"
    assert RedactionStrategy.PARTIAL.value == "partial"
    assert RedactionStrategy.HASH.value == "hash"
    assert RedactionStrategy.TRUNCATE.value == "truncate"
    assert RedactionStrategy.EMAIL.value == "email"
    assert RedactionStrategy.PRESERVE_TYPE.value == "preserve_type"


def test_caller_type_literals():
    """Test CallerType literal values."""
    # CallerType is a Literal type, not an enum
    assert "cli" in CallerType.__args__
    assert "http" in CallerType.__args__
    assert "system" in CallerType.__args__


def test_event_type_literals():
    """Test EventType literal values."""
    # EventType is a Literal type, not an enum
    assert "tool" in EventType.__args__
    assert "resource" in EventType.__args__
    assert "prompt" in EventType.__args__


def test_status_literals():
    """Test Status literal values."""
    # Status is a Literal type, not an enum
    assert "success" in Status.__args__
    assert "error" in Status.__args__


def test_schema_field_validation():
    """Test that schema fields are properly validated."""
    # Create schema with fields that have redaction rules
    schema = AuditSchema(
        schema_name="validation_test",
        version=1,
        description="Test field validation",
        fields=[
            FieldDefinition("email", "string", sensitive=True),
            FieldDefinition("name", "string", sensitive=False)
        ],
        field_redactions=[
            FieldRedaction("email", RedactionStrategy.EMAIL),
            # Note: redaction for "name" is optional since it's not sensitive
        ]
    )
    
    # Should be able to create the schema without issues
    assert len(schema.fields) == 2
    assert len(schema.field_redactions) == 1
    
    # Check that sensitive field is properly marked
    email_field = next(f for f in schema.fields if f.name == "email")
    name_field = next(f for f in schema.fields if f.name == "name")
    
    assert email_field.sensitive is True
    assert name_field.sensitive is False


def test_schema_versioning():
    """Test schema versioning behavior."""
    schema_v1 = AuditSchema(
        schema_name="versioned_schema",
        version=1,
        description="Version 1"
    )
    
    schema_v2 = AuditSchema(
        schema_name="versioned_schema",
        version=2,
        description="Version 2"
    )
    
    assert schema_v1.get_schema_id() == "versioned_schema:v1"
    assert schema_v2.get_schema_id() == "versioned_schema:v2"
    assert schema_v1.get_schema_id() != schema_v2.get_schema_id()