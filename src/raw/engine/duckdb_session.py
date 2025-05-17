import duckdb
from pathlib import Path
from typing import Dict, Any, Optional
from raw.config.site_config import load_site_config
from raw.config.user_config import load_user_config
from raw.config.types import SiteConfig, UserConfig
from raw.engine.secret_injection import inject_secrets
from raw.engine.extension_loader import load_raw_extension
from raw.engine.python_bootstrap import run_init_script

class DuckDBSession:
    def __init__(self):
        self.conn = None
        self.site_config: Optional[SiteConfig] = None
        self.user_config: Optional[UserConfig] = None
        
    def _load_configs(self):
        """Load both site and user configs"""
        self.site_config = load_site_config()
        self.user_config = load_user_config()
        
    def _get_project_profile(self) -> tuple[str, str]:
        """Get the current project and profile from site config"""
        if not self.site_config:
            raise ValueError("Site config not loaded")
        return self.site_config["project"], self.site_config["profile"]
        
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
        # Load configs first
        self._load_configs()
        
        # Connect to DuckDB using path from config
        db_path = self.site_config["duckdb"]["path"]
        self.conn = duckdb.connect(db_path)
            
        # Load RAW extension
        load_raw_extension(self.conn)
        
        # Load Python bootstrap if configured
        run_init_script(self.conn, self.site_config)
            
        # Inject secrets
        inject_secrets(self.conn, self.site_config, self.user_config, self.site_config["profile"])
        
        return self.conn
        
    def close(self):
        """Close the DuckDB connection"""
        if self.conn:
            self.conn.close()
            self.conn = None