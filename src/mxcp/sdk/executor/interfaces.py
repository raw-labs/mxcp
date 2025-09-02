"""Core interfaces for MXCP executor system.

This module provides the core interfaces for the MXCP executor system, which
handles execution of source code in different languages (SQL, Python, etc.)
with proper validation and lifecycle management.

Example usage:
    >>> from mxcp.sdk.executor import ExecutionEngine, ExecutionContext
    >>> from mxcp.sdk.executor.plugins import DuckDBExecutor, PythonExecutor
    >>>
    >>> # Create engine and register executors
    >>> engine = ExecutionEngine(strict=False)
    >>> engine.register_executor(DuckDBExecutor())
    >>> engine.register_executor(PythonExecutor())
    >>>
    >>> # Execute SQL with validation (per-request execution context)
    >>> exec_context = ExecutionContext()
    >>> exec_context.set("duckdb_session", duckdb_session)
    >>> exec_context.set("site_config", site_config)
    >>> result = await engine.execute(
    ...     language="sql",
    ...     source_code="SELECT * FROM table LIMIT $limit",
    ...     params={"limit": 5},
    ...     context=exec_context
    ... )
    >>>
    >>> # Shutdown (shutdown hooks run here)
    >>> engine.shutdown()
"""

import contextlib
import threading
from abc import ABC, abstractmethod
from typing import Any

from mxcp.sdk.telemetry import (
    decrement_gauge,
    get_current_span,
    increment_gauge,
    record_counter,
    traced_operation,
)
from mxcp.sdk.validator import TypeValidator

from .context import ExecutionContext


class ExecutorPlugin(ABC):
    """Base interface for execution plugins.

    Each plugin handles a specific execution language/environment
    (e.g., SQL, Python, R) and manages its own internal resources
    (database sessions, plugins, locking, etc.)

    Executors are fully constructed and ready to use after instantiation.
    Higher-level components handle lifecycle management by creating/destroying instances.

    Example implementation:
        >>> from mxcp.sdk.executor.interfaces import ExecutorPlugin
        >>> from mxcp.sdk.executor import ExecutionContext
        >>>
        >>> class CustomExecutor(ExecutorPlugin):
        ...     def __init__(self, config):
        ...         # Create all internal resources in constructor
        ...         self._internal_session = self._create_session(config)
        ...         self._internal_plugins = self._load_plugins(config)
        ...
        ...     @property
        ...     def language(self) -> str:
        ...         return "custom"
        ...
        ...     async def execute(self, source_code: str, params: Dict[str, Any],
        ...                     context: ExecutionContext) -> Any:
        ...         # Use internal session and plugins with dynamic user context
        ...         return self._internal_session.execute(source_code, params, context)
        ...
        ...     def shutdown(self) -> None:
        ...         # Clean up internal resources
        ...         self._internal_session.close()
    """

    @property
    @abstractmethod
    def language(self) -> str:
        """Return the language this executor handles (e.g., 'sql', 'python')."""
        pass

    @abstractmethod
    async def execute(
        self, source_code: str, params: dict[str, Any], context: ExecutionContext
    ) -> Any:
        """Execute source code with the given parameters.

        Args:
            source_code: The source code to execute
            params: Parameters for the execution
            context: Execution context with user info and runtime state

        Returns:
            The result of the execution
        """
        pass

    @abstractmethod
    def shutdown(self) -> None:
        """Shut down the executor and clean up resources.

        This is called when the executor is being stopped.
        Executors should run shutdown hooks and clean up their internal resources here.
        """
        pass

    @abstractmethod
    def validate_source(self, source_code: str) -> bool:
        """Validate source code syntax without execution.

        Args:
            source_code: The source code to validate

        Returns:
            True if valid, False otherwise
        """
        pass

    @abstractmethod
    def extract_parameters(self, source_code: str) -> list[str]:
        """Extract parameter names from source code.

        Args:
            source_code: The source code to analyze

        Returns:
            List of parameter names found in the source code
        """
        pass

    @abstractmethod
    def prepare_context(self, context: ExecutionContext) -> None:
        """Prepare the execution context with executor-specific resources.

        This method is called before any execution to allow executors
        to add their resources to the context.

        Args:
            context: The execution context to prepare
        """
        # Default implementation does nothing
        pass


class ExecutionEngine:
    """Central execution engine that manages multiple executor plugins.

    The engine handles:
    - Registration of executor plugins for different languages
    - Engine lifecycle management (startup/shutdown)
    - Input/output validation using mxcp.sdk.validator
    - Routing execution requests to appropriate executors

    Executors are ready to use immediately after registration.
    Call startup() to initialize engine-level context and run init hooks.

    Example usage:
        >>> from mxcp.sdk.executor import ExecutionEngine
        >>> from mxcp.sdk.executor import ExecutionContext
        >>> from mxcp.sdk.executor.plugins import DuckDBExecutor, PythonExecutor
        >>>
        >>> # Create engine and register executors
        >>> engine = ExecutionEngine(strict=False)
        >>> engine.register_executor(DuckDBExecutor(...))
        >>> engine.register_executor(PythonExecutor(...))
        >>>
        >>> # Execute code with per-request context
        >>> exec_context = ExecutionContext(user_context=user_context)
        >>> exec_context.set("duckdb_session", duckdb_session)
        >>> exec_context.set("site_config", site_config)
        >>> result = await engine.execute(
        ...     language="python",
        ...     source_code="return x + y",
        ...     params={"x": 1, "y": 2},
        ...     context=exec_context
        ... )
        >>>
        >>> # Shutdown engine (shutdown hooks run here)
        >>> engine.shutdown()
    """

    def __init__(self, strict: bool = False):
        """Initialize the execution engine.

        Args:
            strict: If True, validation errors will raise exceptions
        """
        self._executors: dict[str, ExecutorPlugin] = {}
        self._strict = strict
        self._lock = threading.Lock()

    def register_executor(self, executor: ExecutorPlugin) -> None:
        """Register an executor plugin.

        Args:
            executor: The executor plugin to register (must be fully constructed)

        Raises:
            ValueError: If an executor for this language is already registered
        """
        language = executor.language
        if language in self._executors:
            raise ValueError(f"Executor for language '{language}' is already registered")
        self._executors[language] = executor

    def shutdown(self) -> None:
        """Shut down all registered executors.

        This calls shutdown() on all registered executors.
        This is where shutdown hooks should run.
        """
        with self._lock:
            for executor in self._executors.values():
                executor.shutdown()
            self._executors.clear()

    async def execute(
        self,
        language: str,
        source_code: str,
        params: dict[str, Any],
        context: ExecutionContext,
        input_schema: list[dict[str, Any]] | None = None,
        output_schema: dict[str, Any] | None = None,
    ) -> Any:
        """Execute source code in the specified language.

        Args:
            language: The programming language
            source_code: The source code to execute
            params: Parameters for the execution
            context: Execution context with user info and runtime state
            input_schema: Optional input validation schema
            output_schema: Optional output validation schema

        Returns:
            The result of the execution

        Raises:
            ValueError: If language is not supported or validation fails
        """
        # Track concurrent executions at the engine level
        increment_gauge(
            "mxcp.execution.concurrent",
            attributes={"language": language},
            description="Currently running executions across all languages",
        )

        try:
            # Start telemetry span for execution
            with traced_operation(
                "mxcp.execution_engine.execute",
                attributes={
                    "mxcp.language": language,
                    "mxcp.params.count": len(params) if params else 0,
                    "mxcp.has_input_schema": input_schema is not None,
                    "mxcp.has_output_schema": output_schema is not None,
                },
            ):
                if language not in self._executors:
                    available = list(self._executors.keys())
                    # Record failure before raising
                    record_counter(
                        "mxcp.execution.total",
                        attributes={
                            "language": language,
                            "status": "error",
                            "error": "unsupported_language",
                        },
                        description="Total executions across all languages",
                    )
                    raise ValueError(f"Language '{language}' not supported. Available: {available}")

                # Validate input parameters if schema provided
                if input_schema:
                    with traced_operation("mxcp.validation.input"):
                        validator = TypeValidator.from_dict(
                            {"input": {"parameters": input_schema}}, strict=self._strict
                        )
                        params = validator.validate_input(params)
                        validation_span = get_current_span()
                        if validation_span:
                            validation_span.set_attribute("mxcp.validation.passed", True)

                # Prepare context with all executor resources
                for _exec_lang, exec_instance in self._executors.items():
                    exec_instance.prepare_context(context)

                # Execute the code (this will create a child span in the executor)
                executor = self._executors[language]
                result = await executor.execute(source_code, params, context)

                # Validate output if schema provided
                if output_schema:
                    with traced_operation("mxcp.validation.output"):
                        validator = TypeValidator.from_dict(
                            {"output": output_schema}, strict=self._strict
                        )
                        result = validator.validate_output(result)
                        validation_span = get_current_span()
                        if validation_span:
                            validation_span.set_attribute("mxcp.validation.passed", True)

                # Record success metrics
                record_counter(
                    "mxcp.execution.total",
                    attributes={"language": language, "status": "success"},
                    description="Total executions across all languages",
                )

                # Add result info to current span if available
                span = get_current_span()
                if span and hasattr(result, "__len__"):
                    with contextlib.suppress(Exception):
                        span.set_attribute("mxcp.result.count", len(result))

                return result
        except Exception:
            # Record error metrics
            record_counter(
                "mxcp.execution.total",
                attributes={"language": language, "status": "error"},
                description="Total executions across all languages",
            )
            raise
        finally:
            # Always decrement concurrent executions
            decrement_gauge(
                "mxcp.execution.concurrent",
                attributes={"language": language},
                description="Currently running executions across all languages",
            )

    def validate_source(self, language: str, source_code: str) -> bool:
        """Validate source code syntax without execution.

        Args:
            language: The programming language
            source_code: The source code to validate

        Returns:
            True if valid, False otherwise

        Raises:
            ValueError: If language is not supported
        """
        if language not in self._executors:
            available = list(self._executors.keys())
            raise ValueError(f"Language '{language}' not supported. Available: {available}")

        executor = self._executors[language]
        return executor.validate_source(source_code)

    def extract_parameters(self, language: str, source_code: str) -> list[str]:
        """Extract parameter names from source code.

        Args:
            language: The programming language
            source_code: The source code to analyze

        Returns:
            List of parameter names found in the source code

        Raises:
            ValueError: If language is not supported
        """
        if language not in self._executors:
            available = list(self._executors.keys())
            raise ValueError(f"Language '{language}' not supported. Available: {available}")

        executor = self._executors[language]
        if hasattr(executor, "extract_parameters"):
            return executor.extract_parameters(source_code)
        else:
            # Fallback for executors that don't implement parameter extraction
            return []
