import click
import asyncio
import json
import time
from typing import Dict, Any, Optional
from pathlib import Path
from mxcp.config.user_config import load_user_config
from mxcp.config.site_config import load_site_config
from mxcp.cli.utils import output_result, output_error, configure_logging
from mxcp.config.analytics import track_command_with_timing
from mxcp.auth.providers import UserContext
from mxcp.evals.runner import run_eval_suite, run_all_evals

def format_eval_results(results: Dict[str, Any], debug: bool = False) -> str:
    """Format eval results for human-readable output"""
    output = []
    
    if "error" in results:
        output.append(f"{click.style('❌ Error:', fg='red', bold=True)} {results['error']}")
        return "\n".join(output)
    
    # Single suite results
    if "suite" in results:
        tests = results.get("tests", [])
        total_tests = len(tests)
        passed_tests = sum(1 for t in tests if t.get("passed", False))
        failed_tests = total_tests - passed_tests
        
        # Header with summary
        output.append(f"\n{click.style('🧪 Eval Execution Summary', fg='cyan', bold=True)}")
        output.append(f"   Suite: {click.style(results['suite'], fg='yellow')}")
        if "description" in results:
            output.append(f"   Description: {results['description']}")
        if "model" in results:
            output.append(f"   Model: {click.style(results['model'], fg='yellow')}")
        output.append(f"   • {click.style(str(total_tests), fg='yellow')} tests total")
        if passed_tests > 0:
            output.append(f"   • {click.style(f'{passed_tests} passed', fg='green')}")
        if failed_tests > 0:
            output.append(f"   • {click.style(f'{failed_tests} failed', fg='red')}")
        
        # Show failed tests first
        failed = [t for t in tests if not t.get("passed", False)]
        if failed:
            output.append(f"\n{click.style('❌ Failed tests:', fg='red', bold=True)}")
            output.append("")
            for test in failed:
                test_time = test.get("time", 0)
                output.append(f"  {click.style('✗', fg='red')} {click.style(test['name'], fg='cyan')} {click.style(f'({test_time:.2f}s)', fg='bright_black')}")
                if test.get("description"):
                    output.append(f"    {test['description']}")
                
                if "error" in test:
                    output.append(f"    {click.style('Error:', fg='red')} {test['error']}")
                
                failures = test.get("failures", [])
                for failure in failures:
                    output.append(f"    {click.style('💡', fg='yellow')} {failure}")
                
                if debug and "details" in test:
                    output.append(f"    {click.style('Debug info:', fg='yellow')}")
                    for line in json.dumps(test['details'], indent=4).split('\n'):
                        output.append(f"    {line}")
                output.append("")
        
        # Show passed tests
        passed = [t for t in tests if t.get("passed", False)]
        if passed:
            output.append(f"\n{click.style('✅ Passed tests:', fg='green', bold=True)}")
            output.append("")
            for test in passed:
                test_time = test.get("time", 0)
                output.append(f"  {click.style('✓', fg='green')} {click.style(test['name'], fg='cyan')} {click.style(f'({test_time:.2f}s)', fg='bright_black')}")
                if test.get("description") and debug:
                    output.append(f"    {test['description']}")
        
        # Summary
        if all(t.get("passed", False) for t in tests):
            output.append(f"\n{click.style('🎉 All eval tests passed!', fg='green', bold=True)}")
        else:
            output.append(f"\n{click.style('⚠️  Failed:', fg='yellow', bold=True)} {failed_tests} eval test(s) failed")
            output.append(f"\n{click.style('💡 Tips for fixing failed evals:', fg='yellow')}")
            output.append("   • Check that tool names match your endpoint definitions")
            output.append("   • Verify argument names and types are correct")
            output.append("   • Ensure prompts are clear and unambiguous")
            output.append("   • Review assertion expectations")
        
        # Add timing info if available
        if "elapsed_time" in results:
            output.append(f"\n{click.style('⏱️  Total time:', fg='cyan')} {results['elapsed_time']:.2f}s")
    
    # Multiple suite results
    elif "suites" in results:
        suites = results.get("suites", [])
        
        # Handle case with no eval files
        if results.get("no_evals", False):
            output.append(click.style("\nℹ️  No eval files found", fg='blue'))
            output.append(f"   Create eval files ending with '-evals.yml' or '.evals.yml'")
            return "\n".join(output)
        
        total_suites = len(suites)
        passed_suites = sum(1 for s in suites if s.get("status") == "passed")
        failed_suites = sum(1 for s in suites if s.get("status") == "failed")
        error_suites = sum(1 for s in suites if s.get("status") == "error")
        
        # Header
        output.append(f"\n{click.style('🧪 Eval Execution Summary', fg='cyan', bold=True)}")
        output.append(f"   Evaluated {click.style(str(total_suites), fg='yellow')} suite{'s' if total_suites != 1 else ''}")
        if passed_suites > 0:
            output.append(f"   • {click.style(f'{passed_suites} passed', fg='green')}")
        if failed_suites > 0:
            output.append(f"   • {click.style(f'{failed_suites} failed', fg='red')}")
        if error_suites > 0:
            output.append(f"   • {click.style(f'{error_suites} errors', fg='red')}")
        
        # Show errors first
        errors = [s for s in suites if s.get("status") == "error"]
        if errors:
            output.append(f"\n{click.style('❌ Suites with errors:', fg='red', bold=True)}")
            for suite in errors:
                suite_name = suite['suite']
                output.append(f"\n  {click.style('✗', fg='red')} {click.style(suite_name, fg='yellow')}")
                output.append(f"    {click.style('Error:', fg='red')} {suite.get('error', 'Unknown error')}")
        
        # Show failed suites
        failed = [s for s in suites if s.get("status") == "failed"]
        if failed:
            output.append(f"\n{click.style('❌ Failed tests:', fg='red', bold=True)}")
            for suite in failed:
                tests = suite.get("tests", [])
                suite_name = suite['suite']
                path = suite.get('path', '')
                output.append(f"\n  {click.style('✗', fg='red')} {click.style(suite_name, fg='yellow')} ({path})")
                
                # Show individual tests
                for test in tests:
                    test_time = test.get("time", 0)
                    if test.get("passed", False):
                        output.append(f"    {click.style('✓', fg='green')} {test['name']} {click.style(f'({test_time:.2f}s)', fg='bright_black')}")
                    else:
                        output.append(f"    {click.style('✗', fg='red')} {test['name']} {click.style(f'({test_time:.2f}s)', fg='bright_black')}")
                        if test.get("error") and debug:
                            output.append(f"      {click.style('Error:', fg='red')} {test['error']}")
                        for failure in test.get("failures", []):
                            output.append(f"      {click.style('💡', fg='yellow')} {failure}")
        
        # Show passed suites
        passed = [s for s in suites if s.get("status") == "passed"]
        if passed:
            output.append(f"\n{click.style('✅ Passed tests:', fg='green', bold=True)}")
            for suite in passed:
                tests = suite.get("tests", [])
                suite_name = suite['suite']
                path = suite.get('path', '')
                output.append(f"\n  {click.style('✓', fg='green')} {click.style(suite_name, fg='yellow')} ({path})")
                
                # Show individual tests
                for test in tests:
                    test_time = test.get("time", 0)
                    output.append(f"    {click.style('✓', fg='green')} {test['name']} {click.style(f'({test_time:.2f}s)', fg='bright_black')}")
        
        # Overall summary
        if all(s.get("status") == "passed" for s in suites):
            output.append(f"\n{click.style('🎉 All eval suites passed!', fg='green', bold=True)}")
        else:
            output.append(f"\n{click.style('💡 Tip:', fg='yellow')} Run 'mxcp evals <suite_name>' to see detailed results for a specific suite")
        
        # Add timing info if available
        if "elapsed_time" in results:
            output.append(f"\n{click.style('⏱️  Total time:', fg='cyan')} {results['elapsed_time']:.2f}s")
    
    return "\n".join(output)

@click.command(name="evals")
@click.argument("suite_name", required=False)
@click.option("--user-context", "-u", help="User context as JSON string or @file.json")
@click.option("--model", "-m", help="Override model to use for evaluation")
@click.option("--profile", help="Profile name to use")
@click.option("--json-output", is_flag=True, help="Output in JSON format")
@click.option("--debug", is_flag=True, help="Show detailed debug information")
@track_command_with_timing("evals")
def evals(suite_name: Optional[str], user_context: Optional[str], model: Optional[str], 
         profile: Optional[str], json_output: bool, debug: bool):
    """Run LLM evaluation tests.
    
    This command executes eval tests that verify LLM behavior with your endpoints.
    If no suite name is provided, it will run all eval suites.
    
    \b
    User context can be provided for testing policy-protected endpoints:
    --user-context '{"user_id": "123", "role": "admin"}'
    --user-context @user_context.json
    
    \b
    Examples:
        mxcp evals                      # Run all eval suites
        mxcp evals churn_checks         # Run specific eval suite
        mxcp evals --model gpt-4-turbo  # Override model
        mxcp evals --json-output        # Output results in JSON format
        mxcp evals --user-context '{"role": "admin"}'  # Run with admin role
    """
    # Configure logging
    configure_logging(debug)
    
    try:
        site_config = load_site_config()
        user_config = load_user_config(site_config)
        
        # Parse user context if provided
        cli_user_context = None
        if user_context:
            if user_context.startswith("@"):
                # Load from file
                file_path = Path(user_context[1:])
                if not file_path.exists():
                    raise click.BadParameter(f"User context file not found: {file_path}")
                try:
                    with open(file_path) as f:
                        context_data = json.load(f)
                except json.JSONDecodeError as e:
                    raise click.BadParameter(f"Invalid JSON in user context file {file_path}: {e}")
            else:
                # Parse as JSON string
                try:
                    context_data = json.loads(user_context)
                except json.JSONDecodeError as e:
                    raise click.BadParameter(f"Invalid JSON in user context: {e}")
            
            # Create UserContext object from the data
            cli_user_context = UserContext(
                provider="cli",
                user_id=context_data.get("user_id", "cli_user"),
                username=context_data.get("username", "cli_user"),
                email=context_data.get("email"),
                name=context_data.get("name"),
                avatar_url=context_data.get("avatar_url"),
                raw_profile=context_data
            )
        
        # Run evals
        start_time = time.time()
        if suite_name:
            results = asyncio.run(run_eval_suite(
                suite_name, user_config, site_config, profile,
                cli_user_context=cli_user_context, override_model=model
            ))
        else:
            results = asyncio.run(run_all_evals(
                user_config, site_config, profile,
                cli_user_context=cli_user_context, override_model=model
            ))
        elapsed_time = time.time() - start_time
        results['elapsed_time'] = elapsed_time
        
        if json_output:
            output_result(results, json_output, debug)
        else:
            click.echo(format_eval_results(results, debug))
        
        # Exit with error code if any tests failed
        if suite_name and not results.get("all_passed", True):
            exit(1)
        elif not suite_name and results.get("suites"):
            if any(s.get("status") != "passed" for s in results["suites"]):
                exit(1)
                    
    except Exception as e:
        output_error(e, json_output, debug)
        exit(1) 