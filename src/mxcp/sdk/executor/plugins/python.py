"""Python executor plugin for Python code execution.

This plugin handles Python code execution with full lifecycle management,
including runtime hooks, context management, and module loading.

Example usage:
    >>> from mxcp.sdk.executor import ExecutionEngine, ExecutionContext
    >>> from mxcp.sdk.executor.plugins import PythonExecutor
    >>> from pathlib import Path
    >>>
    >>> # Create Python executor
    >>> executor = PythonExecutor(repo_root=Path("/path/to/repo"))
    >>>
    >>> # Create engine and register executor
    >>> engine = ExecutionEngine()
    >>> engine.register_executor(executor)
    >>>
    >>> # Execute inline Python code
    >>> result = await engine.execute(
    ...     language="python",
    ...     source_code="return sum(data)",
    ...     params={"data": [1, 2, 3, 4, 5]}
    ... )
    >>>
    >>> # Execute Python file
    >>> result = await engine.execute(
    ...     language="python",
    ...     source_code="data_analysis.py",
    ...     params={"dataset": "sales_data"}
    ... )
    >>>
    >>> # Execute with validation
    >>> input_schema = [{"name": "numbers", "type": "array", "items": {"type": "number"}}]
    >>> output_schema = {"type": "number"}
    >>> result = await engine.execute(
    ...     language="python",
    ...     source_code="return statistics.mean(numbers)",
    ...     params={"numbers": [1, 2, 3, 4, 5]},
    ...     input_schema=input_schema,
    ...     output_schema=output_schema
    ... )
"""

import ast
import asyncio
import hashlib
import inspect
import logging
import sys
import tempfile
import typing
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np
import pandas as pd
from pydantic import BaseModel, TypeAdapter, ValidationError

from mxcp.sdk.telemetry import (
    decrement_gauge,
    increment_gauge,
    record_counter,
    traced_operation,
)

from ..context import ExecutionContext
from ..interfaces import ExecutorPlugin

if TYPE_CHECKING:
    from .python_plugin.loader import PythonEndpointLoader

logger = logging.getLogger(__name__)


class PythonExecutor(ExecutorPlugin):
    """Executor plugin for Python code execution.

    Handles Python code execution with full lifecycle management,
    including runtime hooks, context management, and module loading.

    Example usage:
        >>> from mxcp.sdk.executor.plugins import PythonExecutor
        >>> from mxcp.sdk.executor import ExecutionContext
        >>> from pathlib import Path
        >>>
        >>> # Create executor
        >>> executor = PythonExecutor(repo_root=Path("/path/to/repo"))
        >>>
        >>> # Execute inline Python code
        >>> exec_context = ExecutionContext(user_context=user_context)
        >>> result = await executor.execute(
        ...     "return sum(data)",
        ...     {"data": [1, 2, 3, 4, 5]},
        ...     exec_context
        ... )
        >>>
        >>> # Execute Python file
        >>> result = await executor.execute(
        ...     "data_analysis.py",
        ...     {"dataset": "sales_data"},
        ...     exec_context
        ... )
        >>>
        >>> # Validate Python syntax
        >>> is_valid = executor.validate_source("return 42")
        >>>
        >>> # Lifecycle management
        >>> executor.shutdown()
    """

    def __init__(self, repo_root: Path | None = None):
        """Initialize Python executor.

        Creates Python loader, preloads all modules to register hooks,
        and runs init hooks to complete initialization.

        Args:
            repo_root: Repository root directory. If None, will use current working directory.
        """
        self.repo_root = repo_root
        if not self.repo_root:
            logger.warning("No repo root provided, using current working directory")
            self.repo_root = Path.cwd()

        # Initialize Python loader immediately
        from .python_plugin.loader import PythonEndpointLoader

        self._loader = PythonEndpointLoader(self.repo_root)

        # Preload all Python modules to register hooks, then run init hooks
        # This ensures complete Python runtime initialization
        try:
            # First, preload all Python modules which registers the hooks
            logger.info("Preloading Python modules to register hooks...")
            self._loader.preload_all_modules()

            # Then run init hooks on the now-registered hooks
            from mxcp.runtime import run_init_hooks

            logger.info("Running init hooks after module preload...")
            run_init_hooks()
            logger.info("Init hooks completed successfully")
        except ImportError:
            logger.debug("Runtime module not available for init hooks")
        except Exception as e:
            logger.warning(f"Init hooks failed during Python executor initialization: {e}")
            # Don't fail executor creation if hooks fail

        logger.info("Python executor initialized")

    @property
    def language(self) -> str:
        """The language this executor handles."""
        return "python"

    @property
    def loader(self) -> "PythonEndpointLoader":
        """Get the Python module loader."""
        if not self._loader:
            raise RuntimeError("Python loader not initialized")
        return self._loader

    def shutdown(self) -> None:
        """Shut down the Python executor.

        This is where shutdown hooks should run - once per engine shutdown.
        """
        logger.info("Python executor shutting down - running shutdown hooks")

        # Run shutdown hooks
        try:
            from mxcp.runtime import run_shutdown_hooks

            logger.info("Running engine-level shutdown hooks...")
            run_shutdown_hooks()
        except ImportError:
            logger.warning("Runtime module not available for shutdown hooks")
        except Exception as e:
            logger.error(f"Failed to run shutdown hooks: {e}")

        # Clean up loader
        if self._loader:
            self._loader.cleanup()

        logger.info("Python executor shutdown complete")

    def validate_source(self, source_code: str) -> bool:
        """Validate Python source code syntax.

        Args:
            source_code: Python code to validate

        Returns:
            True if valid, False otherwise
        """
        try:
            # Check if it's a file path
            if self._is_file_path(source_code):
                if self.repo_root:
                    return (self.repo_root / "python" / source_code).exists()
                return False

            # Validate inline code syntax
            compile(source_code, "<string>", "exec")
            return True
        except SyntaxError as e:
            logger.debug(f"Python syntax validation failed: {e}")
            return False
        except Exception as e:
            logger.debug(f"Python validation failed: {e}")
            return False

    def extract_parameters(self, source_code: str) -> list[str]:
        """Extract parameter names from Python source code.

        Args:
            source_code: Python code to analyze

        Returns:
            List of parameter names found in the Python code
        """
        try:
            # Check if it's a file path
            if self._is_file_path(source_code):
                return self._extract_parameters_from_file(source_code)
            else:
                return self._extract_parameters_from_inline(source_code)
        except Exception as e:
            logger.debug(f"Python parameter extraction failed: {e}")
            return []

    def _extract_parameters_from_file(self, file_path: str) -> list[str]:
        """Extract parameters from a Python file."""
        try:
            # Parse file path and function name
            if ":" in file_path:
                actual_file_path, function_name = file_path.split(":", 1)
            else:
                actual_file_path = file_path
                function_name = None

            # Load the module
            module = self.loader.load_python_module(Path(actual_file_path))

            # Find the target function
            if function_name:
                if hasattr(module, function_name):
                    func = getattr(module, function_name)
                else:
                    return []
            else:
                # Find main function or first callable
                file_name = Path(actual_file_path).stem
                func = None

                if hasattr(module, "main"):
                    func = module.main
                elif hasattr(module, file_name):
                    func = getattr(module, file_name)
                else:
                    # Find any callable function
                    functions = [
                        name
                        for name in dir(module)
                        if callable(getattr(module, name)) and not name.startswith("_")
                    ]
                    if functions:
                        func = getattr(module, functions[0])

                if not func:
                    return []

            # Extract function signature
            if callable(func):
                sig = inspect.signature(func)
                return list(sig.parameters.keys())

            return []

        except Exception as e:
            logger.debug(f"Failed to extract parameters from file {file_path}: {e}")
            return []

    def _extract_parameters_from_inline(self, source_code: str) -> list[str]:
        """Extract parameters from inline Python code."""
        try:
            # Handle return statements by wrapping in a function
            if source_code.strip().startswith("return "):
                # For simple return expressions, analyze what variables are referenced
                return_expr = source_code.strip()[7:]  # Remove 'return '
                expr_tree = ast.parse(return_expr, mode="eval")

                # Find all variable names used in the expression
                params = []
                for node in ast.walk(expr_tree):
                    if (
                        isinstance(node, ast.Name)
                        and isinstance(node.ctx, ast.Load)
                        and node.id not in ["pd", "np", "pandas", "numpy"]
                        and node.id not in params
                    ):
                        params.append(node.id)
                return params
            else:
                # For more complex code, try to find function definitions
                tree = ast.parse(source_code)

                # Look for function definitions
                for node in ast.walk(tree):
                    if isinstance(node, ast.FunctionDef):
                        # Return parameters of the first function found
                        return [arg.arg for arg in node.args.args]

                # If no function found, analyze variable references
                params = []
                for node in ast.walk(tree):
                    if (
                        isinstance(node, ast.Name)
                        and isinstance(node.ctx, ast.Load)
                        and node.id not in ["pd", "np", "pandas", "numpy"]
                        and node.id not in params
                    ):
                        params.append(node.id)
                return params

        except Exception as e:
            logger.debug(f"Failed to extract parameters from inline code: {e}")
            return []

    async def execute(
        self, source_code: str, params: dict[str, Any], context: ExecutionContext
    ) -> Any:
        """Execute Python source code with parameters.

        Args:
            source_code: Python code to execute or file path
            params: Parameter values
            context: Runtime context

        Returns:
            Execution result
        """
        # Determine execution type
        is_file = self._is_file_path(source_code)
        execution_type = "file" if is_file else "inline"

        # For files, extract just the filename for telemetry
        if is_file:
            # Remove any function suffix for the span name
            display_name = source_code.split(":")[-1] if ":" in source_code else source_code
            # Get just the filename without path
            if "/" in display_name:
                display_name = display_name.split("/")[-1]
        else:
            # For inline code, hash it for privacy
            display_name = f"inline_{hashlib.sha256(source_code.encode()).hexdigest()[:8]}"

        # Track concurrent executions
        increment_gauge(
            "mxcp.python.concurrent_executions",
            attributes={"type": execution_type},
            description="Currently running Python executions",
        )

        try:
            with traced_operation(
                "mxcp.python.execute",
                attributes={
                    "mxcp.python.type": execution_type,
                    "mxcp.python.name": display_name,
                    "mxcp.python.params.count": len(params) if params else 0,
                },
            ):
                try:
                    # Check if it's a file path or inline code
                    logger.info(f"Executing Python source: {repr(source_code[:100])}...")
                    if is_file:
                        logger.info("Detected as file path, using _execute_from_file")
                        result = await self._execute_from_file(source_code, params, context)
                    else:
                        logger.info("Detected as inline code, using _execute_inline")
                        result = await self._execute_inline(source_code, params, context)

                    # Record success metrics
                    record_counter(
                        "mxcp.python.executions_total",
                        attributes={"type": execution_type, "status": "success"},
                        description="Total Python executions",
                    )

                    return result
                except (ImportError, SyntaxError) as e:
                    # These are executor-level errors that should be wrapped
                    logger.error(f"Python execution failed: {e}")
                    # Record error metrics
                    record_counter(
                        "mxcp.python.executions_total",
                        attributes={"type": execution_type, "status": "error"},
                        description="Total Python executions",
                    )
                    raise RuntimeError(f"Failed to execute Python code: {e}") from e
                except Exception:
                    # Let other exceptions (FileNotFoundError, AttributeError, runtime errors) propagate
                    # But still record metrics
                    record_counter(
                        "mxcp.python.executions_total",
                        attributes={"type": execution_type, "status": "error"},
                        description="Total Python executions",
                    )
                    raise
        finally:
            # Always decrement concurrent executions
            decrement_gauge(
                "mxcp.python.concurrent_executions",
                attributes={"type": execution_type},
                description="Currently running Python executions",
            )

    def _is_file_path(self, source_code: str) -> bool:
        """Check if source code is a file path."""
        # Simple heuristic: if it's a single line ending with .py or .py:function, treat as file
        stripped = source_code.strip()
        return (
            "\n" not in stripped
            and (stripped.endswith(".py") or ".py:" in stripped)
            and not stripped.startswith("return")
        )

    async def _execute_from_file(
        self, file_path: str, params: dict[str, Any], context: ExecutionContext
    ) -> Any:
        """Execute Python code from a file."""
        try:
            # Parse file path and function name (e.g., "python/test_module.py:multiply")
            if ":" in file_path:
                actual_file_path, function_name = file_path.split(":", 1)
            else:
                actual_file_path = file_path
                function_name = None

            # Load the module using the correct method name
            module = self.loader.load_python_module(Path(actual_file_path))

            # Determine function to call
            if function_name:
                # Specific function requested
                if hasattr(module, function_name):
                    func = getattr(module, function_name)
                else:
                    raise AttributeError(
                        f"Function '{function_name}' not found in {actual_file_path}"
                    )
            else:
                # Get the main function (assume it's named 'main' or matches the file name)
                file_name = Path(actual_file_path).stem
                fallback_function_name = "main"  # Default to 'main'

                # Try to find the function
                if hasattr(module, fallback_function_name):
                    func = getattr(module, fallback_function_name)
                elif hasattr(module, file_name):
                    func = getattr(module, file_name)
                else:
                    # Look for any callable function that's not a built-in
                    functions = [
                        name
                        for name in dir(module)
                        if callable(getattr(module, name)) and not name.startswith("_")
                    ]
                    if functions:
                        func = getattr(module, functions[0])
                    else:
                        raise AttributeError(f"No callable function found in {actual_file_path}")

            # Execute the function
            return await self._execute_function(func, params, context)

        except Exception as e:
            logger.error(f"Failed to execute file {file_path}: {e}")
            raise

    async def _execute_inline(
        self, source_code: str, params: dict[str, Any], context: ExecutionContext
    ) -> Any:
        """Execute inline Python code."""
        try:
            # Create execution namespace with parameters
            namespace = params.copy()

            # Add common imports
            namespace.update(
                {
                    "pd": pd,
                    "np": np,
                    "pandas": pd,
                    "numpy": np,
                }
            )

            # Handle return statements by wrapping in a function
            if source_code.strip().startswith("return "):
                # Extract the return expression
                return_expr = source_code.strip()[7:]  # Remove 'return '
                wrapped_code = f"__result = {return_expr}"
            else:
                wrapped_code = source_code

            # Execute in a temporary file to get proper error reporting
            with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
                f.write(wrapped_code)
                f.flush()

                # Execute the code
                exec(compile(wrapped_code, f.name, "exec"), namespace)

            # Check for explicit result variables first
            if "__result" in namespace:
                return namespace["__result"]
            elif "result" in namespace:
                return namespace["result"]

            # If no explicit result, look for callable functions and try to find one to execute
            callables = {
                name: obj
                for name, obj in namespace.items()
                if callable(obj)
                and not name.startswith("_")
                and name not in {"pd", "np", "pandas", "numpy"}
            }

            if callables:
                # Try to find a function whose signature matches the parameters
                for _func_name, func in callables.items():
                    try:
                        sig = inspect.signature(func)
                        # Check if the function parameters match our input parameters
                        func_params = list(sig.parameters.keys())
                        if set(params.keys()).issubset(set(func_params)) or len(func_params) == 0:
                            # Call the function
                            return await self._execute_function(func, params, context)
                    except (ValueError, TypeError, AttributeError):
                        # Only catch errors related to introspection, not runtime errors
                        continue

            # No suitable function found
            raise ValueError("No suitable function found in inline code")

        except Exception as e:
            logger.error(f"Failed to execute inline code: {e}")
            raise

    async def _execute_function(
        self, func: Callable[..., Any], params: dict[str, Any], context: ExecutionContext
    ) -> Any:
        """Execute a function with parameters."""

        try:
            from ..context import reset_execution_context, set_execution_context

            # Convert parameters based on function signature
            converted_params = self._convert_parameters(func, params)

            # Handle validation errors
            if isinstance(converted_params, dict) and "__validation_errors" in converted_params:
                # Convert structured errors to string for backward compatibility
                # TODO: In future, return structured errors directly for better UI
                error_parts = []
                for param_name, param_errors in converted_params["__validation_errors"].items():
                    error_details = [f"{err['field']}: {err['message']}" for err in param_errors]
                    error_parts.append(f"Invalid {param_name}: {', '.join(error_details)}")
                return "; ".join(error_parts)

            # Check if function is async
            if asyncio.iscoroutinefunction(func):
                # For async functions, set context and let contextvars propagate it
                context_token = set_execution_context(context)
                try:
                    result = await func(**converted_params)
                finally:
                    reset_execution_context(context_token)
            else:
                # For sync functions, use copy_context to propagate all context variables to thread
                def sync_function_wrapper() -> Any:
                    from ..context import reset_execution_context, set_execution_context

                    thread_token = set_execution_context(context)
                    try:
                        return func(**converted_params)
                    finally:
                        reset_execution_context(thread_token)

                # Copy current context (including auth context) and run in thread pool
                import contextvars

                ctx = contextvars.copy_context()
                loop = asyncio.get_event_loop()
                result = await loop.run_in_executor(None, ctx.run, sync_function_wrapper)

            return result

        except Exception as e:
            logger.error(f"Function execution failed: {e}")
            raise

    def _convert_parameters(
        self, func: Callable[..., Any], params: dict[str, Any]
    ) -> dict[str, Any]:
        """Convert parameters based on function signature with comprehensive type support.

        Features:
        - Uses TypeAdapter for robust type conversion and validation
        - Supports forward references with proper module namespace context
        - Collects structured validation errors per parameter for better UI
        - Uses signature binding for proper parameter handling
        - Handles **kwargs functions specially to maintain compatibility

        Args:
            func: The function to call
            params: Raw parameter dictionary

        Returns:
            Converted parameters dictionary, or dict with __validation_errors on failure.
            The __validation_errors contains structured per-parameter error details.
        """

        # Get function signature
        sig = inspect.signature(func)

        # Resolve type hints with proper module context for forward references
        try:
            globalns = getattr(func, "__globals__", {})
            # Use the defining module's namespace for localns (handles more forward-ref edge cases)
            mod = sys.modules.get(getattr(func, "__module__", ""), None)
            localns = vars(mod) if mod else globalns
            type_hints = typing.get_type_hints(
                func, globalns=globalns, localns=localns, include_extras=True
            )
        except (NameError, AttributeError, TypeError) as e:
            logger.debug(f"Failed to resolve type hints for {func.__name__}: {e}")
            type_hints = {}

        # Use signature binding for proper parameter mapping, but handle **kwargs specially
        has_var_keyword = any(
            p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()
        )

        if has_var_keyword:
            # For functions with **kwargs, use direct parameter mapping to maintain compatibility
            bound_params = params
        else:
            # For regular functions, use bind_partial for proper parameter handling
            try:
                bound_args = sig.bind_partial(**params)
                bound_args.apply_defaults()
                bound_params = bound_args.arguments
            except TypeError as e:
                # If binding fails, fall back to direct parameter mapping
                logger.debug(f"Parameter binding failed for {func.__name__}: {e}")
                bound_params = params

        converted_params = {}
        validation_errors = {}  # Dict to store per-parameter error details

        for param_name, param_value in bound_params.items():
            try:
                # Get resolved type hint, fall back to raw annotation if available
                param_type = type_hints.get(param_name)
                if param_type is None and param_name in sig.parameters:
                    param_type = sig.parameters[param_name].annotation

                # Skip if no type annotation or annotation is Any/object
                if (
                    param_type is None
                    or param_type == inspect.Parameter.empty
                    or param_type in (typing.Any, object)
                ):
                    converted_params[param_name] = param_value
                    continue

                # Convert the parameter value based on its type
                converted_value = self._convert_parameter_value(param_name, param_value, param_type)
                converted_params[param_name] = converted_value

            except ValidationError as ve:
                # Collect structured validation errors for this parameter
                param_errors = []
                for error in ve.errors():
                    param_errors.append(
                        {
                            "field": (
                                ".".join(str(loc) for loc in error["loc"])
                                if error["loc"]
                                else param_name
                            ),
                            "message": error["msg"],
                            "type": error["type"],
                        }
                    )
                validation_errors[param_name] = param_errors

            except Exception as e:
                # Log unexpected errors with stack trace and fail validation
                logger.exception(f"Unexpected error converting parameter '{param_name}'")
                validation_errors[param_name] = [
                    {
                        "field": param_name,
                        "message": f"Unexpected conversion error: {str(e)}",
                        "type": "unexpected_error",
                    }
                ]

        # Return structured validation errors if any occurred
        if validation_errors:
            logger.error(
                f"Parameter validation failed for parameters: {list(validation_errors.keys())}"
            )
            return {"__validation_errors": validation_errors}

        return converted_params

    def _convert_parameter_value(self, param_name: str, param_value: Any, param_type: Any) -> Any:
        """Convert a single parameter value based on its type annotation.

        Uses TypeAdapter to handle all type conversions uniformly:
        - Direct models: User
        - Optional models: Optional[User], User | None
        - Container types: list[User], dict[str, User], etc.
        - Complex nested types: dict[str, list[User]]
        - Non-model types: TypedDicts, dataclasses, primitives

        Args:
            param_name: Parameter name (for logging/errors)
            param_value: Raw parameter value
            param_type: Resolved type annotation

        Returns:
            Converted parameter value

        Raises:
            ValidationError: If pydantic validation fails
        """

        # Fast path: if value is already a BaseModel instance, keep it as-is
        if isinstance(param_value, BaseModel):
            logger.debug(f"Parameter '{param_name}' is already a BaseModel instance")
            return param_value

        # Try to create TypeAdapter for the parameter type
        try:
            adapter = TypeAdapter(param_type)
            logger.debug(f"Converting parameter '{param_name}' using TypeAdapter for {param_type}")
            return adapter.validate_python(param_value)
        except (TypeError, ValueError) as e:
            # TypeAdapter couldn't be created or type doesn't need validation
            # This happens for types that don't require special handling
            logger.debug(f"No TypeAdapter needed for parameter '{param_name}': {e}")
            return param_value
