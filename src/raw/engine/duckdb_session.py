import duckdb
from typing import Dict, Any, Optional
from raw.config.types import SiteConfig, UserConfig
from raw.engine.secret_injection import inject_secrets
from raw.engine.extension_loader import load_extensions
from raw.engine.python_bootstrap import run_init_script
import logging

logger = logging.getLogger(__name__)

class DuckDBSession:
    def __init__(self, user_config: UserConfig, site_config: SiteConfig, profile: Optional[str] = None):
        if profile is not None and not isinstance(profile, str):
            raise ValueError(f"profile argument must be a string, not {type(profile)}: {profile}")
        self.conn = None
        self.user_config = user_config
        self.site_config = site_config
        self.profile = profile
        
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
        # Connect to DuckDB using path from config
        profile = self.profile or self.site_config["profile"]
        db_path = self.site_config["profiles"][profile]["duckdb"]["path"]
        self.conn = duckdb.connect(db_path)
            
        # Load DuckDB extensions
        load_extensions(self.conn)
        
        # Load Python bootstrap if configured
        run_init_script(self.conn, self.site_config)
            
        # Inject secrets using the active profile
        project, profile_name = self._get_project_profile()
        logger.debug(f"Using project: {project}, profile: {profile_name}")
        inject_secrets(self.conn, self.site_config, self.user_config, profile_name)
        
        return self.conn
        
    def close(self):
        """Close the DuckDB connection"""
        if self.conn:
            self.conn.close()
            self.conn = None