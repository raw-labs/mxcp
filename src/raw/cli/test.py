import click
import json
import asyncio
from typing import Dict, Any, Optional
from raw.endpoints.tester import run_tests, run_all_tests
from raw.config.user_config import load_user_config
from raw.config.site_config import load_site_config
from raw.cli.utils import output_result, output_error

def format_test_results(results):
    """Format test results for human-readable output"""
    if isinstance(results, str):
        return results
        
    output = []
    
    # Overall status
    status = results.get("status", "unknown")
    tests_run = results.get("tests_run", 0)
    output.append(f"Status: {status.upper()}")
    output.append(f"Tests run: {tests_run}")
    output.append("")
    
    # Individual endpoint results
    for endpoint_result in results.get("endpoints", []):
        endpoint = endpoint_result.get("endpoint", "unknown")
        endpoint_status = endpoint_result.get("status", "unknown")
        output.append(f"Endpoint: {endpoint}")
        output.append(f"Status: {endpoint_status.upper()}")
        
        if "message" in endpoint_result:
            output.append(f"Message: {endpoint_result['message']}")
            
        # Test results
        for test in endpoint_result.get("tests", []):
            test_name = test.get("name", "Unnamed test")
            test_status = test.get("status", "unknown")
            test_time = test.get("time", 0)
            
            output.append(f"  Test: {test_name}")
            output.append(f"  Status: {test_status.upper()}")
            output.append(f"  Time: {test_time:.2f}s")
            
            if test.get("description"):
                output.append(f"  Description: {test['description']}")
                
            if test.get("error"):
                output.append(f"  Error: {test['error']}")
                
        output.append("")
        
    return "\n".join(output)

@click.command(name="test")
@click.argument("endpoint", required=False)
@click.option("--profile", help="Profile name to use")
@click.option("--json-output", is_flag=True, help="Output in JSON format")
@click.option("--debug", is_flag=True, help="Show detailed error information")
def test(endpoint: Optional[str], profile: Optional[str], json_output: bool, debug: bool):
    """Run tests for one or all endpoints"""
    try:
        site_config = load_site_config()
        user_config = load_user_config(site_config)
        
        if endpoint:
            results = asyncio.run(run_tests(endpoint, user_config, site_config, profile))
        else:
            results = asyncio.run(run_all_tests(user_config, site_config, profile))
            
        if json_output:
            output_result(results, json_output, debug)
        else:
            click.echo(format_test_results(results))
    except Exception as e:
        output_error(e, json_output, debug)