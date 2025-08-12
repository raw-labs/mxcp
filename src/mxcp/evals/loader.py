import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, cast

import yaml
from jsonschema import validate

from mxcp.config.site_config import SiteConfig, find_repo_root
from mxcp.evals._types import EvalSuite

logger = logging.getLogger(__name__)


def discover_eval_files(
    site_config: Optional[SiteConfig] = None,
) -> List[Tuple[Path, Optional[EvalSuite], Optional[str]]]:
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
    results: List[Tuple[Path, Optional[EvalSuite], Optional[str]]] = []

    # Determine the evals directory
    if site_config and "paths" in site_config:
        paths_config = site_config.get("paths", {})
        if paths_config and "evals" in paths_config:
            evals_path = paths_config.get("evals")
            if evals_path:
                evals_dir = base_path / evals_path
            else:
                evals_dir = base_path / "evals"
        else:
            evals_dir = base_path / "evals"
    else:
        # Fallback to default
        evals_dir = base_path / "evals"

    # Skip if directory doesn't exist
    if not evals_dir.exists():
        logger.info(f"Evals directory {evals_dir} does not exist, skipping eval discovery")
        return results

    schema_path = Path(__file__).parent / "eval_schemas" / "eval-schema-1.json"
    with open(schema_path) as f:
        schema = json.load(f)

    # Find all YAML files in the evals directory
    for file_path in evals_dir.rglob("*.yml"):
        try:
            with open(file_path) as f:
                data = yaml.safe_load(f)

            # Check if this is a mxcp eval file
            if "mxcp" not in data:
                logger.warning(f"Skipping {file_path}: Not a mxcp eval file (missing 'mxcp' field)")
                continue

            # Validate against schema
            validate(instance=data, schema=schema)

            results.append((file_path, cast(EvalSuite, data), None))
            logger.debug(f"Loaded eval file: {file_path}")
        except Exception as e:
            error_msg = f"Failed to load eval file {file_path}: {str(e)}"
            results.append((file_path, None, error_msg))
            logger.error(error_msg)

    return results


def load_eval_suite(
    suite_name: str, site_config: Optional[SiteConfig] = None
) -> Optional[Tuple[Path, EvalSuite]]:
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
