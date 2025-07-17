from enum import Enum
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

class EndpointType(Enum):
    TOOL = "tool"
    RESOURCE = "resource"
    PROMPT = "prompt"

def get_endpoint_source_code(endpoint_dict: dict, endpoint_type: str, endpoint_file_path: Path, repo_root: Path) -> str:
    """Get the source code for the endpoint, resolving code vs file."""
    source = endpoint_dict[endpoint_type]["source"]
    if "code" in source:
        return source["code"]
    elif "file" in source:
        source_path = Path(source["file"])
        if source_path.is_absolute():
            full_path = repo_root / source_path.relative_to("/")
        else:
            full_path = endpoint_file_path.parent / source_path
        return full_path.read_text()
    else:
        raise ValueError("No source code found in endpoint definition")
