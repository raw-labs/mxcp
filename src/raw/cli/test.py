import click
from raw.endpoints.tester import run_tests, run_all_tests
from raw.config.site_config import load_site_config
from raw.config.user_config import load_user_config

@click.command(name="test")
@click.argument("endpoint", required=False)
@click.option("--profile", default=None)
@click.option("--json", is_flag=True)
def test(endpoint, profile, json):
    """Run endpoint tests"""
    config = load_site_config()
    user = load_user_config()
    if endpoint:
        results = run_tests(endpoint, config, user, profile)
    else:
        results = run_all_tests(config, user, profile)
    print(results if json else str(results))