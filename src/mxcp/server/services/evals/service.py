import logging
import time
from collections.abc import Callable
from typing import Any

import click
from pydantic_ai import ModelSettings

from mxcp.sdk.auth import UserContextModel
from mxcp.sdk.evals import LLMExecutor, ParameterDefinition, ProviderConfig, ToolDefinition
from mxcp.sdk.validator import TypeSchemaModel
from mxcp.server.core.config.models import SiteConfigModel, UserConfigModel
from mxcp.server.core.config.site_config import find_repo_root
from mxcp.server.definitions.endpoints.loader import EndpointLoader
from mxcp.server.definitions.endpoints.models import ParamDefinitionModel, TypeDefinitionModel
from mxcp.server.definitions.evals.loader import discover_eval_files, load_eval_suite
from mxcp.server.executor.engine import create_runtime_environment
from mxcp.server.executor.runners.tool import EndpointToolExecutor, EndpointWithPath

logger = logging.getLogger(__name__)


def _create_model_config(
    model: str, user_config: UserConfigModel
) -> tuple[str, str, dict[str, Any], ProviderConfig]:
    """Create a model configuration tuple from user config.

    Args:
        model: Model name to use
        user_config: User configuration containing model settings

    Returns:
        Tuple of (model_name, model_type, options, api_key, base_url, timeout)

    Raises:
        ValueError: If model is not configured or has invalid type
    """
    models_config = user_config.models
    if not models_config or not models_config.models:
        raise ValueError("No models configuration found in user config")

    model_config = models_config.models.get(model)
    if not model_config:
        raise ValueError(f"Model '{model}' not configured in user config")

    model_type = model_config.type
    api_key = model_config.api_key
    options = dict(model_config.options or {})
    api_mode = options.get("api") or options.get("endpoint")

    if not api_key:
        raise ValueError(f"No API key configured for model '{model}'")

    if model_type not in {"anthropic", "openai"}:
        raise ValueError(f"Unknown model type: {model_type}")

    effective_model_type = (
        "openai-responses" if model_type == "openai" and api_mode == "responses" else model_type
    )

    base_url = model_config.base_url
    timeout = model_config.timeout

    # Ensure timeout also flows through options if present
    if timeout and "timeout" not in options:
        options["timeout"] = timeout

    provider_config = ProviderConfig(api_key=api_key, base_url=base_url, timeout=timeout)

    return model, effective_model_type, options, provider_config


def _build_model_settings(
    model_name: str, model_type: str, model_options: dict[str, Any], allowed_keys: set[str]
) -> ModelSettings:
    model_opts = dict(model_options)
    model_opts.pop("api", None)
    model_opts.pop("endpoint", None)

    recognized_options = {k: v for k, v in model_opts.items() if k in allowed_keys}
    body_extras: dict[str, Any] = dict(recognized_options.get("extra_body") or {})
    header_extras: dict[str, str] = dict(recognized_options.get("extra_headers") or {})
    ignored: list[str] = []

    for key, value in model_opts.items():
        if key in allowed_keys:
            continue
        if key.startswith("body:"):
            body_extras[key.split(":", 1)[1]] = value
        elif key.startswith("header:"):
            header_value: str
            if isinstance(value, list):
                header_value = ",".join(str(v) for v in value)
            else:
                header_value = str(value)
            header_extras[key.split(":", 1)[1]] = header_value
        else:
            ignored.append(key)

    if ignored:
        logger.warning(
            "Ignoring unprefixed model options for model '%s': %s. "
            "Use 'body:<key>' or 'header:<key>' prefixes.",
            model_name,
            sorted(ignored),
        )

    if body_extras:
        recognized_options["extra_body"] = body_extras
    if header_extras:
        recognized_options["extra_headers"] = header_extras

    if "max_tokens" not in recognized_options:
        recognized_options["max_tokens"] = 10_000

    return ModelSettings(**recognized_options)  # type: ignore[typeddict-item,no-any-return]


def _type_definition_to_schema(type_definition: TypeDefinitionModel) -> dict[str, Any]:
    schema: dict[str, Any] = {"type": type_definition.type}

    if type_definition.description:
        schema["description"] = type_definition.description
    if type_definition.default is not None:
        schema["default"] = type_definition.default
    if type_definition.enum:
        schema["enum"] = list(type_definition.enum)
    if type_definition.examples:
        schema["examples"] = list(type_definition.examples)

    if type_definition.type == "string":
        if type_definition.format:
            schema["format"] = type_definition.format
        if type_definition.minLength is not None:
            schema["minLength"] = type_definition.minLength
        if type_definition.maxLength is not None:
            schema["maxLength"] = type_definition.maxLength
        if type_definition.pattern:
            schema["pattern"] = type_definition.pattern
    elif type_definition.type in {"number", "integer"}:
        if type_definition.minimum is not None:
            schema["minimum"] = type_definition.minimum
        if type_definition.maximum is not None:
            schema["maximum"] = type_definition.maximum
        if type_definition.exclusiveMinimum is not None:
            schema["exclusiveMinimum"] = type_definition.exclusiveMinimum
        if type_definition.exclusiveMaximum is not None:
            schema["exclusiveMaximum"] = type_definition.exclusiveMaximum
        if type_definition.multipleOf is not None:
            schema["multipleOf"] = type_definition.multipleOf
    elif type_definition.type == "array":
        if type_definition.items is not None:
            schema["items"] = _type_definition_to_schema(type_definition.items)
        else:
            schema["items"] = {"type": "string"}
        if type_definition.minItems is not None:
            schema["minItems"] = type_definition.minItems
        if type_definition.maxItems is not None:
            schema["maxItems"] = type_definition.maxItems
        if type_definition.uniqueItems is not None:
            schema["uniqueItems"] = type_definition.uniqueItems
    elif type_definition.type == "object":
        if type_definition.properties:
            schema["properties"] = {
                key: _type_definition_to_schema(value)
                for key, value in type_definition.properties.items()
            }
        if type_definition.required:
            schema["required"] = list(type_definition.required)
        if type_definition.additionalProperties is not None:
            schema["additionalProperties"] = type_definition.additionalProperties

    return schema


def _parameter_definition_from_model(param: ParamDefinitionModel) -> ParameterDefinition:
    has_default = "default" in param.model_fields_set
    schema = _type_definition_to_schema(param)
    schema.pop("name", None)
    return ParameterDefinition(
        name=param.name,
        type=param.type,
        description=param.description or "",
        default=param.default if has_default else None,
        required=not has_default,
        schema=schema or None,
    )


def _load_endpoints(site_config: SiteConfigModel) -> list[EndpointWithPath]:
    """Load all available endpoints.

    Args:
        site_config: Site configuration for endpoint discovery

    Returns:
        List of (endpoint definition, file path)
    """
    loader = EndpointLoader(site_config)
    endpoints: list[EndpointWithPath] = []
    discovered = loader.discover_endpoints()

    for path, endpoint_def, error in discovered:
        if error is None and endpoint_def and (endpoint_def.tool or endpoint_def.resource):
            # Only include endpoints that have a tool or resource definition
            endpoints.append(EndpointWithPath(endpoint_def, path))

    return endpoints


def _convert_endpoints_to_tool_definitions(
    endpoints: list[EndpointWithPath],
) -> list[ToolDefinition]:
    """Convert endpoint definitions to ToolDefinition objects for the LLM.

    Args:
        endpoints: List of endpoint definitions

    Returns:
        List of ToolDefinition objects containing metadata for the LLM
    """
    tool_definitions = []

    for entry in endpoints:
        endpoint_def = entry.definition
        if endpoint_def.tool:
            tool = endpoint_def.tool

            tool_parameters = [
                _parameter_definition_from_model(param) for param in (tool.parameters or [])
            ]

            return_type = None
            if tool.return_:
                return_type = TypeSchemaModel.model_validate(
                    tool.return_.model_dump(mode="python", exclude_unset=True, by_alias=True)
                )

            annotations = (
                tool.annotations.model_dump(mode="python", exclude_unset=True)
                if tool.annotations
                else {}
            )

            tool_definitions.append(
                ToolDefinition(
                    name=tool.name,
                    description=tool.description or "",
                    parameters=tool_parameters,
                    return_type=return_type,
                    annotations=annotations,
                    tags=tool.tags or [],
                )
            )

        elif endpoint_def.resource:
            resource = endpoint_def.resource
            resource_parameters = [
                _parameter_definition_from_model(param) for param in (resource.parameters or [])
            ]

            return_type = None
            if resource.return_:
                return_type = TypeSchemaModel.model_validate(
                    resource.return_.model_dump(mode="python", exclude_unset=True, by_alias=True)
                )

            tool_definitions.append(
                ToolDefinition(
                    name=resource.uri,
                    description=resource.description or "",
                    parameters=resource_parameters,
                    return_type=return_type,
                    annotations={},
                    tags=resource.tags or [],
                )
            )

    return tool_definitions


def _compact_text(*parts: str, max_length: int | None = 240) -> str:
    """Join parts, collapse whitespace, and optionally truncate for display."""
    text = " ".join(p.strip() for p in parts if p).strip()
    text = " ".join(text.split())
    if max_length and len(text) > max_length:
        return text[: max_length - 3] + "..."
    return text


def _format_expected_answer_failure(
    response: str,
    expected: str,
    grade: str | None,
    comment: str | None,
    reasoning: str | None,
) -> str:
    """Build a multi-line failure detail block for expected-answer grading."""
    lines = [
        f"LLM Answer: {response}",
        f"Expected: {expected}",
        f"Grade: {grade or 'unknown'}",
        f"Comment: {comment or 'n/a'}",
        f"Reasoning: {reasoning or 'n/a'}",
    ]
    return "\n".join(lines)


async def run_eval_suite(
    suite_name: str,
    user_config: UserConfigModel,
    site_config: SiteConfigModel,
    profile: str | None,
    cli_user_context: UserContextModel | None = None,
    override_model: str | None = None,
    progress_callback: Callable[[str, str], None] | None = None,
    expected_answer_model: str | None = None,
) -> dict[str, Any]:
    """Run a specific eval suite by name.

    Args:
        suite_name: Name of the eval suite to run
        user_config: User configuration
        site_config: Site configuration
        profile: Profile to use
        cli_user_context: Optional user context from CLI
        override_model: Optional model override

    Returns:
        Dictionary with test results
    """
    # Load the eval suite
    result = load_eval_suite(suite_name, site_config)
    if not result:
        return {"error": f"Eval suite '{suite_name}' not found"}

    file_path, eval_suite = result

    # Determine which model to use
    model = override_model or eval_suite.model
    if not model:
        models_config = user_config.models
        model = models_config.default if models_config else None

    if not model:
        return {
            "error": "No model specified. Set 'model' in eval suite or configure a default model.",
            "suite": suite_name,
        }
    grading_model = expected_answer_model or getattr(eval_suite, "expected_answer_model", None)

    # Create model configuration
    model_name, model_type, model_options, provider_config = _create_model_config(
        model, user_config
    )
    allowed_keys = set(ModelSettings.__annotations__.keys())
    model_opts = dict(model_options)

    model_settings = _build_model_settings(model_name, model_type, model_opts, allowed_keys)

    # Load endpoints
    endpoints = _load_endpoints(site_config)

    # Convert endpoints to tool definitions for the LLM
    tool_definitions = _convert_endpoints_to_tool_definitions(endpoints)

    # Create runtime environment
    runtime_env = create_runtime_environment(user_config, site_config, profile)
    engine = runtime_env.execution_engine

    # Create tool executor that bridges LLM calls to endpoint execution
    tool_executor = EndpointToolExecutor(engine, endpoints)
    grading_executor: LLMExecutor | None = None

    if grading_model:
        grade_model_name, grade_model_type, grade_opts, grade_provider = _create_model_config(
            grading_model, user_config
        )
        grade_settings = _build_model_settings(
            grade_model_name, grade_model_type, dict(grade_opts), allowed_keys
        )
        grading_executor = LLMExecutor(
            grade_model_name,
            grade_model_type,
            grade_settings,
            [],  # no tools needed for grading
            tool_executor,
            provider_config=grade_provider,
        )

    logger.info(f"Running eval suite: {suite_name} from {file_path}")
    logger.info(f"Suite description: {eval_suite.description or 'No description'}")
    logger.info(f"Model: {model}")
    logger.info(f"Number of tests: {len(eval_suite.tests)}")

    total_tests = len(eval_suite.tests)
    if progress_callback:
        progress_callback(
            f"suite:{suite_name}",
            "🧪 "
            + click.style(
                f"Running suite '{suite_name}' with {total_tests} test"
                f"{'' if total_tests == 1 else 's'} using model '{model_name}'...",
                fg="yellow",
            ),
        )

    try:
        # Create LLM executor with model config, tool definitions, and tool executor
        executor = LLMExecutor(
            model_name,
            model_type,
            model_settings,
            tool_definitions,
            tool_executor,
            provider_config=provider_config,
            system_prompt=eval_suite.system_prompt,
        )

        # Run each test
        tests = []
        for idx, test in enumerate(eval_suite.tests, start=1):
            test_start = time.time()
            if progress_callback:
                progress_callback(
                    f"test:{suite_name}:{idx}",
                    "  ⏳ "
                    + click.style(
                        f"[{suite_name}] {idx}/{total_tests} • {test.name}...",
                        fg="cyan",
                    ),
                )

            # Determine user context for this test
            test_user_context = cli_user_context
            if test_user_context is None and test.user_context is not None:
                test_context_data = test.user_context
                test_user_context = UserContextModel(
                    provider="test",
                    user_id=test_context_data.get("user_id", "test_user"),
                    username=test_context_data.get("username", "test_user"),
                    email=test_context_data.get("email"),
                    name=test_context_data.get("name"),
                    avatar_url=test_context_data.get("avatar_url"),
                    raw_profile=test_context_data,
                )

            try:
                # Execute the prompt
                agent_result = await executor.execute_prompt(
                    test.prompt, user_context=test_user_context
                )

                response = agent_result.answer
                tool_calls = agent_result.tool_calls
                execution_error = agent_result.error

                # Evaluate assertions
                failures: list[str] = []
                assertions = test.assertions
                evaluation: dict[str, Any] | None = None

                # If the agent failed to execute, report it clearly
                if execution_error:
                    failures.append(f"Agent execution failed: {execution_error}")

                for call in tool_calls:
                    if call.error:
                        logger.debug(
                            "Tool '%s' failed during test '%s': %s",
                            call.tool,
                            test.name,
                            call.error,
                        )

                # Check must_call assertions
                if assertions.must_call:
                    for expected_call in assertions.must_call:
                        expected_tool = expected_call.tool
                        expected_args = expected_call.args or {}

                        found = False
                        for call in tool_calls:
                            if call.tool == expected_tool:
                                actual_args = call.arguments or {}
                                if all(actual_args.get(k) == v for k, v in expected_args.items()):
                                    found = True
                                    break

                        if not found:
                            failures.append(
                                f"Expected call to '{expected_tool}' with args {expected_args} not found"
                            )

                # Check must_not_call assertions
                if assertions.must_not_call:
                    for forbidden_tool in assertions.must_not_call:
                        if any(call.tool == forbidden_tool for call in tool_calls):
                            failures.append(
                                f"Tool '{forbidden_tool}' was called but should not have been"
                            )

                # Check answer_contains assertions
                if assertions.answer_contains:
                    for expected_text in assertions.answer_contains:
                        if expected_text.lower() not in response.lower():
                            failures.append(
                                f"Expected text '{expected_text}' not found in response"
                            )

                # Check answer_not_contains assertions
                if assertions.answer_not_contains:
                    for forbidden_text in assertions.answer_not_contains:
                        if forbidden_text.lower() in response.lower():
                            failures.append(f"Forbidden text '{forbidden_text}' found in response")

                if assertions.expected_answer:
                    logger.debug(
                        "Evaluating expected_answer assertion for test '%s': response_length=%d, expected='%s'",
                        test.name,
                        len(response),
                        (
                            assertions.expected_answer[:100] + "..."
                            if len(assertions.expected_answer) > 100
                            else assertions.expected_answer
                        ),
                    )
                    grader = grading_executor or executor
                    evaluation = await grader.evaluate_expected_answer(
                        response, assertions.expected_answer
                    )
                    grade = (evaluation.get("result") or "").lower()
                    comment = evaluation.get("comment") or "Model answer did not match expected"
                    reasoning = evaluation.get("reasoning") or ""

                    logger.debug(
                        "Expected answer evaluation for '%s': grade=%s, response='%s'",
                        test.name,
                        grade,
                        response[:150] + "..." if len(response) > 150 else response,
                    )

                    detail = _format_expected_answer_failure(
                        response,
                        assertions.expected_answer,
                        grade or "unknown",
                        comment,
                        reasoning,
                    )
                    if grade != "correct":
                        logger.info(
                            "Test '%s' failed expected_answer check: grade=%s, comment=%s",
                            test.name,
                            grade,
                            comment,
                        )
                        failures.append(detail)

                test_time = time.time() - test_start

                passed = len(failures) == 0
                tests.append(
                    {
                        "name": test.name,
                        "description": test.description,
                        "passed": passed,
                        "failures": failures,
                        "time": test_time,
                        "details": {
                            "response": response,
                            "execution_error": execution_error,
                            "tool_calls": [
                                {
                                    "id": call.id,
                                    "tool": call.tool,
                                    "arguments": call.arguments,
                                    "result": call.result,
                                    "error": call.error,
                                }
                                for call in tool_calls
                            ],
                            "expected_answer": assertions.expected_answer,
                            "expected_answer_evaluation": evaluation,
                        },
                    }
                )
                if progress_callback:
                    icon = click.style("✓", fg="green") if passed else click.style("✗", fg="red")
                    progress_callback(
                        f"test:{suite_name}:{idx}",
                        "  "
                        + icon
                        + " "
                        + click.style(
                            f"[{suite_name}] {idx}/{total_tests} • {test.name} ({test_time:.2f}s)",
                            fg="green" if passed else "red",
                        ),
                    )

            except Exception as e:
                test_time = time.time() - test_start
                tests.append(
                    {
                        "name": test.name,
                        "description": test.description,
                        "passed": False,
                        "error": str(e),
                        "time": test_time,
                    }
                )
                if progress_callback:
                    progress_callback(
                        f"test:{suite_name}:{idx}",
                        "  ✗ "
                        + click.style(
                            f"[{suite_name}] {idx}/{total_tests} • {test.name} errored: {e} ({test_time:.2f}s)",
                            fg="red",
                        ),
                    )

    finally:
        # Clean up runtime environment
        runtime_env.shutdown()

    all_passed = all(test.get("passed", False) for test in tests)

    return {
        "suite": suite_name,
        "description": eval_suite.description,
        "model": model,
        "tests": tests,
        "all_passed": all_passed,
    }


async def run_all_evals(
    user_config: UserConfigModel,
    site_config: SiteConfigModel,
    profile: str | None,
    cli_user_context: UserContextModel | None = None,
    override_model: str | None = None,
    progress_callback: Callable[[str, str], None] | None = None,
    expected_answer_model: str | None = None,
) -> dict[str, Any]:
    """Run all eval suites found in the repository.

    Args:
        user_config: User configuration
        site_config: Site configuration
        profile: Profile to use
        cli_user_context: Optional user context from CLI
        override_model: Optional model override

    Returns:
        Dictionary with results from all suites
    """
    eval_files = discover_eval_files(site_config)

    if not eval_files:
        logger.warning("No eval files found")
        return {"suites": [], "no_evals": True}

    suites = []
    for file_path, eval_suite, error in eval_files:
        if error:
            suites.append(
                {
                    "suite": str(file_path),
                    "path": str(
                        file_path.relative_to(find_repo_root()) if file_path else "unknown"
                    ),
                    "status": "error",
                    "error": error,
                }
            )
        else:
            if eval_suite is None:
                continue
            suite_name = eval_suite.suite or "unnamed"
            # Run the suite (progress_callback is passed through to run_eval_suite)
            result = await run_eval_suite(
                suite_name,
                user_config,
                site_config,
                profile,
                cli_user_context,
                override_model,
                progress_callback=progress_callback,
                expected_answer_model=expected_answer_model,
            )

            # Get relative path
            try:
                relative_path = str(file_path.relative_to(find_repo_root()))
            except Exception:
                relative_path = str(file_path)

            # Determine pass/fail
            all_passed = bool(result.get("all_passed"))
            if not all_passed and result.get("summary"):
                all_passed = result["summary"].get("failed", 1) == 0

            suites.append(
                {
                    "suite": suite_name,
                    "path": relative_path,
                    "status": "passed" if all_passed else "failed",
                    "tests": result.get("tests", []),
                    "error": result.get("error") or "",
                }
            )

    return {"suites": suites}


def get_model_config(
    user_config: UserConfigModel, model_name: str | None = None
) -> dict[str, Any] | None:
    """Get model configuration from user config.

    Args:
        user_config: User configuration
        model_name: Name of the model (optional, uses default if not provided)

    Returns:
        Model configuration if found, None otherwise
    """
    models_config = user_config.models
    if not models_config or not models_config.models:
        return None

    # If no model name provided, try to get default
    if not model_name:
        model_name = models_config.default
        if not model_name:
            return None

    model_config = models_config.models.get(model_name)
    if not model_config:
        return None
    return model_config.model_dump(exclude_none=True)
