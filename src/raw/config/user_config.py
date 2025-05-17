import os
import yaml
from pathlib import Path
import json
from jsonschema import validate, ValidationError

def load_user_config():
    path = Path(os.environ.get("RAW_CONFIG", Path.home() / ".raw" / "config.yaml"))
    if not path.exists():
        raise FileNotFoundError(f"RAW user config not found at {path}")
    with open(path) as f:
        config = yaml.safe_load(f)
    # Load and apply JSON Schema validation
    schema_path = Path(__file__).parent / "schemas" / "raw-config-schema-1.0.0.json"
    with open(schema_path) as schema_file:
        schema = json.load(schema_file)

    try:
        validate(instance=config, schema=schema)
    except ValidationError as e:
        raise ValueError(f"User config validation error: {e.message}")
    return config
