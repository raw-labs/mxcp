from typing import Any, Dict, Optional
import json
import logging
from mcp.server.fastmcp import FastMCP
from raw.endpoints.loader import EndpointLoader
from raw.endpoints.executor import EndpointExecutor, EndpointType
from raw.config.user_config import UserConfig
from raw.config.site_config import SiteConfig, get_active_profile

logger = logging.getLogger(__name__)

class RAWMCP:
    """RAW MCP Server implementation that bridges RAW endpoints with MCP protocol."""
    
    def __init__(self, user_config: UserConfig, site_config: SiteConfig, profile: Optional[str] = None, stateless_http: bool = False, json_response: bool = False, host: str = "localhost", port: int = 8000):
        """Initialize the RAW MCP server.
        
        Args:
            profile: Optional profile name to use for configuration
            stateless_http: Whether to run in stateless HTTP mode
            json_response: Whether to use JSON responses instead of SSE
            host: The host to bind to
            port: The port to bind to
        """
        self.mcp = FastMCP(
            "RAW Server",
            stateless_http=stateless_http,
            json_response=json_response,
            host=host,
            port=port
        )
        self.user_config = user_config
        self.site_config = site_config
        self.active_profile = get_active_profile(self.user_config, self.site_config, profile)
        self.loader = EndpointLoader(self.site_config)
        self.endpoints = self.loader.discover_endpoints()
        logger.info(f"Discovered {len(self.endpoints)} endpoints")
        
    def _convert_param_type(self, value: Any, param_type: str) -> Any:
        """Convert parameter value to the correct type based on JSON Schema type.
        
        Args:
            value: The parameter value to convert
            param_type: The JSON Schema type to convert to
            
        Returns:
            The converted value
        """
        try:
            if param_type == "string":
                return str(value)
            elif param_type == "integer":
                return int(value)
            elif param_type == "boolean":
                if isinstance(value, str):
                    return value.lower() == "true"
                return bool(value)
            elif param_type == "array":
                if isinstance(value, str):
                    return json.loads(value)
                return value
            elif param_type == "object":
                if isinstance(value, str):
                    return json.loads(value)
                return value
            return value
        except (ValueError, json.JSONDecodeError) as e:
            logger.error(f"Error converting parameter value {value} to type {param_type}: {e}")
            raise ValueError(f"Invalid parameter value for type {param_type}: {value}")

    def _register_tool(self, tool_def: Dict[str, Any]):
        """Register a tool endpoint with MCP.
        
        Args:
            tool_def: The tool definition from YAML
        """
        @self.mcp.tool()
        async def tool_handler(**params):
            try:
                # Convert parameters to correct types
                converted_params = {}
                for param in tool_def["parameters"]:
                    param_name = param["name"]
                    if param_name in params:
                        converted_params[param_name] = self._convert_param_type(
                            params[param_name], 
                            param["type"]
                        )
                
                # Execute using RAW's executor
                executor = EndpointExecutor(EndpointType.TOOL, tool_def["name"], self.user_config, self.site_config, self.active_profile)
                return await executor.execute(converted_params)
            except Exception as e:
                logger.error(f"Error executing tool {tool_def['name']}: {e}")
                raise

    def _register_resource(self, resource_def: Dict[str, Any]):
        """Register a resource endpoint with MCP.
        
        Args:
            resource_def: The resource definition from YAML
        """
        @self.mcp.resource(resource_def['uri'])
        async def resource_handler(**params):
            try:
                converted_params = {}
                for param in resource_def["parameters"]:
                    param_name = param["name"]
                    if param_name in params:
                        converted_params[param_name] = self._convert_param_type(
                            params[param_name], 
                            param["type"]
                        )
                
                executor = EndpointExecutor(EndpointType.RESOURCE, resource_def["uri"], self.user_config, self.site_config, self.active_profile)
                return await executor.execute(converted_params)
            except Exception as e:
                logger.error(f"Error executing resource {resource_def['uri']}: {e}")
                raise

    def _register_prompt(self, prompt_def: Dict[str, Any]):
        """Register a prompt endpoint with MCP.
        
        Args:
            prompt_def: The prompt definition from YAML
        """
        @self.mcp.prompt()
        async def prompt_handler(**params):
            try:
                converted_params = {}
                for param in prompt_def["parameters"]:
                    param_name = param["name"]
                    if param_name in params:
                        converted_params[param_name] = self._convert_param_type(
                            params[param_name], 
                            param["type"]
                        )
                
                executor = EndpointExecutor(EndpointType.PROMPT, prompt_def["name"], self.user_config, self.site_config, self.active_profile)
                return await executor.execute(converted_params)
            except Exception as e:
                logger.error(f"Error executing prompt {prompt_def['name']}: {e}")
                raise

    def register_endpoints(self):
        """Register all discovered endpoints with MCP."""
        for path, endpoint_def in self.endpoints:
            try:
                if "tool" in endpoint_def:
                    self._register_tool(endpoint_def["tool"])
                    logger.info(f"Registered tool endpoint from {path}: {endpoint_def['tool']['name']}")
                elif "resource" in endpoint_def:
                    self._register_resource(endpoint_def["resource"])
                    logger.info(f"Registered resource endpoint from {path}: {endpoint_def['resource']['uri']}")
                elif "prompt" in endpoint_def:
                    self._register_prompt(endpoint_def["prompt"])
                    logger.info(f"Registered prompt endpoint from {path}: {endpoint_def['prompt']['name']}")
                else:
                    logger.warning(f"Unknown endpoint type in {path}: {endpoint_def}")
            except Exception as e:
                logger.error(f"Error registering endpoint {path}: {e}")
                raise

    def run(self, transport: str = "streamable-http"):
        """Run the MCP server.
        
        Args:
            transport: The transport to use ("streamable-http" or "stdio")
        """
        try:
            logger.info("Starting MCP server...")
            # Register all endpoints
            self.register_endpoints()
            logger.info("Endpoints registered successfully.")
            
            # Start server using MCP's built-in run method
            self.mcp.run(transport=transport)
            logger.info("MCP server started successfully.")
        except Exception as e:
            logger.error(f"Error running MCP server: {e}")
            raise 