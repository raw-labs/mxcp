from pathlib import Path
import yaml
from typing import Dict, List, Optional, Tuple
from mxcp.evals.types import EvalSuite
from mxcp.config.site_config import find_repo_root
import json
from jsonschema import validate
import logging

logger = logging.getLogger(__name__)

def discover_eval_files() -> List[Tuple[Path, Optional[EvalSuite], Optional[str]]]:
    """Discover all eval files in the repository.
    
    Returns:
        List of tuples where each tuple contains:
        - file_path: Path to the eval file
        - eval_suite: The loaded eval suite if successful, None if failed
        - error_message: Error message if loading failed, None if successful
    """
    base_path = find_repo_root()
    results = []
    
    schema_path = Path(__file__).parent / "schemas" / "eval-schema-1.0.0.json"
    with open(schema_path) as f:
        schema = json.load(f)
    
    # Find all files ending with -evals.yml or .evals.yml
    for pattern in ["*-evals.yml", "*.evals.yml"]:
        for f in base_path.rglob(pattern):
            try:
                with open(f) as file:
                    data = yaml.safe_load(file)
                    
                # Validate against schema
                validate(instance=data, schema=schema)
                
                results.append((f, data, None))
                logger.debug(f"Loaded eval file: {f}")
            except Exception as e:
                error_msg = f"Failed to load eval file {f}: {str(e)}"
                results.append((f, None, error_msg))
                logger.error(error_msg)
    
    return results

def load_eval_suite(suite_name: str) -> Optional[Tuple[Path, EvalSuite]]:
    """Load a specific eval suite by name.
    
    Args:
        suite_name: Name of the eval suite to load
        
    Returns:
        Tuple of (file_path, eval_suite) if found, None otherwise
    """
    eval_files = discover_eval_files()
    
    for file_path, eval_suite, error in eval_files:
        if error is None and eval_suite and eval_suite.get("suite") == suite_name:
            return (file_path, eval_suite)
    
    return None 