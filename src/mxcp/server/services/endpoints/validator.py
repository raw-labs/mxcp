import re
from pathlib import Path
from typing import cast

from jinja2 import Environment, meta

from mxcp.sdk.executor import ExecutionEngine
from mxcp.server.core.config.models import SiteConfigModel
from mxcp.server.core.config.site_config import find_repo_root
from mxcp.server.definitions.endpoints.loader import EndpointLoader
from mxcp.server.definitions.endpoints.models import (
    EndpointDefinitionModel,
    PromptDefinitionModel,
    ResourceDefinitionModel,
    ToolDefinitionModel,
)
from mxcp.server.definitions.endpoints.utils import get_endpoint_source_code
from mxcp.server.services.endpoints.models import (
    EndpointValidationResultModel,
    EndpointValidationSummaryModel,
)

RESOURCE_VAR_RE = re.compile(r"{([^{}]+)}")


def _validate_resource_uri_vs_params(
    res_def: ResourceDefinitionModel, path: Path
) -> EndpointValidationResultModel | None:
    uri_params = set(RESOURCE_VAR_RE.findall(res_def.uri))
    params = res_def.parameters or []
    yaml_params = {p.name for p in params}

    extra_in_yaml = yaml_params - uri_params
    if extra_in_yaml:
        return EndpointValidationResultModel(
            status="error",
            path=str(path),
            message=(
                f"Resource parameter(s) {sorted(extra_in_yaml)} are not used "
                f"in uri '{res_def.uri}'. Put them in the uri or make a "
                f"'tool:' instead."
            ),
        )
    return None


def validate_all_endpoints(
    site_config: SiteConfigModel, execution_engine: ExecutionEngine
) -> EndpointValidationSummaryModel:
    """Validate all endpoints in the repository.

    Args:
        site_config: Site configuration
        execution_engine: SDK execution engine to use for validation

    Returns:
        Dictionary with validation status and details for each endpoint
    """
    try:
        # Use EndpointLoader to discover endpoints
        loader = EndpointLoader(site_config)
        endpoints = loader.discover_endpoints()
        if not endpoints:
            return EndpointValidationSummaryModel(
                status="error",
                validated=[],
                message="No endpoints found",
            )

        results: list[EndpointValidationResultModel] = []
        has_errors = False

        for path, endpoint, error in endpoints:
            path_str = str(path)  # Convert PosixPath to string
            if error:
                results.append(
                    EndpointValidationResultModel(status="error", path=path_str, message=error)
                )
                has_errors = True
            elif endpoint:
                result = validate_endpoint_payload(endpoint, path_str, execution_engine)
                results.append(result)
                if result.status == "error":
                    has_errors = True
            else:
                results.append(
                    EndpointValidationResultModel(
                        status="error", path=path_str, message="Failed to load endpoint"
                    )
                )
                has_errors = True

        return EndpointValidationSummaryModel(
            status="error" if has_errors else "ok",
            validated=results,
        )
    except Exception as e:
        return EndpointValidationSummaryModel(status="error", validated=[], message=str(e))


def _extract_template_variables(template: str) -> set[str]:
    """Extract all Jinja template variables using Jinja2's own parser."""
    env = Environment()
    ast = env.parse(template)
    # Get all variables including nested ones
    variables = meta.find_undeclared_variables(ast)
    # Split nested variables and add their base names
    base_vars = set()
    for var in variables:
        # Handle nested variables like 'item.name'
        parts = var.split(".")
        base_vars.add(parts[0])
    return base_vars


def validate_endpoint_payload(
    endpoint: EndpointDefinitionModel, path: str, execution_engine: ExecutionEngine
) -> EndpointValidationResultModel:
    """Validate a single endpoint payload and return a typed result."""
    try:
        repo_root = find_repo_root()
        path_obj = Path(path).resolve()
        relative_path = str(path_obj.relative_to(repo_root))
    except ValueError:
        relative_path = Path(path).name
        path_obj = Path(path).resolve()
        repo_root = path_obj.parent
    except Exception:
        relative_path = Path(path).name
        path_obj = Path(path).resolve()
        repo_root = path_obj.parent

    try:
        endpoint_type: str | None = None
        component: ToolDefinitionModel | ResourceDefinitionModel | PromptDefinitionModel | None = (
            None
        )
        name: str | None = None

        if endpoint.tool is not None:
            endpoint_type = "tool"
            component = endpoint.tool
            name = component.name
        elif endpoint.resource is not None:
            endpoint_type = "resource"
            component = endpoint.resource
            name = component.uri
        elif endpoint.prompt is not None:
            endpoint_type = "prompt"
            component = endpoint.prompt
            name = component.name

        if not endpoint_type or component is None or not name:
            return EndpointValidationResultModel(
                status="error",
                path=relative_path,
                message="No valid endpoint type (tool/resource/prompt) found",
            )

        if endpoint_type == "prompt":
            prompt_def = cast(PromptDefinitionModel, component)
            messages = prompt_def.messages or []
            if not messages:
                return EndpointValidationResultModel(
                    status="error",
                    path=relative_path,
                    message="No messages found in prompt definition",
                )

            parameters = prompt_def.parameters or []
            defined_params = {p.name for p in parameters}

            for i, msg in enumerate(messages):
                template_vars = _extract_template_variables(msg.prompt)
                undefined_vars = template_vars - defined_params
                if undefined_vars:
                    return EndpointValidationResultModel(
                        status="error",
                        path=relative_path,
                        message=(
                            f"Message {i} uses undefined template variables: "
                            f"{', '.join(sorted(undefined_vars))}"
                        ),
                    )

            return EndpointValidationResultModel(status="ok", path=relative_path)

        executable_component: ToolDefinitionModel | ResourceDefinitionModel
        if endpoint_type == "resource":
            resource_def = cast(ResourceDefinitionModel, component)
            err = _validate_resource_uri_vs_params(resource_def, Path(relative_path))
            if err:
                return err
            executable_component = resource_def
        else:
            executable_component = cast(ToolDefinitionModel, component)

        language = executable_component.language or "sql"

        if language == "python":
            source = executable_component.source
            if not source or source.file is None:
                return EndpointValidationResultModel(
                    status="error",
                    path=relative_path,
                    message="Python endpoints must specify source.file",
                )

            file_path = Path(source.file)
            if not file_path.is_absolute():
                file_path = path_obj.parent / file_path

            if not file_path.exists():
                return EndpointValidationResultModel(
                    status="error",
                    path=relative_path,
                    message=f"Python source file not found: {file_path}",
                )

            return EndpointValidationResultModel(status="ok", path=relative_path)

        if language == "sql":
            try:
                sql_query = get_endpoint_source_code(endpoint, endpoint_type, path_obj, repo_root)
            except Exception as e:
                return EndpointValidationResultModel(
                    status="error",
                    path=relative_path,
                    message=f"Error resolving source code: {str(e)}",
                )

            if not sql_query:
                return EndpointValidationResultModel(
                    status="error", path=relative_path, message="No SQL query found"
                )

            try:
                validation_result = execution_engine.validate_source("sql", sql_query)
                if not validation_result.is_valid:
                    error_message = (
                        validation_result.error_message or "Source code syntax validation failed"
                    )
                    return EndpointValidationResultModel(
                        status="error",
                        path=relative_path,
                        message=f"Source code syntax validation failed: {error_message}",
                    )

                sql_param_names = execution_engine.extract_parameters("sql", sql_query)
            except Exception as e:
                return EndpointValidationResultModel(
                    status="error",
                    path=relative_path,
                    message=f"Source code validation error: {str(e)}",
                )

            if not isinstance(sql_param_names, list):
                sql_param_names = list(sql_param_names)

            yaml_params = executable_component.parameters or []
            yaml_param_names = [p.name for p in yaml_params]

            missing_params = set(sql_param_names) - set(yaml_param_names)
            extra_params = set(yaml_param_names) - set(sql_param_names)
            if missing_params or extra_params:
                return EndpointValidationResultModel(
                    status="error",
                    path=relative_path,
                    message=f"Parameter mismatch: missing={missing_params}, extra={extra_params}",
                )

            return EndpointValidationResultModel(status="ok", path=relative_path)

        return EndpointValidationResultModel(
            status="error",
            path=relative_path,
            message=f"Unsupported language '{language}' for endpoint validation",
        )

    except Exception as e:
        return EndpointValidationResultModel(status="error", path=relative_path, message=str(e))


def validate_endpoint(
    path: str, site_config: SiteConfigModel, execution_engine: ExecutionEngine
) -> EndpointValidationResultModel:
    """Validate a single endpoint file."""
    try:
        # Use EndpointLoader to properly load and validate the endpoint
        loader = EndpointLoader(site_config)
        all_endpoints = loader.discover_endpoints()

        # Find the endpoint that matches the given path
        path_obj = Path(path).resolve()
        for endpoint_path, endpoint, error in all_endpoints:
            if endpoint_path.resolve() == path_obj:
                if error:
                    return EndpointValidationResultModel(status="error", path=path, message=error)
                elif endpoint:
                    return validate_endpoint_payload(endpoint, path, execution_engine)
                else:
                    return EndpointValidationResultModel(
                        status="error", path=path, message="Failed to load endpoint"
                    )

        # If not found in discovered endpoints, it might not be a valid endpoint file
        return EndpointValidationResultModel(
            status="error",
            path=path,
            message="Endpoint file not found or not a valid endpoint",
        )

    except Exception as e:
        return EndpointValidationResultModel(status="error", path=path, message=str(e))
