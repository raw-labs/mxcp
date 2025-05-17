import yaml
import json
from jsonschema import validate, ValidationError
from pathlib import Path
from raw.config.types import SiteConfig

def _apply_defaults(config: dict) -> dict:
    """Apply default values to the config"""
    # Create a copy to avoid modifying the input
    config = config.copy()
    
    # Apply defaults for optional sections
    if "dbt" not in config:
        config["dbt"] = {"enabled": True}
    elif "enabled" not in config["dbt"]:
        config["dbt"]["enabled"] = True
        
    # DuckDB defaults
    if "duckdb" not in config:
        config["duckdb"] = {"path": ":memory:"}
    elif "path" not in config["duckdb"]:
        config["duckdb"]["path"] = ":memory:"
        
    return config

def load_site_config(path=None) -> SiteConfig:
    if path:
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"{path} not found.")
    else:
        # Traverse upward from current directory
        current = Path.cwd()
        for parent in [current] + list(current.parents):
            candidate = parent / "raw-site.yml"
            if candidate.exists():
                path = candidate
                break
        else:
            raise FileNotFoundError("raw-site.yml not found in current directory or any parent directory.")

    with open(path) as f:
        config = yaml.safe_load(f)
        
    # Apply defaults before validation
    config = _apply_defaults(config)
        
    # Load and apply JSON Schema validation
    schema_path = Path(__file__).parent / "schemas" / "raw-site-schema-1.0.0.json"
    with open(schema_path) as schema_file:
        schema = json.load(schema_file)

    try:
        validate(instance=config, schema=schema)
    except ValidationError as e:
        raise ValueError(f"Site config validation error: {e.message}")
    return config
