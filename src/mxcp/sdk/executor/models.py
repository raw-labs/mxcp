"""Pydantic models for the executor module."""

from mxcp.sdk.models import SdkBaseModel


class ValidationResultModel(SdkBaseModel):
    """Result of source code validation."""

    is_valid: bool
    error_message: str | None = None
