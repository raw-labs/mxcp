"""Test runner for executing endpoint tests.

This module provides the core test execution logic for running tests
defined in endpoint YAML files. It handles test execution, result
normalization, and assertion checking.
"""

import json
import logging
import time
from typing import Any

import numpy as np

from mxcp.sdk.auth import UserContext
from mxcp.sdk.executor import ExecutionEngine
from mxcp.server.core.config.models import SiteConfigModel, UserConfigModel
from mxcp.server.definitions.endpoints._types import EndpointDefinition, TestDefinition
from mxcp.server.definitions.endpoints.loader import EndpointLoader
from mxcp.server.services.endpoints import execute_endpoint_with_engine

logger = logging.getLogger(__name__)


class TestRunner:
    """Runs tests for endpoints using the execution engine."""

    def __init__(
        self,
        user_config: UserConfigModel,
        site_config: SiteConfigModel,
        execution_engine: ExecutionEngine,
    ):
        """Initialize the test runner.

        Args:
            user_config: User configuration
            site_config: Site configuration
            execution_engine: Execution engine to use for running tests
        """
        self.user_config = user_config
        self.site_config = site_config
        self.execution_engine = execution_engine
        self.loader = EndpointLoader(site_config)

    async def run_tests_for_endpoint(
        self,
        endpoint_type: str,
        name: str,
        cli_user_context: UserContext | None = None,
        request_headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Run tests for a specific endpoint.

        Args:
            endpoint_type: Type of endpoint ("tool", "resource", "prompt")
            name: Name of the endpoint
            cli_user_context: Optional user context from CLI

        Returns:
            Test results dictionary with status, tests_run, and test details
        """
        try:
            logger.info(f"Running tests for endpoint: {endpoint_type}/{name}")

            # Load the endpoint definition
            result = self.loader.load_endpoint(endpoint_type, name)
            if result is None:
                logger.error(f"Endpoint not found: {endpoint_type}/{name}")
                return {"status": "error", "message": f"Endpoint not found: {endpoint_type}/{name}"}

            endpoint_file_path, endpoint_def = result

            # Get test definitions
            tests = self._extract_tests(endpoint_def, endpoint_type)
            logger.info(f"Found {len(tests)} tests")

            if not tests:
                return {"status": "ok", "tests_run": 0, "no_tests": True, "tests": []}

            # Extract column names from return schema
            column_names = self._extract_column_names(endpoint_def, endpoint_type)
            logger.info(f"Column names for results: {column_names}")

            # Run each test
            test_results = []
            has_error = False
            has_failed = False

            for test_def in tests:
                test_result = await self._run_single_test(
                    endpoint_type, name, test_def, column_names, cli_user_context, request_headers
                )
                test_results.append(test_result)

                if test_result["status"] == "error":
                    has_error = True
                elif test_result["status"] == "failed":
                    has_failed = True

            # Determine overall status
            status = "ok"
            if has_error:
                status = "error"
            elif has_failed:
                status = "failed"

            logger.info(f"Final test status: {status}")
            return {"status": status, "tests_run": len(tests), "tests": test_results}

        except Exception as e:
            logger.error(f"Error in run_tests_for_endpoint: {str(e)}")
            return {"status": "error", "message": str(e)}

    async def _run_single_test(
        self,
        endpoint_type: str,
        endpoint_name: str,
        test_def: TestDefinition,
        column_names: list[str],
        cli_user_context: UserContext | None,
        request_headers: dict[str, str] | None,
    ) -> dict[str, Any]:
        """Run a single test.

        Args:
            endpoint_type: Type of endpoint
            endpoint_name: Name of the endpoint
            test_def: Test definition
            column_names: Column names for result normalization
            cli_user_context: Optional CLI user context

        Returns:
            Test result dictionary
        """
        start_time = time.time()
        test_name = test_def.get("name", "Unnamed test")
        logger.info(f"Running test: {test_name}")

        try:
            # Convert test arguments to parameters
            params = {}
            for arg in test_def.get("arguments", []):
                params[arg["key"]] = arg["value"]
            logger.info(f"Test parameters: {params}")

            # Determine user context
            test_user_context = self._get_test_user_context(test_def, cli_user_context)

            # Execute the endpoint
            result = await execute_endpoint_with_engine(
                endpoint_type,
                endpoint_name,
                params,
                self.user_config,
                self.site_config,
                self.execution_engine,
                False,  # skip_output_validation
                test_user_context,
                None,  # server_ref
                request_headers,
            )
            logger.info(f"Execution result: {result}")

            # Normalize result for comparison
            normalized_result = normalize_result(result, column_names, endpoint_type)
            logger.info(f"Normalized result: {normalized_result}")

            # Compare with expected results
            passed, error_msg = compare_results(normalized_result, test_def)

            status = "passed" if passed else "failed"
            error = error_msg if not passed else None

            if not passed:
                logger.error(f"Test failed: {error}")

            return {
                "name": test_name,
                "description": test_def.get("description", ""),
                "status": status,
                "error": error,
                "time": time.time() - start_time,
            }

        except Exception as e:
            logger.error(f"Error during test execution: {str(e)}")
            return {
                "name": test_name,
                "description": test_def.get("description", ""),
                "status": "error",
                "error": e,  # Pass the actual exception object
                "time": time.time() - start_time,
            }

    def _extract_tests(self, endpoint_def: EndpointDefinition, endpoint_type: str) -> list[Any]:
        """Extract test definitions from endpoint definition."""
        if endpoint_def is None or not isinstance(endpoint_def, dict):
            return []

        type_key = endpoint_type  # "tool", "resource", or "prompt"
        type_def = endpoint_def.get(type_key)
        if type_def is None or not isinstance(type_def, dict):
            return []

        tests = type_def.get("tests")
        return tests if tests is not None else []

    def _extract_column_names(
        self, endpoint_def: EndpointDefinition, endpoint_type: str
    ) -> list[str]:
        """Extract column names from endpoint return schema."""
        columns = []

        if endpoint_type in ["tool", "resource"]:
            type_def = endpoint_def.get(endpoint_type)
            if type_def and isinstance(type_def, dict) and type_def.get("return"):
                return_def = type_def["return"]
                if return_def and return_def.get("type") == "array" and "items" in return_def:
                    items = return_def["items"]
                    if (
                        isinstance(items, dict)
                        and items.get("type") == "object"
                        and "properties" in items
                    ):
                        properties = items.get("properties", {})
                        if isinstance(properties, dict):
                            columns = list(properties.keys())

        return columns

    def _get_test_user_context(
        self, test_def: TestDefinition, cli_user_context: UserContext | None
    ) -> UserContext | None:
        """Determine user context for test execution."""
        # CLI user context takes precedence
        if cli_user_context is not None:
            logger.info("Using CLI-provided user context")
            return cli_user_context

        # Check for test-defined context
        if "user_context" in test_def:
            test_context_data = test_def["user_context"]
            if test_context_data is not None:
                test_user_context = UserContext(
                    provider="test",  # Special provider for test-defined contexts
                    user_id=test_context_data.get("user_id", "test_user"),
                    username=test_context_data.get("username", "test_user"),
                    email=test_context_data.get("email"),
                    name=test_context_data.get("name"),
                    avatar_url=test_context_data.get("avatar_url"),
                    raw_profile=test_context_data,  # Store full context for policy access
                )
                logger.info(f"Using test-defined user context: {test_context_data}")
                return test_user_context

        return None


def normalize_result(result: Any, column_names: list[str], endpoint_type: str) -> Any:
    """Normalize execution result for comparison with expected result.

    Args:
        result: Raw execution result
        column_names: Column names for tuple-to-dict conversion
        endpoint_type: Type of endpoint

    Returns:
        Normalized result
    """
    # Handle empty results
    if not result:
        return []

    # Handle prompt results
    if endpoint_type == "prompt":
        # Modern prompts return a list of message objects
        if (
            isinstance(result, list)
            and len(result) > 0
            and all(isinstance(msg, dict) and "role" in msg for msg in result)
        ):
            # Find the last assistant message
            for msg in reversed(result):
                if msg.get("role") == "assistant" and "prompt" in msg:
                    assistant_response = msg["prompt"].strip()
                    # Try to parse JSON if it looks like JSON
                    if (
                        assistant_response.startswith("[") and assistant_response.endswith("]")
                    ) or (assistant_response.startswith("{") and assistant_response.endswith("}")):
                        try:
                            return json.loads(assistant_response)
                        except json.JSONDecodeError:
                            pass
                    return assistant_response
            return result

        # Legacy format: Prompts typically return [(messages,)]
        if (
            isinstance(result, list)
            and len(result) == 1
            and isinstance(result[0], tuple)
            and len(result[0]) == 1
        ):
            prompt_result = result[0][0]
            if isinstance(prompt_result, str):
                prompt_result = prompt_result.strip()
                if (prompt_result.startswith("[") and prompt_result.endswith("]")) or (
                    prompt_result.startswith("{") and prompt_result.endswith("}")
                ):
                    try:
                        return json.loads(prompt_result)
                    except json.JSONDecodeError:
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


def compare_results(result: Any, test_def: TestDefinition) -> tuple[bool, str | None]:
    """Compare result with various assertion types in test definition.

    Args:
        result: Actual result
        test_def: Test definition with assertions

    Returns:
        Tuple of (passed, error_message)
    """
    # Exact match with 'result' field
    if "result" in test_def:
        expected = test_def["result"]
        if expected is not None:
            # Convert complex objects for comparison
            def make_serializable(obj: Any) -> Any:
                if isinstance(obj, np.ndarray):
                    return obj.tolist()
                elif isinstance(obj, dict):
                    return {k: make_serializable(v) for k, v in obj.items()}
                elif isinstance(obj, list | tuple):
                    return [make_serializable(item) for item in obj]
                else:
                    return obj

            try:
                serializable_result = make_serializable(result)
                serializable_expected = make_serializable(expected)
                result_json = json.dumps(serializable_result, sort_keys=True)
                expected_json = json.dumps(serializable_expected, sort_keys=True)

                if result_json != expected_json:
                    return (
                        False,
                        f"Result does not match expected output.\nExpected: {expected}\nGot: {result}",
                    )
            except (TypeError, ValueError) as e:
                logger.warning(f"JSON serialization failed, falling back to direct comparison: {e}")
                if result != expected:
                    return (
                        False,
                        f"Result does not match expected output.\nExpected: {expected}\nGot: {result}",
                    )

    # Partial object match with 'result_contains'
    if "result_contains" in test_def:
        expected_contains = test_def["result_contains"]
        if isinstance(result, dict) and isinstance(expected_contains, dict):
            for key, expected_value in expected_contains.items():
                if key not in result:
                    return False, f"Expected field '{key}' not found in result"
                if result[key] != expected_value:
                    return (
                        False,
                        f"Field '{key}' has value {result[key]}, expected {expected_value}",
                    )
        elif isinstance(result, list):
            if isinstance(expected_contains, dict):
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
                    return (
                        False,
                        f"No item in array contains the expected fields: {expected_contains}",
                    )
            else:
                if expected_contains not in result:
                    return False, f"Array does not contain expected value: {expected_contains}"
        else:
            return (
                False,
                f"result_contains assertion requires dict or array result, got {type(result)}",
            )

    # Field exclusion with 'result_not_contains'
    if "result_not_contains" in test_def:
        excluded_fields = test_def["result_not_contains"]
        if isinstance(result, dict) and excluded_fields:
            for field in excluded_fields:
                if field in result:
                    return False, f"Field '{field}' should not be present in result but was found"
        else:
            return False, f"result_not_contains assertion requires dict result, got {type(result)}"

    # Array contains specific item with 'result_contains_item'
    if "result_contains_item" in test_def:
        expected_item = test_def["result_contains_item"]
        if not isinstance(result, list):
            return (
                False,
                f"result_contains_item assertion requires array result, got {type(result)}",
            )

        found = False
        for item in result:
            if item == expected_item:
                found = True
                break
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
            result_str = str(result)
        else:
            result_str = result

        if expected_text not in result_str:
            return False, f"Result does not contain expected text: '{expected_text}'"

    # If no assertions specified, test passes
    return True, None
