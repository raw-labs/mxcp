import os
import runpy
from pathlib import Path

def run_init_script(con, site_config):
    init_path = site_config.get("python", {}).get("path")
    if not init_path:
        return
    path = Path(init_path)
    if not path.exists():
        print("Warning: init.py not found:", path)
        return
    runpy.run_path(str(path))
    print("Executed init.py")