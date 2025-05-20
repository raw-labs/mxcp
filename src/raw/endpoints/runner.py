from typing import Dict, Any, List
from raw.endpoints.executor import EndpointExecutor, EndpointType
from raw.endpoints.loader import EndpointLoader
from raw.config.user_config import UserConfig
from raw.config.site_config import SiteConfig

def run_endpoint(endpoint_type: str, name: str, args: Dict[str, Any], user_config: UserConfig, site_config: SiteConfig, profile: str) -> List[Dict[str, Any]]:
    """
    Run an endpoint with the given arguments, using EndpointLoader for consistency.
    Args:
        endpoint_type: 'tool', 'resource', or 'prompt'
        name: endpoint name (tool/prompt) or uri (resource)
        args: Dictionary of parameter name/value pairs
        user_config: User configuration
        site_config: Site configuration
        profile: Profile name
    Returns:
        List of result rows as dictionaries
    """
    try:
        # Load the endpoint using EndpointLoader
        loader = EndpointLoader(site_config)
        endpoint_dict = loader.load_endpoint(endpoint_type, name)
        if not endpoint_dict:
            raise FileNotFoundError(f"Endpoint {endpoint_type}/{name} not found")

        # Use EndpointExecutor for execution
        executor = EndpointExecutor(EndpointType(endpoint_type), name, user_config, site_config, profile)
        result = executor.execute(args)
        return result
    except Exception as e:
        raise RuntimeError(f"Error running endpoint: {str(e)}")