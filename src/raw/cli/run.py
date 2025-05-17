
import click
from raw.config.site_config import load_site_config
from raw.config.user_config import load_user_config
import duckdb

@click.command(name="run")
@click.argument("endpoint")
@click.option("--profile", default=None)
def run_endpoint(endpoint, profile):
    """Run an endpoint with mock parameters"""
    print(f"Running endpoint: {endpoint}")
    site = load_site_config()
    user = load_user_config()

    con = duckdb.connect(site.get("duckdb", {}).get("path", ":memory:"))
    con.sql("SELECT 'hello from raw'").show()
