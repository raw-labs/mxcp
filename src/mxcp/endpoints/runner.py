from typing import Dict, Any, List, Optional, TYPE_CHECKING
from mxcp.endpoints.executor import EndpointExecutor, EndpointType
from mxcp.endpoints.loader import EndpointLoader
from mxcp.config.user_config import UserConfig
from mxcp.config.site_config import SiteConfig

if TYPE_CHECKING:
    from mxcp.auth.providers import UserContext
    from mxcp.engine.duckdb_session import DuckDBSession

async def run_endpoint(endpoint_type: str, name: str, args: Dict[str, Any], user_config: UserConfig, site_config: SiteConfig, session: 'DuckDBSession', profile: str, validate_output: bool = True, user_context: Optional['UserContext'] = None) -> List[Dict[str, Any]]:
    """
    Run an endpoint with the given arguments, using EndpointLoader for consistency.
    Args:
        endpoint_type: 'tool', 'resource', or 'prompt'
        name: endpoint name (tool/prompt) or uri (resource)
        args: Dictionary of parameter name/value pairs
        user_config: User configuration
        site_config: Site configuration
        session: DuckDB session to use for execution
        profile: Profile name
        validate_output: Whether to validate the output against the return type definition
        user_context: Optional user context for policy enforcement
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
        executor = EndpointExecutor(EndpointType(endpoint_type), name, user_config, site_config, session, profile)
        result = await executor.execute(args, validate_output=validate_output, user_context=user_context)
        return result
    except Exception as e:
        raise RuntimeError(f"Error running endpoint: {str(e)}")