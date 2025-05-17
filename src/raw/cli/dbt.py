import click
from raw.engine.dbt_runner import configure_dbt, run_stale_models

@click.group()
def dbt():
    """DBT-related commands"""
    pass

@dbt.command("config")
def dbt_config():
    """Configure dbt profiles"""
    configure_dbt()

@dbt.command("cron")
def dbt_cron():
    """Run stale dbt models"""
    run_stale_models()