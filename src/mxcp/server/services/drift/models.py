from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from mxcp.server.definitions.endpoints.models import EndpointDefinitionModel


class _DriftBaseModel(BaseModel):
    """Base model for drift snapshot/report structures."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class Column(_DriftBaseModel):
    name: str
    type: str


class Table(_DriftBaseModel):
    name: str
    columns: list[Column]


class ValidationResults(_DriftBaseModel):
    status: Literal["ok", "error"]
    path: str
    message: str | None = None


class TestResult(_DriftBaseModel):
    name: str | None = None
    description: str | None = None
    status: Literal["passed", "failed", "error"]
    error: str | None = None
    time: float | None = None


class TestResults(_DriftBaseModel):
    status: Literal["ok", "error", "failed"]
    tests_run: int | None = None
    tests: list[TestResult] | None = None
    message: str | None = None
    no_tests: bool | None = None


class ResourceDefinition(_DriftBaseModel):
    validation_results: ValidationResults
    test_results: TestResults | None = None
    definition: EndpointDefinitionModel | None = None
    metadata: dict[str, Any] | None = None


class DriftSnapshot(_DriftBaseModel):
    version: Literal[1] = 1
    generated_at: str
    tables: list[Table]
    resources: list[ResourceDefinition]


class ColumnModification(_DriftBaseModel):
    name: str
    old_type: str
    new_type: str


class TableChange(_DriftBaseModel):
    name: str
    change_type: Literal["added", "removed", "modified"]
    columns_added: list[Column] | None = None
    columns_removed: list[Column] | None = None
    columns_modified: list[ColumnModification] | None = None


class ResourceChange(_DriftBaseModel):
    path: str
    endpoint: str | None = None
    change_type: Literal["added", "removed", "modified"]
    validation_changed: bool | None = None
    test_results_changed: bool | None = None
    definition_changed: bool | None = None
    details: dict[str, Any] | None = None


class DriftReport(_DriftBaseModel):
    version: Literal[1] = 1
    generated_at: str
    baseline_snapshot_path: str
    current_snapshot_generated_at: str
    baseline_snapshot_generated_at: str
    has_drift: bool
    summary: dict[str, int]
    table_changes: list[TableChange]
    resource_changes: list[ResourceChange]

