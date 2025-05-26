from typing import Dict, Any, List, Optional
from mxcp.endpoints.executor import EndpointExecutor, EndpointType
from mxcp.endpoints.loader import EndpointLoader
from mxcp.config.user_config import UserConfig
from mxcp.config.site_config import SiteConfig

async def run_endpoint(endpoint_type: str, name: str, args: Dict[str, Any], user_config: UserConfig, site_config: SiteConfig, profile: str, validate_output: bool = True, readonly: Optional[bool] = None) -> List[Dict[str, Any]]:
    """
    Run an endpoint with the given arguments, using EndpointLoader for consistency.
    Args:
        endpoint_type: 'tool', 'resource', or 'prompt'
        name: endpoint name (tool/prompt) or uri (resource)
        args: Dictionary of parameter name/value pairs
        user_config: User configuration
        site_config: Site configuration
        profile: Profile name
        validate_output: Whether to validate the output against the return type definition
        readonly: Whether to open DuckDB connection in read-only mode
    Returns:
        List of result rows as dictionaries
    """
    try:
        # Load the endpoint using EndpointLoader
        loader = EndpointLoader(site_config)
        result = loader.load_endpoint(endpoint_type, name)
        if not result:
            raise FileNotFoundError(f"Endpoint {endpoint_type} {name} not found")

        # Use EndpointExecutor for execution
        executor = EndpointExecutor(EndpointType(endpoint_type), name, user_config, site_config, profile, readonly=readonly)
        result = await executor.execute(args, validate_output=validate_output)
        return result
    except Exception as e:
        raise RuntimeError(f"Error running endpoint: {str(e)}")