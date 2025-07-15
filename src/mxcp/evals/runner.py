from typing import Dict, Any, Optional, List
from mxcp.config.user_config import UserConfig
from mxcp.config.site_config import SiteConfig
from mxcp.sdk.auth.providers import UserContext
from mxcp.evals.loader import discover_eval_files, load_eval_suite, find_repo_root
from mxcp.evals.types import EvalSuite, EvalTest
from mxcp.evals.executor import LLMExecutor
from mxcp.engine.duckdb_session import DuckDBSession
import logging
import time
import asyncio
from pathlib import Path

logger = logging.getLogger(__name__)

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
    
    logger.info(f"Running eval suite: {suite_name} from {file_path}")
    logger.info(f"Suite description: {eval_suite.get('description', 'No description')}")
    logger.info(f"Model: {model}")
    logger.info(f"Number of tests: {len(eval_suite.get('tests', []))}")
    
    # Create a DuckDB session for this eval run
    session = DuckDBSession(user_config, site_config, profile)
    
    try:
        # Create LLM executor
        executor = LLMExecutor(user_config, site_config, profile, session)
        
        # Run each test
        tests = []
        for test in eval_suite.get("tests", []):
            test_start = time.time()
            
            # Determine user context for this test
            test_user_context = cli_user_context
            if test_user_context is None and "user_context" in test:
                # Create UserContext from test definition
                test_context_data = test["user_context"]
                test_user_context = UserContext(
                    provider="test",
                    user_id=test_context_data.get("user_id", "test_user"),
                    username=test_context_data.get("username", "test_user"),
                    email=test_context_data.get("email"),
                    name=test_context_data.get("name"),
                    avatar_url=test_context_data.get("avatar_url"),
                    raw_profile=test_context_data
                )
            
            try:
                # Execute the prompt
                response, tool_calls = await executor.execute_prompt(
                    test["prompt"],
                    model,
                    user_context=test_user_context
                )
                
                # Evaluate assertions
                failures = []
                assertions = test.get("assertions", {})
                
                # Check must_call assertions
                if "must_call" in assertions:
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
                if "must_not_call" in assertions:
                    for forbidden_tool in assertions["must_not_call"]:
                        if any(call["tool"] == forbidden_tool for call in tool_calls):
                            failures.append(f"Tool '{forbidden_tool}' was called but should not have been")
                
                # Check answer_contains assertions
                if "answer_contains" in assertions:
                    for expected_text in assertions["answer_contains"]:
                        if expected_text.lower() not in response.lower():
                            failures.append(f"Expected text '{expected_text}' not found in response")
                
                # Check answer_not_contains assertions
                if "answer_not_contains" in assertions:
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
        session.close()
    
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
            
            suites.append({
                "suite": suite_name,
                "path": relative_path,
                "status": "passed" if result.get("all_passed", False) else "failed",
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