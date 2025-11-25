from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


class EndpointValidationResultModel(BaseModel):
    """Result of validating a single endpoint."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["ok", "error"]
    path: str
    message: str | None = None


class EndpointValidationSummaryModel(BaseModel):
    """Aggregate result for validating multiple endpoints."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["ok", "error"]
    validated: list[EndpointValidationResultModel]
    message: str | None = None

