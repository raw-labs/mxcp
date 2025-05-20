from typing import Dict, Any, List, Optional
from raw.endpoints.executor import execute_endpoint, EndpointType, EndpointExecutor
from raw.endpoints.loader import EndpointLoader
from raw.config.site_config import SiteConfig, find_repo_root
import time
import json
import logging
import os
from pathlib import Path
import yaml
from jsonschema import validate
import duckdb

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

def run_all_tests(config: SiteConfig, profile: Optional[str]) -> Dict[str, Any]:
    """Run tests for all endpoints in the repository"""
    # Find repository root
    repo_root = find_repo_root()
    logger.debug(f"Repository root: {repo_root}")
    
    # List all YAML files in the repository
    endpoints_files = list(repo_root.rglob("*.yml"))
    logger.debug(f"Found {len(endpoints_files)} YAML files")
    
    results = {
        "status": "ok",
        "tests_run": 0,
        "endpoints": []
    }
    
    # Skip raw-site.yml and raw-config.yml
    for file_path in endpoints_files:
        if file_path.name in ["raw-site.yml", "raw-config.yml"]:
            continue
            
        logger.debug(f"Processing file: {file_path}")
        try:
            with open(file_path) as f:
                endpoint_def = yaml.safe_load(f)
                
            # Determine endpoint type and name
            if "tool" in endpoint_def:
                kind = "tool"
                name = endpoint_def["tool"]["name"]
            elif "resource" in endpoint_def:
                kind = "resource"
                name = endpoint_def["resource"]["uri"]
            elif "prompt" in endpoint_def:
                kind = "prompt"
                name = endpoint_def["prompt"]["name"]
            else:
                logger.debug(f"Skipping file {file_path}: not a valid endpoint")
                continue
                
            # Run tests for this endpoint
            endpoint_results = run_tests(f"{kind}/{name}", config, profile)
            results["endpoints"].append(endpoint_results)
            results["tests_run"] += endpoint_results.get("tests_run", 0)
            
            # Update overall status
            if endpoint_results.get("status") == "error":
                results["status"] = "error"
            elif endpoint_results.get("status") == "failed" and results["status"] != "error":
                results["status"] = "failed"
        except Exception as e:
            logger.error(f"Error processing file {file_path}: {str(e)}")
            
    return results

def run_tests(endpoint: str, config: SiteConfig, profile: Optional[str]) -> Dict[str, Any]:
    """Run tests for a specific endpoint"""
    try:
        # Split endpoint into type and name
        endpoint_type, name = endpoint.split("/", 1)
        endpoint_type_enum = EndpointType(endpoint_type.lower())
        logger.info(f"Running tests for endpoint: {endpoint_type}/{name}")
        
        # Use EndpointLoader to load the endpoint definition
        loader = EndpointLoader(config)
        endpoint_def = loader.load_endpoint(endpoint_type, name)
        
        if endpoint_def is None:
            logger.error(f"Endpoint not found: {endpoint}")
            return {
                "status": "error",
                "endpoint": endpoint,
                "message": f"Endpoint not found: {endpoint}"
            }
            
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
                "endpoint": endpoint,
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
            
            try:
                # Use the proper execute_endpoint function
                result = execute_endpoint(endpoint_type, name, params)
                logger.info(f"Execution result: {result}")
                
                # Normalize result for comparison
                normalized_result = normalize_result(result, column_names, endpoint_type)
                logger.info(f"Normalized result: {normalized_result}")
                
                # Compare with expected result
                passed = compare_results(normalized_result, expected_result)
                
                status = "passed" if passed else "failed"
                error = None if passed else "Result does not match expected output"
                
                if not passed:
                    has_failed = True
                    logger.error(f"Test failed: {error}")
                    logger.error(f"Expected: {expected_result}")
                    logger.error(f"Got: {normalized_result}")
                
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
                    "error": str(e),
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
            "endpoint": endpoint,
            "tests_run": len(test_results),
            "tests": test_results
        }
        
    except Exception as e:
        logger.error(f"Error in run_tests: {str(e)}")
        return {
            "status": "error",
            "endpoint": endpoint,
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
        # Prompts typically return [(messages,)]
        if isinstance(result, list) and len(result) == 1 and isinstance(result[0], tuple) and len(result[0]) == 1:
            return result[0][0]  # Extract the messages directly
    
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

def compare_results(result, expected):
    """Compare normalized result with expected result"""
    # Handle None expected result
    if expected is None:
        return True
        
    # Convert both to JSON strings for comparison
    # Use sort_keys to ensure consistency in dictionary key ordering
    result_json = json.dumps(result, sort_keys=True)
    expected_json = json.dumps(expected, sort_keys=True)
    
    return result_json == expected_json