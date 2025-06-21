from typing import Dict, Any, Optional, List
from mxcp.config.user_config import UserConfig
from mxcp.config.site_config import SiteConfig
from mxcp.auth.providers import UserContext
from mxcp.evals.loader import discover_eval_files, load_eval_suite
from mxcp.evals.types import EvalSuite, EvalTest
import logging
import time

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
    result = load_eval_suite(suite_name)
    if not result:
        return {"error": f"Eval suite '{suite_name}' not found"}
    
    file_path, eval_suite = result
    
    # TODO: Implement actual eval execution
    # For now, return a placeholder result
    logger.info(f"Would run eval suite: {suite_name} from {file_path}")
    logger.info(f"Suite description: {eval_suite.get('description', 'No description')}")
    logger.info(f"Model: {override_model or eval_suite.get('model', 'default model')}")
    logger.info(f"Number of tests: {len(eval_suite.get('tests', []))}")
    
    # Placeholder results
    tests = []
    for test in eval_suite.get("tests", []):
        test_start = time.time()
        # TODO: Replace with actual LLM call
        test_time = time.time() - test_start
        
        tests.append({
            "name": test["name"],
            "description": test.get("description"),
            "passed": False,  # Placeholder
            "failures": ["Eval execution not implemented yet"],
            "time": test_time
        })
    
    return {
        "suite": suite_name,
        "description": eval_suite.get("description"),
        "model": override_model or eval_suite.get("model", "default"),
        "tests": tests,
        "all_passed": False
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
    eval_files = discover_eval_files()
    
    if not eval_files:
        logger.warning("No eval files found")
        return {"suites": [], "no_evals": True}
    
    suites = []
    for file_path, eval_suite, error in eval_files:
        if error:
            suites.append({
                "suite": str(file_path),
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
            
            suites.append({
                "suite": suite_name,
                "status": "passed" if result.get("all_passed", False) else "failed",
                "tests": result.get("tests", []),
                "error": result.get("error")
            })
    
    return {"suites": suites}

def get_model_config(user_config: UserConfig, model_name: str) -> Optional[Dict[str, Any]]:
    """Get model configuration from user config.
    
    Args:
        user_config: User configuration
        model_name: Name of the model
        
    Returns:
        Model configuration if found, None otherwise
    """
    # TODO: Once we update user config schema to include models,
    # this will retrieve the model configuration
    logger.info(f"Would retrieve config for model: {model_name}")
    return None 