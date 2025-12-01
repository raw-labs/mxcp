"""Base Pydantic models for the MXCP SDK.

This module provides the base model class that all SDK Pydantic models should inherit from.
It establishes consistent configuration across all models including:

- Strict field validation (no extra fields allowed)
- Immutable instances for thread safety
- Consistent serialization behavior

Example:
    >>> from mxcp.sdk.models import SdkBaseModel
    >>> from pydantic import Field
    >>>
    >>> class MyModel(SdkBaseModel):
    ...     name: str
    ...     count: int = Field(default=0, ge=0)
    >>>
    >>> instance = MyModel(name="test")
    >>> instance.model_dump()
    {'name': 'test', 'count': 0}
"""

from pydantic import BaseModel, ConfigDict


class SdkBaseModel(BaseModel):
    """Base model for all MXCP SDK Pydantic models.

    All SDK models should inherit from this class to ensure consistent
    behavior across the SDK. This base model provides:

    - extra="forbid": Rejects any fields not defined in the model
    - frozen=True: Makes instances immutable for thread safety

    For models that need mutability (e.g., ExecutionContext), use
    a separate configuration or don't inherit from this base.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

