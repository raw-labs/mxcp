import duckdb
from raw.engine.extension_loader import load_raw_extension
from raw.engine.python_bootstrap.py import run_init_script
from raw.engine.secret_injection import inject_secrets

def start_session(site_config, user_config, profile=None):
    db_path = site_config.get("duckdb", {}).get("path", ":memory:")
    con = duckdb.connect(db_path)
    load_raw_extension(con)
    inject_secrets(con, site_config, user_config, profile)
    run_init_script(con, site_config)
    return con