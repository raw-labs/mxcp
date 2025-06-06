import duckdb
from typing import Dict, Any, Optional
from mxcp.config.types import SiteConfig, UserConfig
from mxcp.engine.secret_injection import inject_secrets
from mxcp.engine.extension_loader import load_extensions
from mxcp.engine.plugin_loader import load_plugins
from mxcp.plugins import MXCPBasePlugin
from mxcp.auth.context import get_user_context
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

class DuckDBSession:
    def __init__(self, user_config: UserConfig, site_config: SiteConfig, profile: Optional[str] = None, readonly: Optional[bool] = None):
        if profile is not None and not isinstance(profile, str):
            raise ValueError(f"profile argument must be a string, not {type(profile)}: {profile}")
        self.conn = None
        self.user_config = user_config
        self.site_config = site_config
        self.profile = profile
        self.readonly = readonly
        self.plugins: Dict[str, MXCPBasePlugin] = {}
        self._initialized = False  # Track whether session has been fully initialized
        
    def __enter__(self):
        """Context manager entry"""
        self.connect()
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - ensure connection is closed"""
        self.close()
        
    def __del__(self):
        """Destructor - ensure connection is closed if object is garbage collected"""
        try:
            self.close()
        except Exception:
            # Ignore errors during cleanup in destructor
            pass
        
    def _get_project_profile(self) -> tuple[str, str]:
        """Get the current project and profile from site config"""
        if not self.site_config:
            raise ValueError("Site config not loaded")
            
        project = self.site_config["project"]
        profile_name = self.profile or self.site_config["profile"]
        
        logger.debug(f"Getting project/profile: {project}/{profile_name}")
        return project, profile_name
        
    def _get_profile_config(self) -> Dict[str, Any]:
        """Get the current profile's config from user config"""
        if not self.user_config:
            raise ValueError("User config not loaded")
            
        project, profile = self._get_project_profile()
        project_config = self.user_config["projects"].get(project)
        if not project_config:
            raise ValueError(f"Project '{project}' not found in user config")
            
        profile_config = project_config["profiles"].get(profile)
        if not profile_config:
            raise ValueError(f"Profile '{profile}' not found in project '{project}'")
            
        return profile_config
        
    def connect(self) -> duckdb.DuckDBPyConnection:
        """Establish DuckDB connection and set up the session"""        
        # If already initialized, just return the existing connection
        if self._initialized and self.conn:
            return self.conn
        
        # Connect to DuckDB using path from config
        profile = self.profile or self.site_config["profile"]
        db_path = self.site_config["profiles"][profile]["duckdb"]["path"]
        
        # Determine if connection should be readonly
        # CLI flag takes precedence over config file setting
        readonly = self.readonly
        if readonly is None:
            readonly = self.site_config["profiles"][profile]["duckdb"].get("readonly", False)
            
        # Handle read-only mode when database file doesn't exist
        if readonly and db_path != ":memory:":
            db_file = Path(db_path)
            if not db_file.exists():
                logger.info(f"Database file {db_path} doesn't exist. Creating it first before opening in read-only mode.")
                # Create the database file first
                temp_conn = duckdb.connect(db_path)
                temp_conn.close()
                logger.info(f"Created database file {db_path}")
            
        # Open connection with readonly flag if specified
        if readonly:
            self.conn = duckdb.connect(db_path, read_only=True)
            logger.info("Opened DuckDB connection in read-only mode")
        else:
            self.conn = duckdb.connect(db_path)
            
        # Load DuckDB extensions from config
        extensions = self.site_config["extensions"]
        load_extensions(self.conn, extensions)
            
        # Inject secrets using the active profile
        project, profile_name = self._get_project_profile()
        logger.debug(f"Using project: {project}, profile: {profile_name}")
        inject_secrets(self.conn, self.site_config, self.user_config, profile_name)
        
        # Load plugins
        user_context = get_user_context()
        self.plugins = load_plugins(self.site_config, self.user_config, project, profile_name, self.conn, user_context)
        
        # Create user token UDFs if user is authenticated
        self._create_user_token_udfs()
        
        # Mark as initialized to prevent re-initialization
        self._initialized = True
        
        return self.conn
        
    def _create_user_token_udfs(self):
        """Create UDFs for accessing user tokens if authentication is enabled."""
        user_context = get_user_context()
        if not user_context:
            logger.debug("No user context available, skipping token UDF creation")
            return
            
        logger.info(f"Creating user token UDFs for {user_context.username}")
        
        def get_user_external_token() -> str:
            """Return the current user's OAuth provider token (e.g., GitHub token)."""
            if user_context and user_context.external_token:
                return user_context.external_token
            return ""
            
        def get_username() -> str:
            """Return the current user's username."""
            if user_context:
                return user_context.username
            return ""
            
        def get_user_provider() -> str:
            """Return the current user's OAuth provider (e.g., 'github', 'atlassian')."""
            if user_context:
                return user_context.provider
            return ""
            
        def get_user_email() -> str:
            """Return the current user's email address."""
            if user_context and user_context.email:
                return user_context.email
            return ""
        
        # Register the UDFs with DuckDB
        if self.conn:
            self.conn.create_function("get_user_external_token", get_user_external_token, [], "VARCHAR")
            self.conn.create_function("get_username", get_username, [], "VARCHAR")
            self.conn.create_function("get_user_provider", get_user_provider, [], "VARCHAR")
            self.conn.create_function("get_user_email", get_user_email, [], "VARCHAR")
            logger.info("Created user token UDFs: get_user_external_token(), get_username(), get_user_provider(), get_user_email()")
        
    def close(self):
        """Close the DuckDB connection"""
        if self.conn:
            try:
                self.conn.close()
                logger.debug("DuckDB connection closed successfully")
            except Exception as e:
                logger.error(f"Error closing DuckDB connection: {e}")
            finally:
                self.conn = None
                self._initialized = False  # Reset initialization flag