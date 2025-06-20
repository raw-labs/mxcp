from typing import Dict, Any, List, Optional
from mxcp.endpoints.executor import execute_endpoint, EndpointType, EndpointExecutor
from mxcp.endpoints.loader import EndpointLoader
from mxcp.config.site_config import SiteConfig, find_repo_root
from mxcp.config.user_config import UserConfig
from mxcp.engine.duckdb_session import DuckDBSession
from mxcp.auth.providers import UserContext
import time
import json
import logging
import os
from pathlib import Path
import yaml
from jsonschema import validate
import duckdb
import asyncio
import numpy as np

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

async def run_all_tests(user_config: UserConfig, site_config: SiteConfig, profile: Optional[str], readonly: Optional[bool] = None, cli_user_context: Optional[UserContext] = None) -> Dict[str, Any]:
    """Run tests for all endpoints in the repository (async)"""
    repo_root = find_repo_root()
    logger.debug(f"Repository root: {repo_root}")
    
    # Use EndpointLoader to discover endpoints
    loader = EndpointLoader(site_config)
    endpoints = loader.discover_endpoints()
    logger.debug(f"Found {len(endpoints)} YAML files")
    
    results = {
        "status": "ok",
        "tests_run": 0,
        "endpoints": []
    }
    
    # Create a session for all tests
    session = DuckDBSession(user_config, site_config, profile, readonly=readonly)
    
    try:
        for file_path, endpoint, error_msg in endpoints:
            if file_path.name in ["mxcp-site.yml", "mxcp-config.yml"]:
                continue
                
            logger.debug(f"Processing file: {file_path}")
            
            # Calculate relative path for results
            try:
                relative_path = str(file_path.relative_to(repo_root))
            except ValueError:
                relative_path = file_path.name
            
            if error_msg is not None:
                # This endpoint failed to load
                results["endpoints"].append({
                    "endpoint": str(file_path),
                    "path": relative_path,
                    "test_results": {
                        "status": "error",
                        "message": error_msg
                    }
                })
                results["status"] = "error"
                continue
                
            try:
                # Determine endpoint type and name
                if "tool" in endpoint:
                    kind = "tool"
                    name = endpoint["tool"]["name"]
                elif "resource" in endpoint:
                    kind = "resource"
                    name = endpoint["resource"]["uri"]
                elif "prompt" in endpoint:
                    kind = "prompt"
                    name = endpoint["prompt"]["name"]
                else:
                    logger.debug(f"Skipping file {file_path}: not a valid endpoint")
                    continue
                    
                # Run tests for this endpoint with the shared session
                test_results = await run_tests_with_session(kind, name, user_config, site_config, session, profile, cli_user_context)
                
                # Wrap test results with endpoint context
                endpoint_result = {
                    "endpoint": f"{kind}/{name}",
                    "path": relative_path,
                    "test_results": test_results
                }
                
                results["endpoints"].append(endpoint_result)
                results["tests_run"] += test_results.get("tests_run", 0)
                
                # Update overall status
                if test_results.get("status") == "error":
                    results["status"] = "error"
                elif test_results.get("status") == "failed" and results["status"] != "error":
                    results["status"] = "failed"
            except Exception as e:
                logger.error(f"Error processing file {file_path}: {str(e)}")
                results["endpoints"].append({
                    "endpoint": str(file_path),
                    "path": relative_path,
                    "test_results": {
                        "status": "error",
                        "message": str(e)
                    }
                })
                results["status"] = "error"
    finally:
        session.close()
            
    return results

async def run_tests(endpoint_type: str, name: str, user_config: UserConfig, site_config: SiteConfig, profile: Optional[str], readonly: Optional[bool] = None, cli_user_context: Optional[UserContext] = None) -> Dict[str, Any]:
    """Run tests for a specific endpoint type and name."""
    # Create a session for this test run
    session = DuckDBSession(user_config, site_config, profile, readonly=readonly)
    
    try:
        return await run_tests_with_session(endpoint_type, name, user_config, site_config, session, profile, cli_user_context)
    finally:
        session.close()

async def run_tests_with_session(endpoint_type: str, name: str, user_config: UserConfig, site_config: SiteConfig, session: DuckDBSession, profile: Optional[str], cli_user_context: Optional[UserContext] = None) -> Dict[str, Any]:
    """Run tests for a specific endpoint type and name with an existing session."""
    try:
        endpoint_type_enum = EndpointType(endpoint_type.lower())
        logger.info(f"Running tests for endpoint: {endpoint_type}/{name}")
        
        # Use EndpointLoader to load the endpoint definition
        loader = EndpointLoader(site_config)
        result = loader.load_endpoint(endpoint_type, name)
        
        if result is None:
            logger.error(f"Endpoint not found: {endpoint_type}/{name}")
            return {
                "status": "error",
                "message": f"Endpoint not found: {endpoint_type}/{name}"
            }
            
        endpoint_file_path, endpoint_def = result
            
        # Get test definitions
        tests = []
        if endpoint_type == "tool" and "tests" in endpoint_def["tool"]:
            tests = endpoint_def["tool"]["tests"]
        elif endpoint_type == "resource" and "tests" in endpoint_def["resource"]:
            tests = endpoint_def["resource"]["tests"]
        elif endpoint_type == "prompt" and "tests" in endpoint_def["prompt"]:
            tests = endpoint_def["prompt"]["tests"]
        logger.info(f"Found {len(tests)} tests")
        
        if not tests:
            logger.warning("No tests defined")
            return {
                "status": "ok",
                "tests_run": 0,
                "message": "No tests defined"
            }
            
        # Extract column names from return schema 
        column_names = extract_column_names(endpoint_def, endpoint_type)
        logger.info(f"Column names for results: {column_names}")
        
        # Run each test
        test_results = []
        has_error = False
        has_failed = False
        
        for test_def in tests:
            start_time = time.time()
            test_name = test_def.get('name', 'Unnamed test')
            logger.info(f"Running test: {test_name}")
            
            # Convert test arguments to parameters
            params = {}
            for arg in test_def.get("arguments", []):
                params[arg["key"]] = arg["value"]
            logger.info(f"Test parameters: {params}")
            
            expected_result = test_def.get("result")
            logger.info(f"Expected result: {expected_result}")
            
            # Determine user context for this test
            # CLI user context takes precedence over test-defined context
            test_user_context = cli_user_context
            if test_user_context is None and "user_context" in test_def:
                # Create UserContext from test definition
                test_context_data = test_def["user_context"]
                test_user_context = UserContext(
                    provider="test",  # Special provider for test-defined contexts
                    user_id=test_context_data.get("user_id", "test_user"),
                    username=test_context_data.get("username", "test_user"),
                    email=test_context_data.get("email"),
                    name=test_context_data.get("name"),
                    avatar_url=test_context_data.get("avatar_url"),
                    raw_profile=test_context_data  # Store full context for policy access
                )
                logger.info(f"Using test-defined user context: {test_context_data}")
            elif test_user_context:
                logger.info(f"Using CLI-provided user context")
            
            try:
                # Use the execute_endpoint function with session and profile
                result = await execute_endpoint(endpoint_type, name, params, user_config, site_config, session, profile, user_context=test_user_context)
                logger.info(f"Execution result: {result}")
                
                # Normalize result for comparison
                normalized_result = normalize_result(result, column_names, endpoint_type)
                logger.info(f"Normalized result: {normalized_result}")
                
                # Compare with various assertion types
                passed, error_msg = compare_results(normalized_result, test_def)
                
                status = "passed" if passed else "failed"
                error = error_msg if not passed else None
                
                if not passed:
                    has_failed = True
                    logger.error(f"Test failed: {error}")
                
                test_results.append({
                    "name": test_name,
                    "description": test_def.get("description", ""),
                    "status": status,
                    "error": error,
                    "time": time.time() - start_time
                })
                
            except Exception as e:
                logger.error(f"Error during test execution: {str(e)}")
                test_results.append({
                    "name": test_name,
                    "description": test_def.get("description", ""),
                    "status": "error",
                    "error": e,  # Pass the actual exception object instead of just the string
                    "time": time.time() - start_time
                })
                has_error = True
                
        # Determine overall status based on test results
        status = "ok"
        if has_error:
            status = "error"
        elif has_failed:
            status = "failed"
                
        logger.info(f"Final test status: {status}")
        
        return {
            "status": status,
            "tests_run": len(tests),
            "tests": test_results
        }
    except Exception as e:
        logger.error(f"Error in run_tests: {str(e)}")
        return {
            "status": "error",
            "message": str(e)
        }

def get_endpoint_source_code(endpoint_def: dict, endpoint_type: str, endpoint_file_path: Path, repo_root: Path) -> str:
    """Get the source code for the endpoint, resolving code vs file."""
    source = endpoint_def[endpoint_type]["source"]
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

def extract_column_names(endpoint_def: Dict[str, Any], endpoint_type: str) -> List[str]:
    """Extract column names from endpoint definition"""
    columns = []
    
    if endpoint_type == "tool" and "return" in endpoint_def["tool"]:
        return_def = endpoint_def["tool"]["return"]
        if return_def.get("type") == "array" and "items" in return_def:
            items = return_def["items"]
            if items.get("type") == "object" and "properties" in items:
                columns = list(items["properties"].keys())
    
    elif endpoint_type == "resource" and "return" in endpoint_def["resource"]:
        return_def = endpoint_def["resource"]["return"]
        if return_def.get("type") == "array" and "items" in return_def:
            items = return_def["items"]
            if items.get("type") == "object" and "properties" in items:
                columns = list(items["properties"].keys())
    
    return columns

def normalize_result(result, column_names, endpoint_type):
    """Normalize DuckDB result for comparison with expected result"""
    # Handle empty results
    if not result:
        return []
        
    # Handle prompt results
    if endpoint_type == "prompt":
        # Modern prompts return a list of message objects
        if isinstance(result, list) and len(result) > 0:
            # Check if this is a list of message objects
            if all(isinstance(msg, dict) and 'role' in msg for msg in result):
                # Find the last assistant message
                for msg in reversed(result):
                    if msg.get('role') == 'assistant' and 'prompt' in msg:
                        assistant_response = msg['prompt'].strip()
                        # Try to parse JSON if the result looks like JSON
                        if (assistant_response.startswith('[') and assistant_response.endswith(']')) or \
                           (assistant_response.startswith('{') and assistant_response.endswith('}')):
                            try:
                                return json.loads(assistant_response)
                            except json.JSONDecodeError:
                                # If JSON parsing fails, return the string as is
                                pass
                        return assistant_response
                # If no assistant message found, return the full result
                return result
            
        # Legacy format: Prompts typically return [(messages,)]
        if isinstance(result, list) and len(result) == 1 and isinstance(result[0], tuple) and len(result[0]) == 1:
            prompt_result = result[0][0]  # Extract the messages directly
            
            # Try to parse JSON if the result looks like JSON
            if isinstance(prompt_result, str):
                prompt_result = prompt_result.strip()
                if (prompt_result.startswith('[') and prompt_result.endswith(']')) or \
                   (prompt_result.startswith('{') and prompt_result.endswith('}')):
                    try:
                        return json.loads(prompt_result)
                    except json.JSONDecodeError:
                        # If JSON parsing fails, return the string as is
                        pass
            
            return prompt_result
    
    # Handle tool/resource results (list of tuples)
    if isinstance(result, list) and column_names:
        normalized = []
        
        for row in result:
            if isinstance(row, tuple):
                # Map tuple values to column names
                row_dict = {}
                for i, col in enumerate(column_names):
                    if i < len(row):
                        row_dict[col] = row[i]
                normalized.append(row_dict)
            else:
                normalized.append(row)
        
        return normalized
    
    # Return as is if we can't normalize
    return result

def compare_results(result, test_def):
    """Compare result with various assertion types in test definition.
    
    Returns: (passed: bool, error_message: str or None)
    """
    # Exact match with 'result' field (original behavior)
    if "result" in test_def:
        expected = test_def["result"]
        if expected is not None:
            # For complex objects that can't be JSON serialized (like ndarray),
            # convert to a more basic representation for comparison
            def make_serializable(obj):
                """Convert complex objects to serializable form for comparison"""
                if isinstance(obj, np.ndarray):
                    return obj.tolist()
                elif isinstance(obj, dict):
                    return {k: make_serializable(v) for k, v in obj.items()}
                elif isinstance(obj, (list, tuple)):
                    return [make_serializable(item) for item in obj]
                else:
                    return obj
            
            try:
                # Try to make both objects serializable
                serializable_result = make_serializable(result)
                serializable_expected = make_serializable(expected)
                
                # Convert both to JSON strings for comparison
                # Use sort_keys to ensure consistency in dictionary key ordering
                result_json = json.dumps(serializable_result, sort_keys=True)
                expected_json = json.dumps(serializable_expected, sort_keys=True)
                
                if result_json != expected_json:
                    return False, f"Result does not match expected output.\nExpected: {expected}\nGot: {result}"
            except (TypeError, ValueError) as e:
                # If serialization still fails, fall back to direct comparison
                logger.warning(f"JSON serialization failed, falling back to direct comparison: {e}")
                if result != expected:
                    return False, f"Result does not match expected output.\nExpected: {expected}\nGot: {result}"
    
    # Partial object match with 'result_contains'
    if "result_contains" in test_def:
        expected_contains = test_def["result_contains"]
        if isinstance(result, dict) and isinstance(expected_contains, dict):
            # Check that all expected fields exist with expected values
            for key, expected_value in expected_contains.items():
                if key not in result:
                    return False, f"Expected field '{key}' not found in result"
                if result[key] != expected_value:
                    return False, f"Field '{key}' has value {result[key]}, expected {expected_value}"
        elif isinstance(result, list):
            # For arrays, support both dict patterns and primitive values
            if isinstance(expected_contains, dict):
                # Check if any item contains the expected fields
                found = False
                for item in result:
                    if isinstance(item, dict):
                        matches = True
                        for key, expected_value in expected_contains.items():
                            if key not in item or item[key] != expected_value:
                                matches = False
                                break
                        if matches:
                            found = True
                            break
                if not found:
                    return False, f"No item in array contains the expected fields: {expected_contains}"
            else:
                # For non-dict patterns, check if the value exists in the array
                if expected_contains not in result:
                    return False, f"Array does not contain expected value: {expected_contains}"
        else:
            return False, f"result_contains assertion requires dict or array result, got {type(result)}"
    
    # Field exclusion with 'result_not_contains'
    if "result_not_contains" in test_def:
        excluded_fields = test_def["result_not_contains"]
        if isinstance(result, dict):
            for field in excluded_fields:
                if field in result:
                    return False, f"Field '{field}' should not be present in result but was found"
        else:
            return False, f"result_not_contains assertion requires dict result, got {type(result)}"
    
    # Array contains specific item with 'result_contains_item'
    if "result_contains_item" in test_def:
        expected_item = test_def["result_contains_item"]
        if not isinstance(result, list):
            return False, f"result_contains_item assertion requires array result, got {type(result)}"
        
        found = False
        for item in result:
            if item == expected_item:
                found = True
                break
            # Also support partial match for dict items
            elif isinstance(item, dict) and isinstance(expected_item, dict):
                matches = True
                for key, expected_value in expected_item.items():
                    if key not in item or item[key] != expected_value:
                        matches = False
                        break
                if matches:
                    found = True
                    break
        
        if not found:
            return False, f"Array does not contain expected item: {expected_item}"
    
    # Array contains all items with 'result_contains_all'
    if "result_contains_all" in test_def:
        expected_items = test_def["result_contains_all"]
        if not isinstance(result, list):
            return False, f"result_contains_all assertion requires array result, got {type(result)}"
        
        for expected_item in expected_items:
            found = False
            for item in result:
                if item == expected_item:
                    found = True
                    break
                # Also support partial match for dict items (like result_contains_item)
                elif isinstance(item, dict) and isinstance(expected_item, dict):
                    matches = True
                    for key, expected_value in expected_item.items():
                        if key not in item or item[key] != expected_value:
                            matches = False
                            break
                    if matches:
                        found = True
                        break
            if not found:
                return False, f"Array does not contain expected item: {expected_item}"
    
    # Array length check with 'result_length'
    if "result_length" in test_def:
        expected_length = test_def["result_length"]
        if not isinstance(result, list):
            return False, f"result_length assertion requires array result, got {type(result)}"
        if len(result) != expected_length:
            return False, f"Array has {len(result)} items, expected {expected_length}"
    
    # String contains with 'result_contains_text'
    if "result_contains_text" in test_def:
        expected_text = test_def["result_contains_text"]
        if not isinstance(result, str):
            # Try to convert to string for comparison
            result_str = str(result)
        else:
            result_str = result
        
        if expected_text not in result_str:
            return False, f"Result does not contain expected text: '{expected_text}'"
    
    # If no assertions are specified, consider the test passed
    return True, None