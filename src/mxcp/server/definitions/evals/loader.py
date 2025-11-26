import logging
from pathlib import Path

import yaml
from pydantic import ValidationError

from mxcp.server.core.config.models import SiteConfigModel
from mxcp.server.core.config.site_config import find_repo_root
from mxcp.server.definitions.evals.models import EvalSuiteModel

logger = logging.getLogger(__name__)


def _extract_validation_error(error: ValidationError | Exception) -> str:
    if isinstance(error, ValidationError):
        issues = error.errors()
        if issues:
            first = issues[0]
            loc = ".".join(str(part) for part in first.get("loc", []))
            msg = first.get("msg", str(error))
            return f"{loc}: {msg}" if loc else msg
        return str(error)
    return str(error)


def discover_eval_files(
    site_config: SiteConfigModel | None = None,
) -> list[tuple[Path, EvalSuiteModel | None, str | None]]:
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
    results: list[tuple[Path, EvalSuiteModel | None, str | None]] = []

    # Determine the evals directory
    if site_config:
        evals_dir = base_path / str(site_config.paths.evals)
    else:
        # Fallback to default
        evals_dir = base_path / "evals"

    # Skip if directory doesn't exist
    if not evals_dir.exists():
        logger.info(f"Evals directory {evals_dir} does not exist, skipping eval discovery")
        return results

    # Find all YAML files in the evals directory
    for file_path in evals_dir.rglob("*.yml"):
        try:
            with open(file_path) as f:
                data = yaml.safe_load(f) or {}

            # Check if this is a mxcp eval file
            if "mxcp" not in data:
                logger.warning(f"Skipping {file_path}: Not a mxcp eval file (missing 'mxcp' field)")
                continue

            eval_suite = EvalSuiteModel.model_validate(data)

            results.append((file_path, eval_suite, None))
            logger.debug(f"Loaded eval file: {file_path}")
        except (ValidationError, Exception) as e:
            error_msg = f"Failed to load eval file {file_path}: {_extract_validation_error(e)}"
            results.append((file_path, None, error_msg))
            logger.error(error_msg)

    return results


def load_eval_suite(
    suite_name: str, site_config: SiteConfigModel | None = None
) -> tuple[Path, EvalSuiteModel] | None:
    """Load a specific eval suite by name.

    Args:
        suite_name: Name of the eval suite to load
        site_config: Site configuration to get the evals directory path

    Returns:
        Tuple of (file_path, eval_suite) if found, None otherwise
    """
    eval_files = discover_eval_files(site_config)

    for file_path, eval_suite, error in eval_files:
        if error is None and eval_suite and eval_suite.suite == suite_name:
            return (file_path, eval_suite)

    return None
