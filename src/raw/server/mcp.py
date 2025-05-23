from typing import Any, Dict, Optional, List
import json
import logging
import traceback
from mcp.server.fastmcp import FastMCP
from raw.endpoints.loader import EndpointLoader
from raw.endpoints.executor import EndpointExecutor, EndpointType
from raw.config.user_config import UserConfig
from raw.config.site_config import SiteConfig, get_active_profile
from raw.endpoints.schema import validate_endpoint
from makefun import create_function
from raw.engine.duckdb_session import DuckDBSession

logger = logging.getLogger(__name__)

class RAWMCP:
    """RAW MCP Server implementation that bridges RAW endpoints with MCP protocol."""
    
    def __init__(self, user_config: UserConfig, site_config: SiteConfig, profile: Optional[str] = None, stateless_http: bool = False, json_response: bool = False, host: str = "localhost", port: int = 8000, enable_sql_tools: Optional[bool] = None):
        """Initialize the RAW MCP server.
        
        Args:
            user_config: The user configuration loaded from ~/.raw/config.yml
            site_config: The site configuration loaded from raw-site.yml
            profile: Optional profile name to use for configuration
            stateless_http: Whether to run in stateless HTTP mode
            json_response: Whether to use JSON responses instead of SSE
            host: The host to bind to
            port: The port to bind to
            enable_sql_tools: Whether to enable built-in SQL querying and schema exploration tools.
                            If None, uses the value from site_config.sql_tools.enabled (defaults to True)
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
        self.profile_name = profile or site_config["profile"]
        self.active_profile = get_active_profile(self.user_config, self.site_config, profile)
        self.loader = EndpointLoader(self.site_config)
        self.endpoints = self.loader.discover_endpoints()
        self.skipped_endpoints: List[Dict[str, Any]] = []
        
        # Determine SQL tools enabled state
        if enable_sql_tools is None:
            # Use site config value, defaulting to True if not specified
            self.enable_sql_tools = site_config.get("sql_tools", {}).get("enabled", True)
        else:
            # Use explicitly provided value
            self.enable_sql_tools = enable_sql_tools
            
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
                logger.info(f"Calling {log_name} {endpoint_def.get('name', endpoint_def.get('uri'))} with: {kwargs}")

                # type-convert each param according to the YAML schema --------
                converted = {
                    p["name"]: self._convert_param_type(kwargs[p["name"]], p["type"])
                    for p in endpoint_def.get("parameters", [])
                    if p["name"] in kwargs
                }

                # run through RAW executor -----------------------------------
                exec_ = EndpointExecutor(
                    endpoint_type,
                    endpoint_def["name"] if endpoint_key != "resource" else endpoint_def["uri"],
                    self.user_config,
                    self.site_config,
                    self.profile_name,
                )
                result = await exec_.execute(converted)
                logger.debug(f"Result: {json.dumps(result, indent=2)}")
                return result

            except Exception as e:
                logger.error(f"Error executing {log_name} {endpoint_def.get('name', endpoint_def.get('uri'))}:\n{traceback.format_exc()}")
                raise

        # -------------------------------------------------------------------
        # Dynamically create an *async* function whose signature is
        #   (param1, param2, ...)
        # -------------------------------------------------------------------
        signature = f"({', '.join(param_names)})"
        func_name = endpoint_def.get("name", endpoint_def.get("uri", "handler"))
        if endpoint_key == "resource":
            func_name = self._clean_uri_for_func_name(func_name)
        handler = create_function(signature, _body, func_name=func_name)

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
        async def execute_sql_query(sql: str) -> List[Dict[str, Any]]:
            """Execute a SQL query against the DuckDB database.
            
            Args:
                sql: The SQL query to execute
                
            Returns:
                List of records as dictionaries
            """
            session = DuckDBSession(self.user_config, self.site_config, self.profile_name)
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
        async def list_tables() -> List[Dict[str, str]]:
            """List all tables in the DuckDB database.
            
            Returns:
                List of tables with their names and types
            """
            session = DuckDBSession(self.user_config, self.site_config, self.profile_name)
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
        async def get_table_schema(table_name: str) -> List[Dict[str, Any]]:
            """Get the schema for a specific table.
            
            Args:
                table_name: Name of the table to get schema for
                
            Returns:
                List of columns with their names and types
            """
            session = DuckDBSession(self.user_config, self.site_config, self.profile_name)
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
            
            # Start server using MCP's built-in run method
            self.mcp.run(transport=transport)
            logger.info("MCP server started successfully.")
        except Exception as e:
            logger.error(f"Error running MCP server: {e}")
            raise 