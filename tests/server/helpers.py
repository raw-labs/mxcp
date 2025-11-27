from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from mxcp.sdk.auth import UserContext
from mxcp.sdk.executor.interfaces import ExecutionEngine
from mxcp.server.core.config.models import SiteConfigModel, UserConfigModel
from mxcp.server.executor.context_utils import build_execution_context
from mxcp.server.services.endpoints import (
    execute_endpoint_with_engine as _execute_endpoint_with_engine,
    execute_endpoint_with_engine_and_policy as _execute_endpoint_with_engine_and_policy,
)


def _ensure_models(
    user_config: UserConfigModel | Mapping[str, Any],
    site_config: SiteConfigModel | Mapping[str, Any],
) -> tuple[UserConfigModel, SiteConfigModel]:
    if not isinstance(user_config, UserConfigModel):
        user_config = UserConfigModel.model_validate(user_config)
    if not isinstance(site_config, SiteConfigModel):
        site_config = SiteConfigModel.model_validate(site_config)
    return user_config, site_config


async def execute_endpoint_with_engine(
    endpoint_type: str,
    name: str,
    params: dict[str, Any],
    user_config: UserConfigModel,
    site_config: SiteConfigModel,
    execution_engine: ExecutionEngine,
    *,
    skip_output_validation: bool = False,
    user_context: UserContext | None = None,
    server_ref: Any = None,
    request_headers: dict[str, str] | None = None,
    transport: str = "test",
) -> Any:
    """Test helper that builds an execution context before calling the service API."""

    user_config, site_config = _ensure_models(user_config, site_config)

    context = build_execution_context(
        user_context=user_context,
        user_config=user_config,
        site_config=site_config,
        server_ref=server_ref,
        request_headers=request_headers,
        transport=transport,
    )

    return await _execute_endpoint_with_engine(
        endpoint_type,
        name,
        params,
        user_config,
        site_config,
        execution_engine,
        context,
        skip_output_validation=skip_output_validation,
        user_context=user_context,
        server_ref=server_ref,
    )


async def execute_endpoint_with_engine_and_policy(
    endpoint_type: str,
    name: str,
    params: dict[str, Any],
    user_config: UserConfigModel,
    site_config: SiteConfigModel,
    execution_engine: ExecutionEngine,
    *,
    skip_output_validation: bool = False,
    user_context: UserContext | None = None,
    server_ref: Any = None,
    request_headers: dict[str, str] | None = None,
    transport: str = "test",
) -> tuple[Any, dict[str, Any]]:
    """Helper that returns result + policy info using a built execution context."""

    user_config, site_config = _ensure_models(user_config, site_config)

    context = build_execution_context(
        user_context=user_context,
        user_config=user_config,
        site_config=site_config,
        server_ref=server_ref,
        request_headers=request_headers,
        transport=transport,
    )

    return await _execute_endpoint_with_engine_and_policy(
        endpoint_type=endpoint_type,
        name=name,
        params=params,
        user_config=user_config,
        site_config=site_config,
        execution_engine=execution_engine,
        execution_context=context,
        skip_output_validation=skip_output_validation,
        user_context=user_context,
        server_ref=server_ref,
    )

