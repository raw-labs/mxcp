from pathlib import Path
import yaml
from typing import Dict, List, Optional, Tuple
from mxcp.evals.types import EvalSuite
from mxcp.config.site_config import find_repo_root, SiteConfig
import json
from jsonschema import validate
import logging

logger = logging.getLogger(__name__)

def discover_eval_files(site_config: Optional[SiteConfig] = None) -> List[Tuple[Path, Optional[EvalSuite], Optional[str]]]:
    """Discover all eval files in the configured evals directory.
    
    Args:
        site_config: Site configuration to get the evals directory path
    
    Returns:
        List of tuples where each tuple contains:
        - file_path: Path to the eval file
        - eval_suite: The loaded eval suite if successful, None if failed
        - error_message: Error message if loading failed, None if successful
    """
    base_path = find_repo_root()
    results = []
    
    # Determine the evals directory
    if site_config and "paths" in site_config and "evals" in site_config["paths"]:
        evals_dir = base_path / site_config["paths"]["evals"]
    else:
        # Fallback to default
        evals_dir = base_path / "evals"
    
    # Skip if directory doesn't exist
    if not evals_dir.exists():
        logger.info(f"Evals directory {evals_dir} does not exist, skipping eval discovery")
        return results
    
    schema_path = Path(__file__).parent / "schemas" / "eval-schema-1.0.0.json"
    with open(schema_path) as f:
        schema = json.load(f)
    
    # Find all YAML files in the evals directory
    for f in evals_dir.rglob("*.yml"):
        try:
            with open(f) as file:
                data = yaml.safe_load(file)
                
            # Check if this is a mxcp eval file
            if "mxcp" not in data:
                logger.warning(f"Skipping {f}: Not a mxcp eval file (missing 'mxcp' field)")
                continue
                
            # Validate against schema
            validate(instance=data, schema=schema)
            
            results.append((f, data, None))
            logger.debug(f"Loaded eval file: {f}")
        except Exception as e:
            error_msg = f"Failed to load eval file {f}: {str(e)}"
            results.append((f, None, error_msg))
            logger.error(error_msg)
    
    return results

def load_eval_suite(suite_name: str, site_config: Optional[SiteConfig] = None) -> Optional[Tuple[Path, EvalSuite]]:
    """Load a specific eval suite by name.
    
    Args:
        suite_name: Name of the eval suite to load
        site_config: Site configuration to get the evals directory path
        
    Returns:
        Tuple of (file_path, eval_suite) if found, None otherwise
    """
    eval_files = discover_eval_files(site_config)
    
    for file_path, eval_suite, error in eval_files:
        if error is None and eval_suite and eval_suite.get("suite") == suite_name:
            return (file_path, eval_suite)
    
    return None 