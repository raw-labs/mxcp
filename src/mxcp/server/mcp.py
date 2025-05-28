from typing import Any, Dict, Optional, List
import json
import logging
import traceback
from mcp.server.fastmcp import FastMCP
from mcp.server.auth.settings import AuthSettings, ClientRegistrationOptions
from mxcp.endpoints.loader import EndpointLoader
from mxcp.endpoints.executor import EndpointExecutor, EndpointType
from mxcp.config.user_config import UserConfig
from mxcp.config.site_config import SiteConfig, get_active_profile
from mxcp.endpoints.schema import validate_endpoint
from makefun import create_function
from mxcp.engine.duckdb_session import DuckDBSession
from mxcp.auth.providers import create_oauth_handler, GeneralOAuthAuthorizationServer, MCP_SCOPE
from mxcp.auth.middleware import AuthenticationMiddleware
from mxcp.auth.context import get_user_context
from mxcp.auth.url_utils import create_url_builder

logger = logging.getLogger(__name__)

class RAWMCP:
    """MXCP MCP Server implementation that bridges MXCP endpoints with MCP protocol."""
    
    def __init__(self, user_config: UserConfig, site_config: SiteConfig, profile: Optional[str] = None, stateless_http: bool = False, json_response: bool = False, host: str = "localhost", port: int = 8000, enable_sql_tools: Optional[bool] = None, readonly: bool = False):
        """Initialize the MXCP MCP server.
        
        Args:
            user_config: The user configuration loaded from ~/.mxcp/config.yml
            site_config: The site configuration loaded from mxcp-site.yml
            profile: Optional profile name to use for configuration
            stateless_http: Whether to run in stateless HTTP mode
            json_response: Whether to use JSON responses instead of SSE
            host: The host to bind to
            port: The port to bind to
            enable_sql_tools: Whether to enable built-in SQL querying and schema exploration tools.
                            If None, uses the value from site_config.sql_tools.enabled (defaults to True)
            readonly: Whether to open DuckDB connection in read-only mode
        """
        # Initialize OAuth authentication
        auth_config = user_config.get("auth", {})
        self.oauth_handler = create_oauth_handler(auth_config, host=host, port=port, user_config=user_config)
        self.oauth_server = None
        auth_settings = None
        
        if self.oauth_handler:
            self.oauth_server = GeneralOAuthAuthorizationServer(self.oauth_handler, auth_config)
            
            # Use URL builder for OAuth endpoints
            url_builder = create_url_builder(user_config)
            base_url = url_builder.get_base_url(host=host, port=port)
            
            auth_settings = AuthSettings(
                issuer_url=base_url,
                client_registration_options=ClientRegistrationOptions(
                    enabled=True,
                    valid_scopes=[MCP_SCOPE],
                    default_scopes=[MCP_SCOPE],
                ),
                required_scopes=[MCP_SCOPE],
            )
            logger.info(f"OAuth authentication enabled with provider: {auth_config.get('provider')}")
        else:
            logger.info("OAuth authentication disabled")
        
        # Initialize FastMCP with optional auth settings
        fastmcp_kwargs = {
            "name": "MXCP Server",
            "stateless_http": stateless_http,
            "json_response": json_response,
            "host": host,
            "port": port
        }
        
        logger.info(f"Initializing FastMCP with host={host}, port={port}")
        
        if auth_settings and self.oauth_server:
            fastmcp_kwargs["auth"] = auth_settings
            fastmcp_kwargs["auth_server_provider"] = self.oauth_server
            
        self.mcp = FastMCP(**fastmcp_kwargs)
        
        # Debug: Check what FastMCP actually set for host and port
        logger.info(f"FastMCP settings after initialization: host={self.mcp.settings.host}, port={self.mcp.settings.port}")
        
        # Initialize authentication middleware
        self.auth_middleware = AuthenticationMiddleware(self.oauth_handler, self.oauth_server)
        
        # Register OAuth callback route if authentication is enabled
        if self.oauth_handler and self.oauth_server:
            callback_path = self.oauth_handler.callback_path
            logger.info(f"Registering OAuth callback route: {callback_path}")
            
            # Use custom_route to register the callback
            @self.mcp.custom_route(callback_path, methods=["GET"])
            async def oauth_callback(request):
                return await self.oauth_handler.on_callback(request, self.oauth_server)
            
            # Register Dynamic Client Registration endpoint
            @self.mcp.custom_route("/register", methods=["POST"])
            async def client_registration(request):
                """Handle Dynamic Client Registration requests (RFC 7591)"""
                import json
                from starlette.responses import JSONResponse
                
                try:
                    # Parse client metadata from request body
                    body = await request.body()
                    client_metadata = json.loads(body.decode('utf-8'))
                    
                    # Register the client dynamically
                    registration_response = await self.oauth_server.register_client_dynamically(client_metadata)
                    
                    logger.info(f"Dynamically registered client: {registration_response['client_id']}")
                    
                    return JSONResponse(
                        content=registration_response,
                        status_code=201,
                        headers={"Content-Type": "application/json"}
                    )
                    
                except Exception as e:
                    logger.error(f"Error in client registration: {e}")
                    return JSONResponse(
                        content={"error": "invalid_client_metadata", "error_description": str(e)},
                        status_code=400,
                        headers={"Content-Type": "application/json"}
                    )
            
            # Register OAuth Protected Resource metadata endpoint
            @self.mcp.custom_route("/.well-known/oauth-protected-resource", methods=["GET"])
            async def oauth_protected_resource_metadata(request):
                """Handle OAuth Protected Resource metadata requests (RFC 8693)"""
                from starlette.responses import JSONResponse
                
                # Use URL builder with request context for proper scheme detection
                url_builder = create_url_builder(user_config)
                base_url = url_builder.get_base_url(request)
                
                metadata = {
                    "resource": base_url,
                    "authorization_servers": [base_url],
                    "scopes_supported": [MCP_SCOPE],
                    "bearer_methods_supported": ["header"],
                    "resource_documentation": f"{base_url}/docs"
                }
                
                return JSONResponse(
                    content=metadata,
                    headers={"Content-Type": "application/json"}
                )
        
        self.user_config = user_config
        self.site_config = site_config
        self.profile_name = profile or site_config["profile"]
        self.active_profile = get_active_profile(self.user_config, self.site_config, profile)
        self.loader = EndpointLoader(self.site_config)
        self.readonly = readonly
        
        # Split endpoints into valid and failed
        discovered = self.loader.discover_endpoints()
        self.endpoints = [(path, endpoint) for path, endpoint, error in discovered if error is None]
        self.skipped_endpoints = [{"path": str(path), "error": error} for path, _, error in discovered if error is not None]
        
        # Log discovery results
        logger.info(f"Discovered {len(self.endpoints)} valid endpoints, {len(self.skipped_endpoints)} failed endpoints")
        if self.skipped_endpoints:
            for skipped in self.skipped_endpoints:
                logger.warning(f"Failed to load endpoint {skipped['path']}: {skipped['error']}")
        
        # Determine SQL tools enabled state
        if enable_sql_tools is None:
            # Use site config value, defaulting to True if not specified
            self.enable_sql_tools = site_config.get("sql_tools", {}).get("enabled", True)
        else:
            # Use explicitly provided value
            self.enable_sql_tools = enable_sql_tools
            
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

    def _clean_uri_for_func_name(self, uri: str) -> str:
        """Clean a URI to be used as a function name.
        
        Args:
            uri: The URI to clean
            
        Returns:
            A string suitable for use as a function name
        """
        # Replace protocol:// with _
        name = uri.replace("://", "_")
        # Replace / with _
        name = name.replace("/", "_")
        # Replace {param} with _param
        name = name.replace("{", "_").replace("}", "")
        # Replace any remaining non-alphanumeric chars with _
        name = "".join(c if c.isalnum() else "_" for c in name)
        # Remove consecutive underscores
        name = "_".join(filter(None, name.split("_")))
        return name

    # ---------------------------------------------------------------------------
    # helper that every register_* method will call
    # ---------------------------------------------------------------------------
    def _build_and_register(
        self,
        endpoint_type: EndpointType,
        endpoint_key: str,            # "tool" | "resource" | "prompt"
        endpoint_def: Dict[str, Any],
        decorator,                    # self.mcp.tool() | self.mcp.resource(uri) | self.mcp.prompt()
        log_name: str                 # for nice logging
    ):
        # List of arg names exactly as FastMCP expects
        param_names = [p["name"] for p in endpoint_def.get("parameters", [])]

        # -------------------------------------------------------------------
        # Body of the handler: receives **kwargs with those exact names
        # -------------------------------------------------------------------
        async def _body(**kwargs):
            try:
                # Get the user context from the context variable (set by auth middleware)
                user_context = get_user_context()
                
                logger.info(f"Calling {log_name} {endpoint_def.get('name', endpoint_def.get('uri'))} with: {kwargs}")
                if user_context:
                    logger.info(f"Authenticated user: {user_context.username} (provider: {user_context.provider})")

                # type-convert each param according to the YAML schema --------
                converted = {
                    p["name"]: self._convert_param_type(kwargs[p["name"]], p["type"])
                    for p in endpoint_def.get("parameters", [])
                    if p["name"] in kwargs
                }

                # run through MXCP executor -----------------------------------
                exec_ = EndpointExecutor(
                    endpoint_type,
                    endpoint_def["name"] if endpoint_key != "resource" else endpoint_def["uri"],
                    self.user_config,
                    self.site_config,
                    self.profile_name,
                    readonly=self.readonly
                )
                result = await exec_.execute(converted)
                logger.debug(f"Result: {json.dumps(result, indent=2, default=str)}")
                return result

            except Exception as e:
                logger.error(f"Error executing {log_name} {endpoint_def.get('name', endpoint_def.get('uri'))}:\n{traceback.format_exc()}")
                raise

        # -------------------------------------------------------------------
        # Wrap with authentication middleware
        # -------------------------------------------------------------------
        authenticated_body = self.auth_middleware.require_auth(_body)

        # -------------------------------------------------------------------
        # Dynamically create an *async* function whose signature is
        #   (param1, param2, ...)
        # -------------------------------------------------------------------
        signature = f"({', '.join(param_names)})"
        func_name = endpoint_def.get("name", endpoint_def.get("uri", "handler"))
        if endpoint_key == "resource":
            func_name = self._clean_uri_for_func_name(func_name)
        handler = create_function(signature, authenticated_body, func_name=func_name)

        # Finally register the function with FastMCP -------------------------
        decorator(handler)
        logger.info(f"Registered {log_name}: {func_name}")

    def _register_tool(self, tool_def: Dict[str, Any]):
        """Register a tool endpoint with MCP.
        
        Args:
            tool_def: The tool definition from YAML
        """
        self._build_and_register(
            EndpointType.TOOL,
            "tool",
            tool_def,
            decorator=self.mcp.tool(),
            log_name="tool"
        )

    def _register_resource(self, resource_def: Dict[str, Any]):
        """Register a resource endpoint with MCP.
        
        Args:
            resource_def: The resource definition from YAML
        """
        self._build_and_register(
            EndpointType.RESOURCE,
            "resource",
            resource_def,
            decorator=self.mcp.resource(resource_def["uri"]),
            log_name="resource"
        )

    def _register_prompt(self, prompt_def: Dict[str, Any]):
        """Register a prompt endpoint with MCP.
        
        Args:
            prompt_def: The prompt definition from YAML
        """
        self._build_and_register(
            EndpointType.PROMPT,
            "prompt",
            prompt_def,
            decorator=self.mcp.prompt(),
            log_name="prompt"
        )

    def _register_duckdb_features(self):
        """Register built-in SQL querying and schema exploration tools if enabled."""
        if not self.enable_sql_tools:
            return

        # Register SQL query tool
        @self.mcp.tool(
            name="execute_sql_query",
            description="Execute a SQL query against the DuckDB database and return the results as a list of records"
        )
        @self.auth_middleware.require_auth
        async def execute_sql_query(sql: str) -> List[Dict[str, Any]]:
            """Execute a SQL query against the DuckDB database.
            
            Args:
                sql: The SQL query to execute
                
            Returns:
                List of records as dictionaries
            """
            user_context = get_user_context()
            if user_context:
                logger.info(f"User {user_context.username} executing SQL query")
            
            session = DuckDBSession(self.user_config, self.site_config, self.profile_name, readonly=self.readonly)
            try:
                conn = session.connect()
                result = conn.execute(sql).fetchdf()
                return result.to_dict("records")
            except Exception as e:
                logger.error(f"Error executing SQL query: {e}")
                raise
            finally:
                session.close()

        # Register table list resource
        @self.mcp.tool(
            name="list_tables",
            description="List all tables in the DuckDB database"
        )
        @self.auth_middleware.require_auth
        async def list_tables() -> List[Dict[str, str]]:
            """List all tables in the DuckDB database.
            
            Returns:
                List of tables with their names and types
            """
            user_context = get_user_context()
            if user_context:
                logger.info(f"User {user_context.username} listing tables")
                
            session = DuckDBSession(self.user_config, self.site_config, self.profile_name, readonly=self.readonly)
            try:
                conn = session.connect()
                result = conn.execute("""
                    SELECT 
                        table_name as name,
                        table_type as type
                    FROM information_schema.tables
                    WHERE table_schema = 'main'
                    ORDER BY table_name
                """).fetchdf()
                return result.to_dict("records")
            except Exception as e:
                logger.error(f"Error listing tables: {e}")
                raise
            finally:
                session.close()

        # Register schema resource
        @self.mcp.tool(
            name="get_table_schema",
            description="Get the schema for a specific table in the DuckDB database"
        )
        @self.auth_middleware.require_auth
        async def get_table_schema(table_name: str) -> List[Dict[str, Any]]:
            """Get the schema for a specific table.
            
            Args:
                table_name: Name of the table to get schema for
                
            Returns:
                List of columns with their names and types
            """
            user_context = get_user_context()
            if user_context:
                logger.info(f"User {user_context.username} getting schema for table {table_name}")
                
            session = DuckDBSession(self.user_config, self.site_config, self.profile_name, readonly=self.readonly)
            try:
                conn = session.connect()
                result = conn.execute("""
                    SELECT 
                        column_name as name,
                        data_type as type,
                        is_nullable as nullable
                    FROM information_schema.columns
                    WHERE table_name = ?
                    ORDER BY ordinal_position
                """, [table_name]).fetchdf()
                return result.to_dict("records")
            except Exception as e:
                logger.error(f"Error getting table schema: {e}")
                raise
            finally:
                session.close()

        logger.info("Registered built-in DuckDB features")

    def register_endpoints(self):
        """Register all discovered endpoints with MCP."""
        for path, endpoint_def in self.endpoints:
            try:
                # Validate endpoint before registration
                validation_result = validate_endpoint(str(path), self.user_config, self.site_config, self.active_profile)
                
                if validation_result["status"] != "ok":
                    logger.warning(f"Skipping invalid endpoint {path}: {validation_result.get('message', 'Unknown error')}")
                    self.skipped_endpoints.append({
                        "path": str(path),
                        "error": validation_result.get("message", "Unknown error")
                    })
                    continue

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
                self.skipped_endpoints.append({
                    "path": str(path),
                    "error": str(e)
                })
                continue

        # Register DuckDB features if enabled
        if self.enable_sql_tools:
            self._register_duckdb_features()

        # Report skipped endpoints
        if self.skipped_endpoints:
            logger.warning(f"Skipped {len(self.skipped_endpoints)} invalid endpoints:")
            for skipped in self.skipped_endpoints:
                logger.warning(f"  - {skipped['path']}: {skipped['error']}")

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
            
            # Add debug logging for uvicorn config if using streamable-http
            if transport == "streamable-http":
                logger.info(f"About to start uvicorn with host={self.mcp.settings.host}, port={self.mcp.settings.port}")
            
            # Start server using MCP's built-in run method
            self.mcp.run(transport=transport)
            logger.info("MCP server started successfully.")
        except Exception as e:
            logger.error(f"Error running MCP server: {e}")
            raise 