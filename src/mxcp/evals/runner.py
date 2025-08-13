import logging
import time
from typing import Any, cast

from mxcp.config._types import SiteConfig, UserConfig
from mxcp.executor.engine import create_execution_engine
from mxcp.config.site_config import find_repo_root
from mxcp.endpoints._types import EndpointDefinition
from mxcp.endpoints.loader import EndpointLoader
from mxcp.evals.loader import discover_eval_files, load_eval_suite
from mxcp.executor.runners.tool import EndpointToolExecutor
from mxcp.sdk.auth import UserContext
from mxcp.sdk.evals import (
    ClaudeConfig,
    LLMExecutor,
    ModelConfigType,
    OpenAIConfig,
    ParameterDefinition,
    ToolDefinition,
)

logger = logging.getLogger(__name__)


def _create_model_config(model: str, user_config: UserConfig) -> ModelConfigType:
    """Create a model configuration from user config.

    Args:
        model: Model name to use
        user_config: User configuration containing model settings

    Returns:
        Configured model object

    Raises:
        ValueError: If model is not configured or has invalid type
    """
    models_config = user_config.get("models", {})
    if not models_config:
        raise ValueError("No models configuration found in user config")

    models_dict = models_config.get("models", {})
    if not models_dict:
        raise ValueError("No models defined in models configuration")

    model_config: dict[str, Any] = cast(dict[str, Any], models_dict.get(model, {}))
    if not model_config:
        raise ValueError(f"Model '{model}' not configured in user config")

    model_type = model_config.get("type")
    api_key = model_config.get("api_key")

    if not api_key:
        raise ValueError(f"No API key configured for model '{model}'")

    if model_type == "claude":
        base_url = model_config.get("base_url") or "https://api.anthropic.com"
        timeout = model_config.get("timeout") or 30
        return ClaudeConfig(name=model, api_key=api_key, base_url=base_url, timeout=timeout)
    elif model_type == "openai":
        base_url = model_config.get("base_url") or "https://api.openai.com/v1"
        timeout = model_config.get("timeout") or 30
        return OpenAIConfig(name=model, api_key=api_key, base_url=base_url, timeout=timeout)
    else:
        raise ValueError(f"Unknown model type: {model_type}")


def _load_endpoints(site_config: SiteConfig) -> list[EndpointDefinition]:
    """Load all available endpoints.

    Args:
        site_config: Site configuration for endpoint discovery

    Returns:
        List of endpoint definitions
    """
    loader = EndpointLoader(site_config)
    endpoints: list[EndpointDefinition] = []
    discovered = loader.discover_endpoints()

    for _path, endpoint_def, error in discovered:
        if (
            error is None
            and endpoint_def
            and (endpoint_def.get("tool") or endpoint_def.get("resource"))
        ):
            # Only include endpoints that have a tool or resource definition
            endpoints.append(endpoint_def)

    return endpoints


def _convert_endpoints_to_tool_definitions(
    endpoints: list[EndpointDefinition],
) -> list[ToolDefinition]:
    """Convert endpoint definitions to ToolDefinition objects for the LLM.

    Args:
        endpoints: List of endpoint definitions

    Returns:
        List of ToolDefinition objects containing metadata for the LLM
    """
    tool_definitions = []

    for endpoint_def in endpoints:
        if "tool" in endpoint_def:
            tool = endpoint_def["tool"]
            if tool:
                # Convert parameters
                parameters = []
                tool_params = tool.get("parameters") or []
                for param in tool_params:
                    parameters.append(
                        ParameterDefinition(
                            name=param.get("name", ""),
                            type=param.get("type", "string"),
                            description=param.get("description", ""),
                            default=param.get("default"),
                            required="default" not in param,
                        )
                    )

                tool_definitions.append(
                    ToolDefinition(
                        name=tool["name"],
                        description=tool.get("description") or "",
                        parameters=parameters,
                        return_type=tool.get("return_"),
                        annotations=tool.get("annotations") or {},
                        tags=tool.get("tags") or [],
                    )
                )

        elif "resource" in endpoint_def:
            resource = endpoint_def["resource"]
            if resource:
                # Convert parameters
                parameters = []
                resource_params = resource.get("parameters") or []
                for param in resource_params:
                    parameters.append(
                        ParameterDefinition(
                            name=param.get("name", ""),
                            type=param.get("type", "string"),
                            description=param.get("description", ""),
                            default=param.get("default"),
                            required="default" not in param,
                        )
                    )

                tool_definitions.append(
                    ToolDefinition(
                        name=resource["uri"],
                        description=resource.get("description") or "",
                        parameters=parameters,
                        return_type=resource.get("return"),
                        annotations={},
                        tags=resource.get("tags") or [],
                    )
                )

    return tool_definitions


async def run_eval_suite(
    suite_name: str,
    user_config: UserConfig,
    site_config: SiteConfig,
    profile: str | None,
    cli_user_context: UserContext | None = None,
    override_model: str | None = None,
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
    model = override_model or eval_suite.get("model")
    if not model:
        # Try to get default model from user config
        models_config = user_config.get("models") or {}
        model = models_config.get("default") if models_config else None

    if not model:
        return {
            "error": "No model specified. Set 'model' in eval suite or configure a default model.",
            "suite": suite_name,
        }

    # Create model configuration
    model_config = _create_model_config(model, user_config)

    # Load endpoints
    endpoints = _load_endpoints(site_config)

    # Convert endpoints to tool definitions for the LLM
    tool_definitions = _convert_endpoints_to_tool_definitions(endpoints)

    # Create execution engine
    engine = create_execution_engine(user_config, site_config, profile)

    # Create tool executor that bridges LLM calls to endpoint execution
    tool_executor = EndpointToolExecutor(engine, endpoints)

    logger.info(f"Running eval suite: {suite_name} from {file_path}")
    logger.info(
        f"Suite description: {eval_suite.get('description', 'No description') if eval_suite else 'No description'}"
    )
    logger.info(f"Model: {model}")
    logger.info(f"Number of tests: {len(eval_suite.get('tests', []) if eval_suite else [])}")

    try:
        # Create LLM executor with model config, tool definitions, and tool executor
        executor = LLMExecutor(model_config, tool_definitions, tool_executor)

        # Run each test
        tests = []
        for test in eval_suite.get("tests", []) if eval_suite else []:
            test_start = time.time()

            # Determine user context for this test
            test_user_context = cli_user_context
            if test_user_context is None and "user_context" in test:
                # Create UserContext from test definition
                test_context_data = test["user_context"]
                test_user_context = UserContext(
                    provider="test",
                    user_id=(
                        test_context_data.get("user_id", "test_user")
                        if test_context_data
                        else "test_user"
                    ),
                    username=(
                        test_context_data.get("username", "test_user")
                        if test_context_data
                        else "test_user"
                    ),
                    email=test_context_data.get("email") if test_context_data else None,
                    name=test_context_data.get("name") if test_context_data else None,
                    avatar_url=test_context_data.get("avatar_url") if test_context_data else None,
                    raw_profile=test_context_data if test_context_data else {},
                )

            try:
                # Execute the prompt
                response, tool_calls = await executor.execute_prompt(
                    test["prompt"], user_context=test_user_context
                )

                # Evaluate assertions
                failures = []
                assertions = test.get("assertions", {})

                # Check must_call assertions
                if assertions and "must_call" in assertions:
                    must_calls = assertions.get("must_call")
                    if must_calls:
                        for expected_call in must_calls:
                            expected_tool = expected_call["tool"]
                            expected_args = expected_call.get("args", {})

                            # Check if tool was called with expected args
                            found = False
                            for call in tool_calls:
                                if call["tool"] == expected_tool:
                                    # Check arguments match
                                    actual_args = call.get("arguments", {})
                                    if all(
                                        actual_args.get(k) == v for k, v in expected_args.items()
                                    ):
                                        found = True
                                        break

                            if not found:
                                failures.append(
                                    f"Expected call to '{expected_tool}' with args {expected_args} not found"
                                )

                # Check must_not_call assertions
                if assertions and "must_not_call" in assertions:
                    must_not_calls = assertions.get("must_not_call")
                    if must_not_calls:
                        for forbidden_tool in must_not_calls:
                            if any(call["tool"] == forbidden_tool for call in tool_calls):
                                failures.append(
                                    f"Tool '{forbidden_tool}' was called but should not have been"
                                )

                # Check answer_contains assertions
                if assertions and "answer_contains" in assertions:
                    contains = assertions.get("answer_contains")
                    if contains:
                        for expected_text in contains:
                            if expected_text.lower() not in response.lower():
                                failures.append(
                                    f"Expected text '{expected_text}' not found in response"
                                )

                # Check answer_not_contains assertions
                if assertions and "answer_not_contains" in assertions:
                    not_contains = assertions.get("answer_not_contains")
                    if not_contains:
                        for forbidden_text in not_contains:
                            if forbidden_text.lower() in response.lower():
                                failures.append(
                                    f"Forbidden text '{forbidden_text}' found in response"
                                )

                test_time = time.time() - test_start

                tests.append(
                    {
                        "name": test["name"],
                        "description": test.get("description"),
                        "passed": len(failures) == 0,
                        "failures": failures,
                        "time": test_time,
                        "details": {"response": response, "tool_calls": tool_calls},
                    }
                )

            except Exception as e:
                test_time = time.time() - test_start
                tests.append(
                    {
                        "name": test["name"],
                        "description": test.get("description"),
                        "passed": False,
                        "error": str(e),
                        "time": test_time,
                    }
                )

    finally:
        # Clean up execution engine
        engine.shutdown()

    all_passed = all(test.get("passed", False) for test in tests)

    return {
        "suite": suite_name,
        "description": eval_suite.get("description"),
        "model": model,
        "tests": tests,
        "all_passed": all_passed,
    }


async def run_all_evals(
    user_config: UserConfig,
    site_config: SiteConfig,
    profile: str | None,
    cli_user_context: UserContext | None = None,
    override_model: str | None = None,
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
            suite_name = eval_suite.get("suite", "unnamed")
            # Run the suite
            result = await run_eval_suite(
                suite_name, user_config, site_config, profile, cli_user_context, override_model
            )

            # Get relative path
            try:
                relative_path = str(file_path.relative_to(find_repo_root()))
            except Exception:
                relative_path = str(file_path)

            # Map new result structure to old structure for backward compatibility
            all_passed = result.get("summary", {}).get("failed", 1) == 0 if result else False

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
    user_config: UserConfig, model_name: str | None = None
) -> dict[str, Any] | None:
    """Get model configuration from user config.

    Args:
        user_config: User configuration
        model_name: Name of the model (optional, uses default if not provided)

    Returns:
        Model configuration if found, None otherwise
    """
    models_config = user_config.get("models", {})
    if not models_config:
        return None

    # If no model name provided, try to get default
    if not model_name:
        model_name = models_config.get("default")
        if not model_name:
            return None

    # Get specific model config
    model_configs = models_config.get("models", {})
    if not model_configs:
        return None
    return cast(dict[str, Any] | None, model_configs.get(model_name))
