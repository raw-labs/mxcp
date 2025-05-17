from typing import Dict, Any, List, Optional
from raw.endpoints.executor import execute_endpoint, EndpointType
from raw.endpoints.loader import EndpointLoader
from raw.config.site_config import SiteConfig
from raw.config.user_config import UserConfig
import time
import json

def run_all_tests(config: SiteConfig, user: UserConfig, profile: Optional[str]) -> Dict[str, Any]:
    """Run tests for all endpoints in the repository"""
    loader = EndpointLoader(config)
    endpoints = loader.discover_endpoints()
    
    results = {
        "status": "ok",
        "tests_run": 0,
        "endpoints": []
    }
    
    for endpoint in endpoints:
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
            continue
            
        # Run tests for this endpoint
        endpoint_results = run_tests(f"{kind}/{name}", config, user, profile)
        results["endpoints"].append(endpoint_results)
        results["tests_run"] += endpoint_results.get("tests_run", 0)
        
        # Update overall status
        if endpoint_results.get("status") == "error":
            results["status"] = "error"
            
    return results

def run_tests(endpoint: str, config: SiteConfig, user: UserConfig, profile: Optional[str]) -> Dict[str, Any]:
    """Run tests for a specific endpoint"""
    try:
        # Split endpoint into type and name
        endpoint_type, name = endpoint.split("/", 1)
        endpoint_type = EndpointType(endpoint_type.lower())
        
        # Load endpoint definition
        loader = EndpointLoader(config)
        endpoint_def = loader.load_endpoint(endpoint_type, name)
        
        if not endpoint_def:
            return {
                "status": "error",
                "endpoint": endpoint,
                "message": f"Endpoint not found: {endpoint}"
            }
            
        # Get test definitions
        tests = []
        if endpoint_type == EndpointType.TOOL and "tests" in endpoint_def["tool"]:
            tests = endpoint_def["tool"]["tests"]
        elif endpoint_type == EndpointType.RESOURCE and "tests" in endpoint_def["resource"]:
            tests = endpoint_def["resource"]["tests"]
        elif endpoint_type == EndpointType.PROMPT and "tests" in endpoint_def["prompt"]:
            tests = endpoint_def["prompt"]["tests"]
            
        if not tests:
            return {
                "status": "ok",
                "endpoint": endpoint,
                "tests_run": 0,
                "message": "No tests defined"
            }
            
        # Run each test
        test_results = []
        for test_def in tests:
            start_time = time.time()
            
            # Convert test arguments to parameters
            params = {}
            for arg in test_def.get("arguments", []):
                params[arg["key"]] = arg["value"]
                
            try:
                # Execute endpoint with test parameters
                result = execute_endpoint(endpoint_type.value, name, params)
                
                # Compare with expected result if provided
                expected = test_def.get("result")
                passed = True
                error = None
                
                if expected is not None:
                    # Simple equality check for now
                    # TODO: Add more sophisticated comparison (e.g., partial matches)
                    if json.dumps(result, sort_keys=True) != json.dumps(expected, sort_keys=True):
                        passed = False
                        error = "Result does not match expected output"
                        
                test_results.append({
                    "name": test_def.get("name", "Unnamed test"),
                    "description": test_def.get("description"),
                    "status": "passed" if passed else "failed",
                    "error": error,
                    "time": time.time() - start_time
                })
                
            except Exception as e:
                test_results.append({
                    "name": test_def.get("name", "Unnamed test"),
                    "description": test_def.get("description"),
                    "status": "error",
                    "error": str(e),
                    "time": time.time() - start_time
                })
                
        # Aggregate test results
        status = "ok"
        if any(t["status"] == "error" for t in test_results):
            status = "error"
        elif any(t["status"] == "failed" for t in test_results):
            status = "failed"
            
        return {
            "status": status,
            "endpoint": endpoint,
            "tests_run": len(test_results),
            "tests": test_results
        }
        
    except Exception as e:
        return {
            "status": "error",
            "endpoint": endpoint,
            "message": str(e)
        }