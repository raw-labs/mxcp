"""
Migration utilities for MXCP configuration files.

Handles backward compatibility and provides helpful migration guidance
for users upgrading from pre-production versions.
"""

def check_and_migrate_legacy_version(config_data: dict, config_type: str, config_path: str = None) -> None:
    """
    Check for legacy version format and provide migration guidance.
    
    Args:
        config_data: The loaded YAML configuration data
        config_type: Type of config ("site" or "user")  
        config_path: Path to the config file (for error message)
        
    Raises:
        ValueError: If legacy version format is detected with migration instructions
    """
    if not isinstance(config_data, dict):
        return
        
    mxcp_version = config_data.get("mxcp")
    
    # Check for old string-based versioning (e.g., "1.0.0", "1", etc.)
    if isinstance(mxcp_version, str):
        config_file = config_path or f"mxcp-{config_type}.yml"
        
        if config_type == "site":
            migration_msg = f"""
🚨 MIGRATION REQUIRED: Pre-production MXCP version detected

Your {config_file} file uses an old format from a pre-production release.

REQUIRED CHANGES:

1. Update version format:
   OLD: mxcp: "{mxcp_version}"  
   NEW: mxcp: 1

2. Reorganize your files to the new directory structure:
   
   OLD structure:
   your-project/
   ├── endpoints/           # Mixed tool/resource/prompt files
   ├── mxcp-site.yml
   ├── drift-profile.json   # Drift files in root
   ├── logs-profile.jsonl   # Audit files in root  
   └── db-profile.duckdb    # Database files in root

   NEW structure:
   your-project/
   ├── tools/               # Tool YAML definitions
   ├── resources/           # Resource YAML definitions
   ├── prompts/             # Prompt YAML definitions
   ├── evals/               # Evaluation YAML definitions
   ├── python/              # Python extensions
   ├── sql/                 # SQL implementations
   ├── drift/               # Drift snapshots: drift-profile.json
   ├── audit/               # Audit logs: logs-profile.jsonl
   ├── data/                # Database files: db-profile.duckdb
   └── mxcp-site.yml        # Project configuration

3. Update YAML file references:
   - Tool/resource/prompt files should reference SQL files as: ../sql/filename.sql
   - Move all SQL files from endpoints/ to sql/ directory

MIGRATION STEPS:
1. Update mxcp-site.yml: change 'mxcp: "{mxcp_version}"' to 'mxcp: 1'
2. Create directories: tools/, resources/, prompts/, evals/, python/, sql/, drift/, audit/, data/
3. Move endpoint files to appropriate directories based on type
4. Move SQL files to sql/ directory  
5. Update file references in YAML files
"""
        else:  # user config
            migration_msg = f"""
🚨 MIGRATION REQUIRED: Pre-production MXCP version detected

Your {config_file} file uses an old format from a pre-production release.

REQUIRED CHANGE:
   OLD: mxcp: "{mxcp_version}"
   NEW: mxcp: 1

Please update your global user configuration file at:
{config_path or '~/.mxcp/config.yml'}

Change the first line from:
   mxcp: "{mxcp_version}"
to:
   mxcp: 1

This affects your global MXCP settings. After fixing this, you may also need 
to update your project files to use the new directory structure.
"""
        
        raise ValueError(migration_msg.strip()) 