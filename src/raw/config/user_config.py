import os
import yaml
from pathlib import Path
import json
from jsonschema import validate, ValidationError
from raw.config.types import UserConfig

def _apply_defaults(config: dict) -> dict:
    """Apply default values to the user config"""
    # Create a copy to avoid modifying the input
    config = config.copy()
    
    # Ensure each profile has at least empty secrets and adapter_configs
    for project in config.get("projects", {}).values():
        for profile in project.get("profiles", {}).values():
            if profile is None:
                profile = {}
            if "secrets" not in profile:
                profile["secrets"] = []
            if "adapter_configs" not in profile:
                profile["adapter_configs"] = {}
    
    return config

def load_user_config() -> UserConfig:
    path = Path(os.environ.get("RAW_CONFIG", Path.home() / ".raw" / "config.yml"))
    if not path.exists():
        raise FileNotFoundError(f"RAW user config not found at {path}")
    with open(path) as f:
        config = yaml.safe_load(f)
    
    # Apply defaults before validation
    config = _apply_defaults(config)
    
    # Load and apply JSON Schema validation
    schema_path = Path(__file__).parent / "schemas" / "raw-config-schema-1.0.0.json"
    with open(schema_path) as schema_file:
        schema = json.load(schema_file)

    try:
        validate(instance=config, schema=schema)
    except ValidationError as e:
        raise ValueError(f"User config validation error: {e.message}")
    return config
