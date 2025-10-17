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
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np
import pandas as pd

from mxcp.sdk.telemetry import (
    decrement_gauge,
    increment_gauge,
    record_counter,
    traced_operation,
)

from ..context import ExecutionContext
from ..interfaces import ExecutorPlugin, ValidationResult

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

    def validate_source(self, source_code: str) -> ValidationResult:
        """Validate Python source code syntax.

        Args:
            source_code: Python code to validate

        Returns:
            ValidationResult with is_valid flag and optional error message
        """
        try:
            # Check if it's a file path
            if self._is_file_path(source_code):
                if self.repo_root:
                    file_exists = (self.repo_root / "python" / source_code).exists()
                    if not file_exists:
                        return ValidationResult(
                            is_valid=False,
                            error_message=f"Python file not found: python/{source_code}",
                        )
                    return ValidationResult(is_valid=True)
                return ValidationResult(
                    is_valid=False, error_message="No repository root configured"
                )

            # Validate inline code syntax
            compile(source_code, "<string>", "exec")
            return ValidationResult(is_valid=True)
        except SyntaxError as e:
            error_message = f"Syntax error at line {e.lineno}: {e.msg}"
            logger.debug(f"Python syntax validation failed: {error_message}")
            return ValidationResult(is_valid=False, error_message=error_message)
        except Exception as e:
            error_message = str(e)
            logger.debug(f"Python validation failed: {error_message}")
            return ValidationResult(is_valid=False, error_message=error_message)

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

    def prepare_context(self, context: ExecutionContext) -> None:
        """Prepare the execution context with executor-specific resources.

        This method is called before any execution to allow executors
        to add their resources to the context.

        Args:
            context: The execution context to prepare
        """
        pass

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

            # Check if function is async
            if asyncio.iscoroutinefunction(func):
                # For async functions, set context and let contextvars propagate it
                context_token = set_execution_context(context)
                try:
                    result = await func(**params)
                finally:
                    reset_execution_context(context_token)
            else:
                # For sync functions, use copy_context to propagate all context variables to thread
                def sync_function_wrapper() -> Any:
                    from ..context import reset_execution_context, set_execution_context

                    thread_token = set_execution_context(context)
                    try:
                        return func(**params)
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
