from typing import Any, Dict, Optional, List, Literal, Union
import json
import logging
import traceback
import time
import threading
import atexit
from pathlib import Path
from mcp.server.fastmcp import FastMCP
from mcp.server.auth.settings import AuthSettings, ClientRegistrationOptions
from mxcp.endpoints.loader import EndpointLoader
from mxcp.endpoints.executor import EndpointExecutor, EndpointType, EndpointResult
from mxcp.config.user_config import UserConfig
from mxcp.config.site_config import SiteConfig, get_active_profile
from mxcp.endpoints.schema import validate_endpoint
from makefun import create_function
from mxcp.engine.duckdb_session import DuckDBSession
from mxcp.auth.providers import create_oauth_handler, GeneralOAuthAuthorizationServer
from mxcp.auth.middleware import AuthenticationMiddleware
from mxcp.auth.context import get_user_context
from mxcp.auth.url_utils import create_url_builder
from mxcp.audit import AuditLogger
from mcp.types import ToolAnnotations
from pydantic import Field, BaseModel, create_model
from typing import Annotated
from starlette.responses import JSONResponse
import re
from mxcp.policies import PolicyEnforcementError
import hashlib

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
        # Initialize basic configuration first
        self.user_config = user_config
        self.site_config = site_config
        self.profile_name = profile or site_config["profile"]
        self.active_profile = get_active_profile(self.user_config, self.site_config, profile)
        
        # Initialize OAuth authentication using profile-specific auth config
        auth_config = self.active_profile.get("auth", {})
        self.oauth_handler = create_oauth_handler(auth_config, host=host, port=port, user_config=user_config)
        self.oauth_server = None
        auth_settings = None
        
        if self.oauth_handler:
            self.oauth_server = GeneralOAuthAuthorizationServer(self.oauth_handler, auth_config, user_config)
            
            # Use URL builder for OAuth endpoints
            url_builder = create_url_builder(user_config)
            base_url = url_builder.get_base_url(host=host, port=port)
            
            # Get authorization configuration
            auth_authorization = auth_config.get("authorization", {})
            required_scopes = auth_authorization.get("required_scopes", [])
            
            logger.info(f"Authorization configured - required scopes: {required_scopes or 'none (authentication only)'}")
            
            auth_settings = AuthSettings(
                issuer_url=base_url,
                client_registration_options=ClientRegistrationOptions(
                    enabled=True,
                    # Accept any scope during client registration
                    valid_scopes=None,  # Always None = accept any scope
                    # Set default scopes to match required scopes so new clients get the right permissions
                    default_scopes=required_scopes if required_scopes else None,
                ),
                # Use the configured required scopes (empty list = no scopes required)
                required_scopes=required_scopes if required_scopes else None,
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
        logger.info(f"Authentication middleware initialized with oauth_handler: {self.oauth_handler}, oauth_server: {self.oauth_server}")
        
        # Register OAuth callback route if authentication is enabled
        if self.oauth_handler and self.oauth_server:
            callback_path = self.oauth_handler.callback_path
            logger.info(f"Registering OAuth callback route: {callback_path}")
            
            # Use custom_route to register the callback
            @self.mcp.custom_route(callback_path, methods=["GET"])
            async def oauth_callback(request):
                return await self.oauth_handler.on_callback(request, self.oauth_server)
            
            # Register OAuth Protected Resource metadata endpoint
            @self.mcp.custom_route("/.well-known/oauth-protected-resource", methods=["GET"])
            async def oauth_protected_resource_metadata(request):
                """Handle OAuth Protected Resource metadata requests (RFC 8693)"""
                from starlette.responses import JSONResponse
                
                # Use URL builder with request context for proper scheme detection
                url_builder = create_url_builder(user_config)
                base_url = url_builder.get_base_url(request)
                
                # Get supported scopes from configuration
                auth_authorization = auth_config.get("authorization", {})
                supported_scopes = auth_authorization.get("required_scopes", [])
                
                metadata = {
                    "resource": base_url,
                    "authorization_servers": [base_url],
                    "scopes_supported": supported_scopes,
                    "bearer_methods_supported": ["header"],
                    "resource_documentation": f"{base_url}/docs"
                }
                
                return JSONResponse(
                    content=metadata,
                    headers={"Content-Type": "application/json"}
                )
        
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
            
        # Cache for dynamically created models
        self._model_cache = {}

        # Initialize audit logger if enabled
        profile_config = self.site_config["profiles"][self.profile_name]
        audit_config = profile_config.get("audit", {})
        if audit_config.get("enabled", False):
            self.audit_logger = AuditLogger(
                log_path=Path(audit_config["path"]),
                enabled=True
            )
        else:
            self.audit_logger = None
        
        # Store transport mode (will be set during run())
        self.transport_mode = None
        
        # Create shared DuckDB session and lock for thread-safety
        logger.info("Creating shared DuckDB session for server...")
        self.db_session = DuckDBSession(user_config, site_config, profile, readonly)
        self.db_lock = threading.Lock()
        logger.info("Shared DuckDB session created successfully")
        
        # Register cleanup handler for atexit as a safety net
        atexit.register(self.shutdown)
        
        # Track if we've already shut down to avoid double cleanup
        self._shutdown_called = False

    def shutdown(self):
        """Shutdown the server gracefully."""
        # Prevent double shutdown
        if self._shutdown_called:
            return
        self._shutdown_called = True
        
        logger.info("Shutting down MXCP server...")
        
        try:
            # Close OAuth server persistence first
            if self.oauth_server:
                try:
                    import asyncio
                    asyncio.run(self.oauth_server.close())
                    logger.info("Closed OAuth server persistence")
                except Exception as e:
                    logger.error(f"Error closing OAuth server: {e}")
            
            # Close DuckDB session
            if self.db_session:
                try:
                    self.db_session.close()
                    logger.info("Closed DuckDB session and connection")
                except Exception as e:
                    logger.error(f"Error closing DuckDB session: {e}")
            
            # Shutdown audit logger if initialized
            if self.audit_logger:
                try:
                    self.audit_logger.shutdown()
                    logger.info("Closed audit logger")
                except Exception as e:
                    logger.error(f"Error closing audit logger: {e}")
                    
        except Exception as e:
            logger.error(f"Error during shutdown: {e}")
        finally:
            logger.info("MXCP server shutdown complete")

    def _sanitize_model_name(self, name: str) -> str:
        """Sanitize a name to be a valid Python class name."""
        # Replace non-alphanumeric characters with underscores
        name = re.sub(r'[^a-zA-Z0-9_]', '_', name)
        # Ensure it starts with a letter or underscore
        if name and name[0].isdigit():
            name = f"_{name}"
        # Capitalize first letter for class name convention
        return name.title().replace('_', '')

    def _create_pydantic_model_from_schema(self, schema_def: Dict[str, Any], model_name: str, endpoint_type: Optional[EndpointType] = None) -> Any:
        """Create a Pydantic model from a JSON Schema definition.
        
        Args:
            schema_def: JSON Schema definition
            model_name: Name for the generated model
            endpoint_type: Type of endpoint (affects whether parameters are Optional)
            
        Returns:
            Pydantic model class or type annotation
        """
        # Cache key for this schema (include endpoint_type to avoid conflicts)
        cache_key = f"{model_name}_{hash(json.dumps(schema_def, sort_keys=True))}_{endpoint_type}"
        if cache_key in self._model_cache:
            return self._model_cache[cache_key]
        
        json_type = schema_def.get("type", "string")
        
        # Determine if parameters should be Optional (tools/prompts) or required (resources)
        make_optional = endpoint_type in (EndpointType.TOOL, EndpointType.PROMPT)
        
        # Handle primitive types
        if json_type == "string":
            # Handle enums
            if "enum" in schema_def:
                enum_values = schema_def["enum"]
                if all(isinstance(v, str) for v in enum_values):
                    if make_optional:
                        result = Optional[Literal[tuple(enum_values)]]
                    else:
                        result = Literal[tuple(enum_values)]
                    self._model_cache[cache_key] = result
                    return result
            
            # Create Field with constraints
            field_kwargs = self._extract_field_constraints(schema_def)
            if field_kwargs:
                if make_optional:
                    result = Annotated[Optional[str], Field(**field_kwargs)]
                else:
                    result = Annotated[str, Field(**field_kwargs)]
            else:
                if make_optional:
                    result = Optional[str]
                else:
                    result = str
            self._model_cache[cache_key] = result
            return result
            
        elif json_type == "integer":
            field_kwargs = self._extract_field_constraints(schema_def)
            if field_kwargs:
                if make_optional:
                    result = Annotated[Optional[int], Field(**field_kwargs)]
                else:
                    result = Annotated[int, Field(**field_kwargs)]
            else:
                if make_optional:
                    result = Optional[int]
                else:
                    result = int
            self._model_cache[cache_key] = result
            return result
            
        elif json_type == "number":
            field_kwargs = self._extract_field_constraints(schema_def)
            if field_kwargs:
                if make_optional:
                    result = Annotated[Optional[float], Field(**field_kwargs)]
                else:
                    result = Annotated[float, Field(**field_kwargs)]
            else:
                if make_optional:
                    result = Optional[float]
                else:
                    result = float
            self._model_cache[cache_key] = result
            return result
            
        elif json_type == "boolean":
            field_kwargs = self._extract_field_constraints(schema_def)
            if field_kwargs:
                if make_optional:
                    result = Annotated[Optional[bool], Field(**field_kwargs)]
                else:
                    result = Annotated[bool, Field(**field_kwargs)]
            else:
                if make_optional:
                    result = Optional[bool]
                else:
                    result = bool
            self._model_cache[cache_key] = result
            return result
            
        elif json_type == "array":
            items_schema = schema_def.get("items", {"type": "string"})
            item_type = self._create_pydantic_model_from_schema(items_schema, f"{model_name}Item", endpoint_type)
            
            field_kwargs = self._extract_field_constraints(schema_def)
            if field_kwargs:
                result = Annotated[List[item_type], Field(**field_kwargs)]
            else:
                result = List[item_type]
            self._model_cache[cache_key] = result
            return result
            
        elif json_type == "object":
            # Handle complex objects with properties
            properties = schema_def.get("properties", {})
            required_fields = set(schema_def.get("required", []))
            additional_properties = schema_def.get("additionalProperties", True)
            
            if not properties:
                # Generic object
                field_kwargs = self._extract_field_constraints(schema_def)
                if field_kwargs:
                    result = Annotated[Dict[str, Any], Field(**field_kwargs)]
                else:
                    result = Dict[str, Any]
                self._model_cache[cache_key] = result
                return result
            
            # Create fields for the model
            model_fields = {}
            for prop_name, prop_schema in properties.items():
                prop_type = self._create_pydantic_model_from_schema(
                    prop_schema, 
                    f"{model_name}{self._sanitize_model_name(prop_name)}",
                    endpoint_type
                )
                
                # Extract field constraints for this property
                field_kwargs = self._extract_field_constraints(prop_schema)
                
                # Handle required vs optional fields
                if prop_name in required_fields:
                    if field_kwargs:
                        model_fields[prop_name] = (prop_type, Field(**field_kwargs))
                    else:
                        model_fields[prop_name] = (prop_type, ...)
                else:
                    # Optional field
                    if field_kwargs:
                        model_fields[prop_name] = (Optional[prop_type], Field(None, **field_kwargs))
                    else:
                        model_fields[prop_name] = (Optional[prop_type], None)
            
            # Create the model with proper configuration
            from pydantic import ConfigDict
            model_config = ConfigDict(extra="allow" if additional_properties else "forbid")
            
            result = create_model(
                self._sanitize_model_name(model_name),
                **model_fields,
                __config__=model_config
            )
            
            self._model_cache[cache_key] = result
            return result
        
        # Fallback to Any for unknown types
        result = Any
        self._model_cache[cache_key] = result
        return result

    def _extract_field_constraints(self, schema_def: Dict[str, Any]) -> Dict[str, Any]:
        """Extract Pydantic Field constraints from JSON Schema definition."""
        field_kwargs = {}
        
        # Description
        if "description" in schema_def:
            field_kwargs["description"] = schema_def["description"]
        
        # Default value
        if "default" in schema_def:
            field_kwargs["default"] = schema_def["default"]
        
        # Examples
        if "examples" in schema_def and schema_def["examples"]:
            field_kwargs["examples"] = schema_def["examples"]
        
        # String constraints
        if "minLength" in schema_def:
            field_kwargs["min_length"] = schema_def["minLength"]
        if "maxLength" in schema_def:
            field_kwargs["max_length"] = schema_def["maxLength"]
        if "pattern" in schema_def:
            field_kwargs["pattern"] = schema_def["pattern"]
        
        # Numeric constraints
        if "minimum" in schema_def:
            field_kwargs["ge"] = schema_def["minimum"]
        if "maximum" in schema_def:
            field_kwargs["le"] = schema_def["maximum"]
        if "exclusiveMinimum" in schema_def:
            field_kwargs["gt"] = schema_def["exclusiveMinimum"]
        if "exclusiveMaximum" in schema_def:
            field_kwargs["lt"] = schema_def["exclusiveMaximum"]
        if "multipleOf" in schema_def:
            field_kwargs["multiple_of"] = schema_def["multipleOf"]
        
        # Array constraints
        if "minItems" in schema_def:
            field_kwargs["min_length"] = schema_def["minItems"]
        if "maxItems" in schema_def:
            field_kwargs["max_length"] = schema_def["maxItems"]
        
        return field_kwargs

    def _create_pydantic_field_annotation(self, param_def: Dict[str, Any], endpoint_type: Optional[EndpointType] = None) -> Any:
        """Create a Pydantic type annotation from parameter definition.
        
        Args:
            param_def: Parameter definition from endpoint YAML
            endpoint_type: Type of endpoint (affects whether parameters are Optional)
            
        Returns:
            Pydantic type annotation (class or Annotated type)
        """
        param_name = param_def.get("name", "param")
        return self._create_pydantic_model_from_schema(param_def, param_name, endpoint_type)

    def _json_schema_to_python_type(self, param_def: Dict[str, Any], endpoint_type: Optional[EndpointType] = None) -> Any:
        """Convert JSON Schema type to Python type annotation.
        
        Args:
            param_def: Parameter definition from endpoint YAML
            endpoint_type: Type of endpoint (affects whether parameters are Optional)
            
        Returns:
            Python type annotation
        """
        return self._create_pydantic_field_annotation(param_def, endpoint_type)

    def _create_tool_annotations(self, tool_def: Dict[str, Any]) -> Optional[ToolAnnotations]:
        """Create ToolAnnotations from tool definition.
        
        Args:
            tool_def: Tool definition from endpoint YAML
            
        Returns:
            ToolAnnotations object if annotations are present, None otherwise
        """
        annotations_data = tool_def.get("annotations", {})
        if not annotations_data:
            return None
            
        return ToolAnnotations(
            title=annotations_data.get("title"),
            readOnlyHint=annotations_data.get("readOnlyHint"),
            destructiveHint=annotations_data.get("destructiveHint"),
            idempotentHint=annotations_data.get("idempotentHint"),
            openWorldHint=annotations_data.get("openWorldHint")
        )
            
    def _convert_param_type(self, value: Any, param_type: str) -> Any:
        """Convert parameter value to the correct type based on JSON Schema type.
        
        Args:
            value: The parameter value to convert
            param_type: The JSON Schema type to convert to
            
        Returns:
            The converted value
        """
        try:
            if value is None:
                return None
            elif param_type == "string":
                return str(value)
            elif param_type == "integer":
                return int(value)
            elif param_type == "number":
                return float(value)
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

    def _sanitize_func_name(self, name: str) -> str:
        """Sanitize a name to be used as a Python function name.
        
        Args:
            name: The name to sanitize
            
        Returns:
            A string suitable for use as a Python function name
        """
        # Replace any non-alphanumeric chars with _
        name = "".join(c if c.isalnum() else "_" for c in name)
        # Remove consecutive underscores
        name = "_".join(filter(None, name.split("_")))
        # Ensure it starts with a letter or underscore
        if not name[0].isalpha() and name[0] != '_':
            name = '_' + name
        return name

    def mcp_name_to_py(self, name: str) -> str:
        """Convert MCP endpoint name to a valid Python function name.
        
        Example: 'get-user' → 'mcp_get_user__abc123'
        
        Args:
            name: The original MCP endpoint name
            
        Returns:
            A valid Python function name with hash suffix
        """
        base = re.sub(r"[^a-zA-Z0-9_]", "_", name)
        suffix = hashlib.sha1(name.encode()).hexdigest()[:6]
        return f"mcp_{base}__{suffix}"

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
        # Get parameter definitions
        parameters = endpoint_def.get("parameters", [])
        
        # Create function signature with proper Pydantic type annotations
        param_annotations = {}
        param_signatures = []
        for param in parameters:
            param_name = param["name"]
            param_type = self._json_schema_to_python_type(param, endpoint_type)
            param_annotations[param_name] = param_type
            # Create string representation for makefun
            param_signatures.append(f"{param_name}")
        
        signature = f"({', '.join(param_signatures)})"

        # -------------------------------------------------------------------
        # Body of the handler: receives **kwargs with those exact names
        # -------------------------------------------------------------------
        async def _body(**kwargs):
            start_time = time.time()
            status = "success"
            error_msg = None
            exec_ = None  # Initialize to prevent NameError in finally block
            
            try:
                # Get the user context from the context variable (set by auth middleware)
                user_context = get_user_context()
                
                logger.info(f"Calling {log_name} {endpoint_def.get('name', endpoint_def.get('uri'))} with: {kwargs}")
                if user_context:
                    logger.info(f"Authenticated user: {user_context.username} (provider: {user_context.provider})")

                # type-convert each param according to the YAML schema --------
                converted = {
                    p["name"]: self._convert_param_type(kwargs[p["name"]], p["type"])
                    for p in parameters
                    if p["name"] in kwargs
                }

                # run through MXCP executor -----------------------------------
                exec_ = EndpointExecutor(
                    endpoint_type,
                    endpoint_def["name"] if endpoint_key != "resource" else endpoint_def["uri"],
                    self.user_config,
                    self.site_config,
                    self.db_session,
                    self.profile_name,
                    db_lock=self.db_lock
                )
                result = await exec_.execute(converted, user_context=user_context)
                logger.debug(f"Result: {json.dumps(result, indent=2, default=str)}")
                return result

            except Exception as e:
                status = "error"
                error_msg = str(e)
                logger.error(f"Error executing {log_name} {endpoint_def.get('name', endpoint_def.get('uri'))}:\n{traceback.format_exc()}")
                raise
            finally:
                # Calculate duration
                duration_ms = int((time.time() - start_time) * 1000)
                
                # Determine caller type based on transport
                # Check if we're in HTTP mode by looking for transport_mode
                if hasattr(self, 'transport_mode') and self.transport_mode:
                    if self.transport_mode == "stdio":
                        caller = "stdio"
                    else:
                        caller = "http"  # streamable-http or other HTTP transports
                else:
                    # Fallback to http if transport mode not set
                    caller = "http"
                
                # Get policy decision from executor if available
                policy_decision = "n/a"
                policy_reason = None
                if exec_ is not None and hasattr(exec_, 'last_policy_decision'):
                    policy_decision = exec_.last_policy_decision
                if exec_ is not None and hasattr(exec_, 'last_policy_reason'):
                    policy_reason = exec_.last_policy_reason
                
                # Log the audit event
                if self.audit_logger:
                    self.audit_logger.log_event(
                        caller=caller,
                        event_type=endpoint_key,  # "tool", "resource", or "prompt"
                        name=endpoint_def.get('name', endpoint_def.get('uri', 'unknown')),
                        input_params=kwargs,
                        duration_ms=duration_ms,
                        policy_decision=policy_decision,
                        reason=policy_reason,
                        status=status,
                        error=error_msg,
                        endpoint_def=endpoint_def  # Pass the endpoint definition for schema-based redaction
                    )

        # -------------------------------------------------------------------
        # Wrap with authentication middleware
        # -------------------------------------------------------------------
        authenticated_body = self.auth_middleware.require_auth(_body)

        # -------------------------------------------------------------------
        # Create function with proper signature and annotations using makefun
        # -------------------------------------------------------------------
        original_name = endpoint_def.get("name", endpoint_def.get("uri", "handler"))
        func_name = self.mcp_name_to_py(original_name)
        
        # Create the function with proper signature
        handler = create_function(signature, authenticated_body, func_name=func_name)
        
        # Set the annotations for Pydantic introspection
        handler.__annotations__ = param_annotations

        # Finally register the function with FastMCP -------------------------
        # Use original name for FastMCP registration
        decorator(handler)
        logger.info(f"Registered {log_name}: {original_name} (function: {func_name})")

    def _register_tool(self, tool_def: Dict[str, Any]):
        """Register a tool endpoint with MCP.
        
        Args:
            tool_def: The tool definition from YAML
        """
        # Create tool annotations from the definition
        annotations = self._create_tool_annotations(tool_def)
        
        self._build_and_register(
            EndpointType.TOOL,
            "tool",
            tool_def,
            decorator=self.mcp.tool(
                name=tool_def.get("name"),
                description=tool_def.get("description"),
                annotations=annotations
            ),
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
            decorator=self.mcp.resource(
                resource_def["uri"],
                name=resource_def.get("name"),
                description=resource_def.get("description"),
                mime_type=resource_def.get("mime_type")
            ),
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
            decorator=self.mcp.prompt(
                name=prompt_def.get("name"),
                description=prompt_def.get("description")
            ),
            log_name="prompt"
        )

    def _register_duckdb_features(self):
        """Register built-in SQL querying and schema exploration tools if enabled."""
        if not self.enable_sql_tools:
            return

        # Register SQL query tool with proper metadata
        @self.mcp.tool(
            name="execute_sql_query",
            description="Execute a SQL query against the DuckDB database and return the results as a list of records",
            annotations=ToolAnnotations(
                title="SQL Query Executor",
                readOnlyHint=False,  # SQL can modify data
                destructiveHint=True,  # SQL can delete/update data
                idempotentHint=False,  # SQL queries may not be idempotent
                openWorldHint=False   # Operates on closed database
            )
        )
        @self.auth_middleware.require_auth
        async def execute_sql_query(sql: str) -> List[Dict[str, Any]]:
            """Execute a SQL query against the DuckDB database.
            
            Args:
                sql: The SQL query to execute
                
            Returns:
                List of records as dictionaries
            """
            start_time = time.time()
            status = "success"
            error_msg = None
            
            try:
                user_context = get_user_context()
                if user_context:
                    logger.info(f"User {user_context.username} executing SQL query")
                
                # Use shared connection with thread-safety
                with self.db_lock:
                    result = self.db_session.execute_query_to_dict(sql)
                    return result
            except Exception as e:
                status = "error"
                error_msg = str(e)
                logger.error(f"Error executing SQL query: {e}")
                raise
            finally:
                # Log audit event
                duration_ms = int((time.time() - start_time) * 1000)
                if self.audit_logger:
                    # Determine caller type
                    caller = "stdio" if self.transport_mode == "stdio" else "http"
                    self.audit_logger.log_event(
                        caller=caller,
                        event_type="tool",
                        name="execute_sql_query",
                        input_params={"sql": sql},
                        duration_ms=duration_ms,
                        policy_decision="n/a",
                        reason=None,
                        status=status,
                        error=error_msg
                    )

        # Register table list tool with proper metadata
        @self.mcp.tool(
            name="list_tables",
            description="List all tables in the DuckDB database",
            annotations=ToolAnnotations(
                title="Database Table Lister",
                readOnlyHint=True,   # Only reads metadata
                destructiveHint=False,  # Cannot modify data
                idempotentHint=True,    # Always returns same result
                openWorldHint=False     # Operates on closed database
            )
        )
        @self.auth_middleware.require_auth
        async def list_tables() -> List[Dict[str, str]]:
            """List all tables in the DuckDB database.
            
            Returns:
                List of tables with their names and types
            """
            start_time = time.time()
            status = "success"
            error_msg = None
            
            try:
                user_context = get_user_context()
                if user_context:
                    logger.info(f"User {user_context.username} listing tables")
                    
                # Use shared connection with thread-safety
                with self.db_lock:
                    return self.db_session.execute_query_to_dict("""
                        SELECT 
                            table_name as name,
                            table_type as type
                        FROM information_schema.tables
                        WHERE table_schema = 'main'
                        ORDER BY table_name
                    """)
            except Exception as e:
                status = "error"
                error_msg = str(e)
                logger.error(f"Error listing tables: {e}")
                raise
            finally:
                # Log audit event
                duration_ms = int((time.time() - start_time) * 1000)
                if self.audit_logger:
                    # Determine caller type
                    caller = "stdio" if self.transport_mode == "stdio" else "http"
                    self.audit_logger.log_event(
                        caller=caller,
                        event_type="tool",
                        name="list_tables",
                        input_params={},
                        duration_ms=duration_ms,
                        policy_decision="n/a",
                        reason=None,
                        status=status,
                        error=error_msg
                    )

        # Register schema tool with proper metadata
        @self.mcp.tool(
            name="get_table_schema",
            description="Get the schema for a specific table in the DuckDB database",
            annotations=ToolAnnotations(
                title="Table Schema Inspector",
                readOnlyHint=True,   # Only reads metadata
                destructiveHint=False,  # Cannot modify data
                idempotentHint=True,    # Always returns same result for same table
                openWorldHint=False     # Operates on closed database
            )
        )
        @self.auth_middleware.require_auth
        async def get_table_schema(table_name: str) -> List[Dict[str, Any]]:
            """Get the schema for a specific table.
            
            Args:
                table_name: Name of the table to get schema for
                
            Returns:
                List of columns with their names and types
            """
            start_time = time.time()
            status = "success"
            error_msg = None
            
            try:
                user_context = get_user_context()
                if user_context:
                    logger.info(f"User {user_context.username} getting schema for table {table_name}")
                    
                # Use shared connection with thread-safety
                with self.db_lock:
                    return self.db_session.execute_query_to_dict("""
                        SELECT 
                            column_name as name,
                            data_type as type,
                            is_nullable as nullable
                        FROM information_schema.columns
                        WHERE table_name = $table_name
                        ORDER BY ordinal_position
                    """, {"table_name": table_name})
            except Exception as e:
                status = "error"
                error_msg = str(e)
                logger.error(f"Error getting table schema: {e}")
                raise
            finally:
                # Log audit event
                duration_ms = int((time.time() - start_time) * 1000)
                if self.audit_logger:
                    # Determine caller type
                    caller = "stdio" if self.transport_mode == "stdio" else "http"
                    self.audit_logger.log_event(
                        caller=caller,
                        event_type="tool",
                        name="get_table_schema",
                        input_params={"table_name": table_name},
                        duration_ms=duration_ms,
                        policy_decision="n/a",
                        reason=None,
                        status=status,
                        error=error_msg
                    )

        logger.info("Registered built-in DuckDB features")

    def register_endpoints(self):
        """Register all discovered endpoints with MCP."""
        for path, endpoint_def in self.endpoints:
            try:
                # Validate endpoint before registration using shared session
                validation_result = validate_endpoint(str(path), self.user_config, self.site_config, self.active_profile, self.db_session)
                
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

    async def _initialize_oauth_server(self):
        """Initialize OAuth server persistence if enabled."""
        if self.oauth_server:
            try:
                await self.oauth_server.initialize()
                logger.info("OAuth server initialized successfully")
            except Exception as e:
                logger.error(f"Failed to initialize OAuth server: {e}")
                raise



    def run(self, transport: str = "streamable-http"):
        """Run the MCP server.
        
        Args:
            transport: The transport to use ("streamable-http" or "stdio")
        """
        try:
            logger.info("Starting MCP server...")
            # Store transport mode for use in handlers
            self.transport_mode = transport
            
            # Register all endpoints
            self.register_endpoints()
            logger.info("Endpoints registered successfully.")
            
            # Add debug logging for uvicorn config if using streamable-http
            if transport == "streamable-http":
                logger.info(f"About to start uvicorn with host={self.mcp.settings.host}, port={self.mcp.settings.port}")
            
            # Initialize OAuth server before starting FastMCP
            if self.oauth_server:
                import asyncio
                try:
                    asyncio.run(self._initialize_oauth_server())
                    logger.info("OAuth server initialized successfully")
                except Exception as e:
                    logger.error(f"Failed to initialize OAuth server: {e}")
                    # Continue anyway - server can still function without persistence
            
            # Start server using MCP's built-in run method
            self.mcp.run(transport=transport)
            logger.info("MCP server started successfully.")
        except Exception as e:
            logger.error(f"Error running MCP server: {e}")
            raise 