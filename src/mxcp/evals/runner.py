from typing import Dict, Any, Optional, List
from mxcp.config.user_config import UserConfig
from mxcp.config.site_config import SiteConfig
from mxcp.sdk.auth import UserContext
from mxcp.evals.loader import discover_eval_files, load_eval_suite, find_repo_root
from mxcp.evals.types import EvalSuite, EvalTest, EndpointType, ToolEndpoint, ResourceEndpoint
from mxcp.sdk.evals import LLMExecutor, ToolDefinition, ParameterDefinition, ModelConfigType, ClaudeConfig, OpenAIConfig
from mxcp.sdk.executor import ExecutionEngine
from mxcp.sdk.executor.plugins import DuckDBExecutor, PythonExecutor
from mxcp.endpoints.loader import EndpointLoader
from mxcp.evals.tool_executor import EndpointToolExecutor
import logging
import time
import asyncio
from pathlib import Path

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
    
    model_config = models_dict.get(model, {})
    if not model_config:
        raise ValueError(f"Model '{model}' not configured in user config")
    
    model_type = model_config.get("type")
    api_key = model_config.get("api_key")
    
    if not api_key:
        raise ValueError(f"No API key configured for model '{model}'")
    
    if model_type == "claude":
        base_url = model_config.get("base_url") or "https://api.anthropic.com"
        timeout = model_config.get("timeout") or 30
        return ClaudeConfig(
            name=model,
            api_key=api_key,
            base_url=base_url,
            timeout=timeout
        )
    elif model_type == "openai":
        base_url = model_config.get("base_url") or "https://api.openai.com/v1"
        timeout = model_config.get("timeout") or 30
        return OpenAIConfig(
            name=model,
            api_key=api_key,
            base_url=base_url,
            timeout=timeout
        )
    else:
        raise ValueError(f"Unknown model type: {model_type}")

def _load_endpoints(site_config: SiteConfig) -> List[EndpointType]:
    """Load all available endpoints and convert them to typed objects.
    
    Args:
        site_config: Site configuration for endpoint discovery
        
    Returns:
        List of typed endpoint objects
    """
    loader = EndpointLoader(site_config)
    endpoints = []
    discovered = loader.discover_endpoints()
    
    for path, endpoint_def, error in discovered:
        if error is None and endpoint_def:
            # Extract endpoint info with ALL metadata
            if "tool" in endpoint_def:
                tool = endpoint_def["tool"]
                endpoints.append(ToolEndpoint(
                    name=tool["name"],
                    description=tool.get("description", ""),
                    parameters=tool.get("parameters", []),
                    return_type=tool.get("return"),
                    annotations=tool.get("annotations", {}),
                    tags=tool.get("tags", []),
                    source=tool.get("source", {})
                ))
            elif "resource" in endpoint_def:
                resource = endpoint_def["resource"]
                endpoints.append(ResourceEndpoint(
                    uri=resource["uri"],
                    description=resource.get("description", ""),
                    parameters=resource.get("parameters", []),
                    return_type=resource.get("return"),
                    mime_type=resource.get("mime_type"),
                    tags=resource.get("tags", []),
                    source=resource.get("source", {})
                ))
    
    return endpoints

def _convert_endpoints_to_tool_definitions(endpoints: List[EndpointType]) -> List[ToolDefinition]:
    """Convert endpoint objects to ToolDefinition objects for the LLM.
    
    Args:
        endpoints: List of endpoint objects
        
    Returns:
        List of ToolDefinition objects containing metadata for the LLM
    """
    tool_definitions = []
    
    for endpoint in endpoints:
        # Convert parameters
        parameters = []
        if hasattr(endpoint, 'parameters') and endpoint.parameters:
            for param_dict in endpoint.parameters:
                if isinstance(param_dict, dict):
                    parameters.append(ParameterDefinition(
                        name=param_dict.get("name", ""),
                        type=param_dict.get("type", "string"),
                        description=param_dict.get("description", ""),
                        default=param_dict.get("default"),
                        required="default" not in param_dict
                    ))
        
        # Create tool definition
        if isinstance(endpoint, ToolEndpoint):
            tool_definitions.append(ToolDefinition(
                name=endpoint.name,
                description=endpoint.description,
                parameters=parameters,
                return_type=endpoint.return_type,
                annotations=endpoint.annotations,
                tags=endpoint.tags
            ))
        elif isinstance(endpoint, ResourceEndpoint):
            # Resources are also treated as tools with their URI as the name
            tool_definitions.append(ToolDefinition(
                name=endpoint.uri,
                description=endpoint.description,
                parameters=parameters,
                return_type=endpoint.return_type,
                annotations={},
                tags=endpoint.tags
            ))
    
    return tool_definitions

def _create_execution_engine(user_config: UserConfig, site_config: SiteConfig, profile: Optional[str]) -> ExecutionEngine:
    """Create an ExecutionEngine with DuckDBExecutor and PythonExecutor.
    
    Args:
        user_config: User configuration  
        site_config: Site configuration
        profile: Profile to use
        
    Returns:
        Configured ExecutionEngine
    """
    from mxcp.sdk.executor.plugins.duckdb_plugin.types import DatabaseConfig, PluginDefinition, PluginConfig, SecretDefinition
    from mxcp.sdk.executor.plugins.duckdb_plugin.types import ExtensionDefinition
    
    # Create ExecutionEngine
    engine = ExecutionEngine(strict=False)
    
    # Create DuckDB executor
    # Get database config from user config 
    db_config = user_config.get("database", {})
    database_config = DatabaseConfig(
        path=db_config.get("path", ":memory:") if db_config else ":memory:",
        readonly=db_config.get("readonly", False) if db_config else False,
        extensions=[ExtensionDefinition(name=ext) for ext in db_config.get("extensions", [])] if db_config else []
    )
    
    # Get plugins config
    plugins_list = []
    plugins_config = user_config.get("plugins", {}) if user_config else {}
    if plugins_config:
        plugins_dict = plugins_config.get("plugins", {})
        if plugins_dict:
            plugins_list = [
                PluginDefinition(name=name, module=config.get("module", name), config=name) 
                for name, config in plugins_dict.items()
                if isinstance(config, dict) and config.get("module")
            ]
    
    plugin_config = PluginConfig(
        plugins_path=plugins_config.get("plugins_path", "plugins") if plugins_config else "plugins",
        config=plugins_config.get("config", {}) if plugins_config else {}
    )
    
    # Get secrets
    secrets_list = []
    secrets_config = user_config.get("secrets", {}) if user_config else {}
    if secrets_config:
        secrets_dict = secrets_config.get("secrets", {})
        if secrets_dict:
            secrets_list = [
                SecretDefinition(name=name, type=secret.get("type", "GENERIC"), parameters=secret.get("parameters", {}))
                for name, secret in secrets_dict.items()
                if isinstance(secret, dict) and secret.get("type")
            ]
    
    duckdb_executor = DuckDBExecutor(
        database_config=database_config,
        plugins=plugins_list,
        plugin_config=plugin_config,
        secrets=secrets_list
    )
    engine.register_executor(duckdb_executor)
    
    # Create Python executor
    repo_root = find_repo_root()
    python_executor = PythonExecutor(repo_root=repo_root)
    engine.register_executor(python_executor)
    
    return engine


async def run_eval_suite(suite_name: str, user_config: UserConfig, site_config: SiteConfig,
                        profile: Optional[str], cli_user_context: Optional[UserContext] = None,
                        override_model: Optional[str] = None) -> Dict[str, Any]:
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
        models_config = user_config.get("models", {})
        model = models_config.get("default")
        
    if not model:
        return {
            "error": "No model specified. Set 'model' in eval suite or configure a default model.",
            "suite": suite_name
        }
    
    # Create model configuration
    model_config = _create_model_config(model, user_config)
    
    # Load endpoints
    endpoints = _load_endpoints(site_config)
    
    # Convert endpoints to tool definitions for the LLM
    tool_definitions = _convert_endpoints_to_tool_definitions(endpoints)
    
    # Create execution engine
    engine = _create_execution_engine(user_config, site_config, profile)
    
    # Create tool executor that bridges LLM calls to endpoint execution
    tool_executor = EndpointToolExecutor(engine, endpoints)
    
    logger.info(f"Running eval suite: {suite_name} from {file_path}")
    logger.info(f"Suite description: {eval_suite.get('description', 'No description') if eval_suite else 'No description'}")
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
                    user_id=test_context_data.get("user_id", "test_user") if test_context_data else "test_user",
                    username=test_context_data.get("username", "test_user") if test_context_data else "test_user",
                    email=test_context_data.get("email") if test_context_data else None,
                    name=test_context_data.get("name") if test_context_data else None,
                    avatar_url=test_context_data.get("avatar_url") if test_context_data else None,
                    raw_profile=test_context_data if test_context_data else {}
                )
            
            try:
                # Execute the prompt
                response, tool_calls = await executor.execute_prompt(
                    test["prompt"],
                    user_context=test_user_context
                )
                
                # Evaluate assertions
                failures = []
                assertions = test.get("assertions", {})
                
                # Check must_call assertions
                if assertions and "must_call" in assertions:
                    for expected_call in assertions["must_call"]:
                        expected_tool = expected_call["tool"]
                        expected_args = expected_call.get("args", {})
                        
                        # Check if tool was called with expected args
                        found = False
                        for call in tool_calls:
                            if call["tool"] == expected_tool:
                                # Check arguments match
                                actual_args = call.get("arguments", {})
                                if all(actual_args.get(k) == v for k, v in expected_args.items()):
                                    found = True
                                    break
                        
                        if not found:
                            failures.append(f"Expected call to '{expected_tool}' with args {expected_args} not found")
                
                # Check must_not_call assertions
                if assertions and "must_not_call" in assertions:
                    for forbidden_tool in assertions["must_not_call"]:
                        if any(call["tool"] == forbidden_tool for call in tool_calls):
                            failures.append(f"Tool '{forbidden_tool}' was called but should not have been")
                
                # Check answer_contains assertions
                if assertions and "answer_contains" in assertions:
                    for expected_text in assertions["answer_contains"]:
                        if expected_text.lower() not in response.lower():
                            failures.append(f"Expected text '{expected_text}' not found in response")
                
                # Check answer_not_contains assertions
                if assertions and "answer_not_contains" in assertions:
                    for forbidden_text in assertions["answer_not_contains"]:
                        if forbidden_text.lower() in response.lower():
                            failures.append(f"Forbidden text '{forbidden_text}' found in response")
                
                test_time = time.time() - test_start
                
                tests.append({
                    "name": test["name"],
                    "description": test.get("description"),
                    "passed": len(failures) == 0,
                    "failures": failures,
                    "time": test_time,
                    "details": {
                        "response": response,
                        "tool_calls": tool_calls
                    }
                })
                
            except Exception as e:
                test_time = time.time() - test_start
                tests.append({
                    "name": test["name"],
                    "description": test.get("description"),
                    "passed": False,
                    "error": str(e),
                    "time": test_time
                })
    
    finally:
        # Clean up execution engine
        engine.shutdown()
    
    all_passed = all(test.get("passed", False) for test in tests)
    
    return {
        "suite": suite_name,
        "description": eval_suite.get("description"),
        "model": model,
        "tests": tests,
        "all_passed": all_passed
    }


async def run_all_evals(user_config: UserConfig, site_config: SiteConfig,
                       profile: Optional[str], cli_user_context: Optional[UserContext] = None,
                       override_model: Optional[str] = None) -> Dict[str, Any]:
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
            suites.append({
                "suite": str(file_path),
                "path": str(file_path.relative_to(find_repo_root()) if file_path else "unknown"),
                "status": "error",
                "error": error
            })
        else:
            suite_name = eval_suite.get("suite", "unnamed")
            # Run the suite
            result = await run_eval_suite(
                suite_name, user_config, site_config, profile,
                cli_user_context, override_model
            )
            
            # Get relative path
            try:
                relative_path = str(file_path.relative_to(find_repo_root()))
            except:
                relative_path = str(file_path)
            
            # Map new result structure to old structure for backward compatibility
            all_passed = result.get("summary", {}).get("failed", 1) == 0 if result else False
            
            suites.append({
                "suite": suite_name,
                "path": relative_path,
                "status": "passed" if all_passed else "failed",
                "tests": result.get("tests", []),
                "error": result.get("error")
            })
    
    return {"suites": suites}


def get_model_config(user_config: UserConfig, model_name: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Get model configuration from user config.
    
    Args:
        user_config: User configuration
        model_name: Name of the model (optional, uses default if not provided)
        
    Returns:
        Model configuration if found, None otherwise
    """
    models_config = user_config.get("models", {})
    
    # If no model name provided, try to get default
    if not model_name:
        model_name = models_config.get("default")
        if not model_name:
            return None
    
    # Get specific model config
    model_configs = models_config.get("models", {})
    return model_configs.get(model_name) 