"""
Python endpoint loader for MXCP executor plugin.

This module handles loading Python files as modules for endpoint execution.
This is a cloned version of the loader for the executor plugin system.
"""
import sys
import importlib
import importlib.util
from pathlib import Path
from typing import Dict, Any, Callable, Optional, Set
import logging
import hashlib

logger = logging.getLogger(__name__)


class PythonEndpointLoader:
    """Loads and manages Python modules for endpoints."""
    
    def __init__(self, repo_root: Path):
        """
        Initialize the Python endpoint loader.
        
        Args:
            repo_root: The repository root directory (where mxcp-site.yml is located)
        """
        self.repo_root = repo_root
        self.python_dir = repo_root / "python"
        self._loaded_modules: Dict[str, Any] = {}
        self._module_paths: Set[str] = set()  # Track added paths
        self._ensure_python_path()
        
    def _ensure_python_path(self):
        """Add python/ directory and repo root to sys.path if not already there"""
        # Add python/ directory
        python_path = str(self.python_dir.resolve())
        if python_path not in sys.path and self.python_dir.exists():
            sys.path.insert(0, python_path)
            self._module_paths.add(python_path)
            logger.info(f"Added {python_path} to Python path")
            
        # Also ensure the repo root is in path (for plugin compatibility)
        repo_path = str(self.repo_root.resolve())
        if repo_path not in sys.path:
            sys.path.insert(0, repo_path)
            self._module_paths.add(repo_path)
            logger.info(f"Added {repo_path} to Python path")
            
    def load_python_module(self, file_path: Path) -> Any:
        """
        Load a Python module from file path.
        
        Args:
            file_path: Path to the Python file (can be relative or absolute)
            
        Returns:
            The loaded Python module
            
        Raises:
            FileNotFoundError: If the file doesn't exist
            ImportError: If the module cannot be imported
        """
        # Resolve to absolute path
        if not file_path.is_absolute():
            # If relative, assume relative to repo root
            file_path = self.repo_root / file_path
            
        abs_path = file_path.resolve()
        
        # Check if file exists
        if not abs_path.exists():
            raise FileNotFoundError(f"Python file not found: {abs_path}")
            
        # Check cache
        cache_key = str(abs_path)
        if cache_key in self._loaded_modules:
            logger.debug(f"Returning cached module for {abs_path}")
            return self._loaded_modules[cache_key]
            
        # Determine module name
        module_name = self._get_module_name(abs_path)
        
        # Check if module already in sys.modules (could be imported elsewhere)
        if module_name in sys.modules:
            logger.debug(f"Module {module_name} already in sys.modules")
            module = sys.modules[module_name]
            self._loaded_modules[cache_key] = module
            return module
            
        # Load the module
        logger.info(f"Loading Python module: {module_name} from {abs_path}")
        try:
            spec = importlib.util.spec_from_file_location(module_name, abs_path)
            if spec is None or spec.loader is None:
                raise ImportError(f"Failed to create module spec for {abs_path}")
                
            module = importlib.util.module_from_spec(spec)
            
            # Add to sys.modules before executing (allows self-imports)
            sys.modules[module_name] = module
            
            # Execute the module
            spec.loader.exec_module(module)
            
            # Cache it
            self._loaded_modules[cache_key] = module
            logger.info(f"Successfully loaded module: {module_name}")
            return module
            
        except Exception as e:
            # Remove from sys.modules if loading failed
            if module_name in sys.modules:
                del sys.modules[module_name]
            logger.error(f"Failed to load module {module_name}: {e}")
            raise ImportError(f"Failed to load Python module from {abs_path}: {e}")
            
    def _get_module_name(self, abs_path: Path) -> str:
        """
        Generate a module name for the given path.
        
        Args:
            abs_path: Absolute path to the Python file
            
        Returns:
            A valid Python module name
        """
        try:
            # If the file is under python/ directory, use relative import name
            if abs_path.is_relative_to(self.python_dir):
                relative_path = abs_path.relative_to(self.python_dir)
                # Convert path to module name (e.g., "endpoints/customer.py" -> "endpoints.customer")
                module_parts = []
                for part in relative_path.parts[:-1]:  # All directories
                    module_parts.append(part)
                module_parts.append(relative_path.stem)  # File name without extension
                module_name = ".".join(module_parts)
                return module_name
        except ValueError:
            # Path is not relative to python_dir
            pass
            
        # For files outside python/, create a unique module name
        # Use a hash to ensure uniqueness and avoid conflicts
        path_hash = hashlib.sha256(str(abs_path).encode()).hexdigest()[:8]
        module_name = f"_mxcp_endpoint_{abs_path.stem}_{path_hash}"
        return module_name
        
    def get_function(self, module: Any, function_name: str) -> Callable:
        """
        Get a function from a loaded module.
        
        Args:
            module: The loaded Python module
            function_name: Name of the function to retrieve
            
        Returns:
            The function object
            
        Raises:
            AttributeError: If the function doesn't exist in the module
        """
        if not hasattr(module, function_name):
            # List available functions for better error message
            available = [name for name in dir(module) 
                        if callable(getattr(module, name)) and not name.startswith('_')]
            raise AttributeError(
                f"Function '{function_name}' not found in module. "
                f"Available functions: {', '.join(available) or 'none'}"
            )
        
        func = getattr(module, function_name)
        if not callable(func):
            raise AttributeError(f"'{function_name}' is not a callable function")
            
        return func
        
    def preload_all_modules(self):
        """
        Preload all Python files in the python/ directory.
        
        This is useful for server mode to load all modules at startup,
        which can help catch import errors early.
        """
        if not self.python_dir.exists():
            logger.info(f"Python directory {self.python_dir} does not exist, skipping preload")
            return
            
        loaded_count = 0
        error_count = 0
        
        for py_file in self.python_dir.rglob("*.py"):
            # Skip __pycache__ directories
            if "__pycache__" in str(py_file):
                continue
                
            # Skip __init__.py files (they're loaded automatically)
            if py_file.name == "__init__.py":
                continue
                
            # Skip private files (starting with _)
            if py_file.name.startswith("_"):
                logger.debug(f"Skipping private file: {py_file}")
                continue
                
            try:
                self.load_python_module(py_file)
                loaded_count += 1
            except Exception as e:
                logger.error(f"Failed to preload {py_file}: {e}")
                error_count += 1
                
        logger.info(f"Preloaded {loaded_count} Python modules ({error_count} errors)")
        
    def cleanup(self):
        """
        Clean up loaded modules and restore sys.path.
        
        This is called on shutdown to clean up the Python environment.
        """
        # Remove added paths from sys.path
        for path in self._module_paths:
            if path in sys.path:
                sys.path.remove(path)
                logger.debug(f"Removed {path} from Python path")
                
        # Clear module cache
        self._loaded_modules.clear()
        
        # Note: We don't remove modules from sys.modules as that could
        # break other code that imported them 