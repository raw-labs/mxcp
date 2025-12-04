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


class EndpointErrorModel(BaseModel):
    """A single endpoint error with path and error message.

    Used for reporting validation errors or loading failures for endpoints.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    path: str
    error: str
