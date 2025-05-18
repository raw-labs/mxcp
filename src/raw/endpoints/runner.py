from typing import Dict, Any, Optional, List
from pathlib import Path
import yaml
from raw.endpoints.executor import EndpointExecutor, EndpointType
from raw.endpoints.loader import EndpointLoader
from raw.config.site_config import find_repo_root
from raw.config.user_config import load_user_config

def run_endpoint(endpoint_type: str, name: str, args: Dict[str, Any], config: Dict[str, Any], user: str, profile: str) -> List[Dict[str, Any]]:
    """
    Run an endpoint with the given arguments, using EndpointLoader for consistency.
    Args:
        endpoint_type: 'tool', 'resource', or 'prompt'
        name: endpoint name (tool/prompt) or uri (resource)
        args: Dictionary of parameter name/value pairs
        config: User configuration
        user: User name
        profile: Profile name
    Returns:
        List of result rows as dictionaries
    """
    try:
        # Load the endpoint using EndpointLoader
        repo_root = find_repo_root()
        site_config = {}  # If needed, load site config here
        loader = EndpointLoader(site_config)
        endpoint_dict = loader.load_endpoint(endpoint_type, name)
        if not endpoint_dict:
            raise FileNotFoundError(f"Endpoint {endpoint_type}/{name} not found")

        # Use EndpointExecutor for execution
        executor = EndpointExecutor(EndpointType(endpoint_type), name)
        result = executor.execute(args)
        return result
    except Exception as e:
        raise RuntimeError(f"Error running endpoint: {str(e)}")