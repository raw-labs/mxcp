"""Tests for concurrent execution of Python endpoints without database operations."""
import pytest
import asyncio
import threading
import time
import tempfile
import os
import yaml
from pathlib import Path
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from mxcp.config.user_config import load_user_config
from mxcp.config.site_config import load_site_config
from mxcp.engine.duckdb_session import DuckDBSession
from mxcp.endpoints.executor import EndpointExecutor, EndpointType
from mxcp.endpoints.runner import run_endpoint
from mxcp.runtime import _set_runtime_context, _clear_runtime_context


# Global shared state for testing thread safety
shared_counter = 0
shared_counter_lock = threading.Lock()
execution_log = []
execution_log_lock = threading.Lock()


@pytest.fixture
def temp_project_dir():
    """Create a temporary project directory structure."""
    with tempfile.TemporaryDirectory() as tmpdir:
        project_dir = Path(tmpdir)
        
        # Create directory structure
        (project_dir / "tools").mkdir()
        (project_dir / "python").mkdir()
        
        # Create mxcp-site.yml
        site_config = {
            "mxcp": 1,
            "project": "test-concurrent",
            "profile": "test",
            "profiles": {
                "test": {
                    "duckdb": {
                        "path": ":memory:"  # Use in-memory database
                    }
                }
            },
            "paths": {
                "tools": "tools"
            }
        }
        
        with open(project_dir / "mxcp-site.yml", "w") as f:
            yaml.dump(site_config, f)
        
        # Change to project directory
        original_dir = os.getcwd()
        os.chdir(project_dir)
        
        yield project_dir
        
        # Restore original directory
        os.chdir(original_dir)


@pytest.fixture
def test_configs(temp_project_dir):
    """Create test configurations."""
    # Create user config file
    user_config_data = {
        "mxcp": 1,
        "projects": {
            "test-concurrent": {
                "profiles": {
                    "test": {
                        "secrets": [
                            {
                                "name": "api_key",
                                "type": "value",
                                "parameters": {
                                    "value": "test-key-123"
                                }
                            },
                            {
                                "name": "api_secret",
                                "type": "value", 
                                "parameters": {
                                    "value": "test-secret-456"
                                }
                            }
                        ],
                        "plugin": {"config": {}}
                    }
                }
            }
        }
    }
    
    # Write user config to file
    config_path = temp_project_dir / "mxcp-config.yml"
    with open(config_path, "w") as f:
        yaml.dump(user_config_data, f)
    
    # Set environment variable to point to our config
    os.environ["MXCP_CONFIG"] = str(config_path)
    
    # Load configs
    site_config = load_site_config()
    user_config = load_user_config(site_config)
    
    yield user_config, site_config
    
    # Clean up environment variable
    if "MXCP_CONFIG" in os.environ:
        del os.environ["MXCP_CONFIG"]


@pytest.fixture
def test_session(test_configs):
    """Create a minimal test DuckDB session (just for the executor)."""
    user_config, site_config = test_configs
    session = DuckDBSession(user_config, site_config, profile="test")
    yield session
    session.close()


@pytest.fixture(autouse=True)
def reset_global_state():
    """Reset global state before each test."""
    global shared_counter, execution_log
    shared_counter = 0
    execution_log.clear()
    yield


def test_concurrent_sync_python_functions(temp_project_dir, test_configs, test_session):
    """Test concurrent execution of synchronous Python functions."""
    user_config, site_config = test_configs
    
    # Create Python file with sync functions
    python_file = temp_project_dir / "python" / "concurrent_sync.py"
    python_file.write_text("""
import threading
import time
import random
from mxcp.runtime import config

# Module-level state
call_count = 0
call_count_lock = threading.Lock()
thread_local = threading.local()

def increment_shared_counter(amount: int, delay: float = 0.001) -> dict:
    \"\"\"Increment a shared counter with optional delay.\"\"\"
    global call_count
    
    thread_id = threading.current_thread().name
    start_time = time.time()
    
    # Simulate some work
    time.sleep(delay)
    
    # Access module-level state (thread-safe)
    with call_count_lock:
        call_count += 1
        local_call_count = call_count
    
    # Use a temporary file for shared state instead of importing test module
    import tempfile
    import os
    counter_file = os.path.join(tempfile.gettempdir(), 'mxcp_test_counter.txt')
    
    # Read current value (with potential race condition)
    try:
        with open(counter_file, 'r') as f:
            old_value = int(f.read().strip())
    except (FileNotFoundError, ValueError):
        old_value = 0
    
    # Add delay to increase chance of race
    time.sleep(random.uniform(0.0001, 0.001))
    
    # Write new value (race condition here!)
    new_value = old_value + amount
    with open(counter_file, 'w') as f:
        f.write(str(new_value))
    
    return {
        "thread_id": thread_id,
        "old_value": old_value,
        "new_value": new_value,
        "amount": amount,
        "duration": time.time() - start_time,
        "call_count": local_call_count
    }

def safe_increment_counter(amount: int) -> dict:
    \"\"\"Thread-safe increment using lock.\"\"\"
    thread_id = threading.current_thread().name
    
    # Use file locking for thread safety
    import tempfile
    import os
    import fcntl
    counter_file = os.path.join(tempfile.gettempdir(), 'mxcp_test_counter_safe.txt')
    lock_file = counter_file + '.lock'
    
    # Use file-based locking
    with open(lock_file, 'w') as lockf:
        fcntl.flock(lockf.fileno(), fcntl.LOCK_EX)
        try:
            # Read current value
            try:
                with open(counter_file, 'r') as f:
                    old_value = int(f.read().strip())
            except (FileNotFoundError, ValueError):
                old_value = 0
            
            # Write new value
            new_value = old_value + amount
            with open(counter_file, 'w') as f:
                f.write(str(new_value))
        finally:
            fcntl.flock(lockf.fileno(), fcntl.LOCK_UN)
    
    return {
        "thread_id": thread_id,
        "old_value": old_value,
        "new_value": new_value,
        "amount": amount
    }

def test_context_access() -> dict:
    \"\"\"Test access to runtime context (secrets, config).\"\"\"
    thread_id = threading.current_thread().name
    
    # Access secrets
    api_key = config.get_secret("api_key")
    api_secret = config.get_secret("api_secret")
    missing = config.get_secret("missing_key")
    
    # Access config settings
    project = config.get_setting("project")
    profile = config.get_setting("profile")
    
    # Test thread-local storage
    if not hasattr(thread_local, 'counter'):
        thread_local.counter = 0
    thread_local.counter += 1
    
    return {
        "thread_id": thread_id,
        "has_api_key": api_key is not None,
        "api_key_starts": api_key[:5] if api_key else None,
        "has_api_secret": api_secret is not None,
        "missing_secret": missing,
        "project": project,
        "profile": profile,
        "thread_local_counter": thread_local.counter
    }

def cpu_intensive_task(iterations: int) -> dict:
    \"\"\"Simulate CPU-intensive work.\"\"\"
    thread_id = threading.current_thread().name
    start_time = time.time()
    
    # Do some CPU work
    result = 0
    for i in range(iterations):
        result += i ** 2
    
    duration = time.time() - start_time
    
    return {
        "thread_id": thread_id,
        "iterations": iterations,
        "result": result,
        "duration": duration
    }
""")
    
    # Create tool definitions
    (temp_project_dir / "tools" / "increment_shared_counter.yml").write_text("""
mxcp: 1
tool:
  name: increment_shared_counter
  description: Increment shared counter (unsafe)
  language: python
  source:
    file: ../python/concurrent_sync.py
  parameters:
    - name: amount
      type: integer
      description: Amount to increment
    - name: delay
      type: number
      description: Delay in seconds
      default: 0.001
  return:
    type: object
""")
    
    (temp_project_dir / "tools" / "safe_increment_counter.yml").write_text("""
mxcp: 1
tool:
  name: safe_increment_counter
  description: Thread-safe increment
  language: python
  source:
    file: ../python/concurrent_sync.py
  parameters:
    - name: amount
      type: integer
      description: Amount to increment
  return:
    type: object
""")
    
    (temp_project_dir / "tools" / "test_context_access.yml").write_text("""
mxcp: 1
tool:
  name: test_context_access
  description: Test runtime context access
  language: python
  source:
    file: ../python/concurrent_sync.py
  parameters: []
  return:
    type: object
""")
    
    (temp_project_dir / "tools" / "cpu_intensive_task.yml").write_text("""
mxcp: 1
tool:
  name: cpu_intensive_task
  description: CPU intensive task
  language: python
  source:
    file: ../python/concurrent_sync.py
  parameters:
    - name: iterations
      type: integer
      description: Number of iterations
  return:
    type: object
""")
    
    print("\n=== Testing concurrent sync functions ===")
    
    # Test 1: Race conditions with unsafe increment
    async def test_race_conditions():
        # Clear counter file
        import tempfile
        counter_file = os.path.join(tempfile.gettempdir(), 'mxcp_test_counter.txt')
        if os.path.exists(counter_file):
            os.remove(counter_file)
        
        tasks = []
        for i in range(20):
            executor = EndpointExecutor(
                EndpointType.TOOL,
                "increment_shared_counter",
                user_config,
                site_config,
                test_session
            )
            task = executor.execute({"amount": 1, "delay": 0.0001})
            tasks.append(task)
        
        results = await asyncio.gather(*tasks)
        
        # Read final value from file
        try:
            with open(counter_file, 'r') as f:
                final_value = int(f.read().strip())
        except (FileNotFoundError, ValueError):
            final_value = 0
        
        print(f"\nRace condition test:")
        print(f"  Final counter value: {final_value} (expected: 20)")
        print(f"  Number of executions: {len(results)}")
        
        # Check for race conditions
        unique_old_values = set(r["old_value"] for r in results)
        print(f"  Unique old values seen: {len(unique_old_values)}")
        
        # With race conditions, we likely see duplicate old_values
        # and final value < 20
        if final_value < 20:
            print(f"  ✓ Race condition detected: {final_value} < 20")
        
        return final_value
    
    # Test 2: Thread-safe increment
    async def test_thread_safe():
        # Clear counter file
        import tempfile
        counter_file = os.path.join(tempfile.gettempdir(), 'mxcp_test_counter_safe.txt')
        lock_file = counter_file + '.lock'
        if os.path.exists(counter_file):
            os.remove(counter_file)
        if os.path.exists(lock_file):
            os.remove(lock_file)
        
        tasks = []
        for i in range(20):
            executor = EndpointExecutor(
                EndpointType.TOOL,
                "safe_increment_counter",
                user_config,
                site_config,
                test_session
            )
            task = executor.execute({"amount": 1})
            tasks.append(task)
        
        results = await asyncio.gather(*tasks)
        
        # Read final value from file
        with open(counter_file, 'r') as f:
            final_value = int(f.read().strip())
        
        print(f"\nThread-safe test:")
        print(f"  Final counter value: {final_value} (expected: 20)")
        
        # Verify sequential increments
        old_values = sorted([r["old_value"] for r in results])
        assert old_values == list(range(20))
        assert final_value == 20
        print(f"  ✓ All increments were sequential")
    
    # Test 3: Context isolation
    async def test_context_isolation():
        tasks = []
        for i in range(10):
            executor = EndpointExecutor(
                EndpointType.TOOL,
                "test_context_access",
                user_config,
                site_config,
                test_session
            )
            task = executor.execute({})
            tasks.append(task)
        
        results = await asyncio.gather(*tasks)
        
        print(f"\nContext isolation test:")
        print(f"  Number of executions: {len(results)}")
        
        # All should have access to secrets
        assert all(r["has_api_key"] for r in results)
        assert all(r["api_key_starts"] == "test-" for r in results)
        assert all(r["has_api_secret"] for r in results)
        assert all(r["missing_secret"] is None for r in results)
        
        # Thread-local counters should be independent
        thread_counters = defaultdict(list)
        for r in results:
            thread_counters[r["thread_id"]].append(r["thread_local_counter"])
        
        print(f"  Threads used: {len(thread_counters)}")
        for thread_id, counters in thread_counters.items():
            print(f"    {thread_id}: {counters}")
        
        # Each thread's counter should increment sequentially
        for thread_id, counters in thread_counters.items():
            assert counters == list(range(1, len(counters) + 1))
        
        print(f"  ✓ Thread-local storage working correctly")
    
    # Test 4: CPU-bound tasks
    async def test_cpu_bound():
        start_time = time.time()
        
        tasks = []
        for i in range(5):
            executor = EndpointExecutor(
                EndpointType.TOOL,
                "cpu_intensive_task",
                user_config,
                site_config,
                test_session
            )
            task = executor.execute({"iterations": 100000})
            tasks.append(task)
        
        results = await asyncio.gather(*tasks)
        total_time = time.time() - start_time
        
        print(f"\nCPU-bound test:")
        print(f"  Tasks: {len(results)}")
        print(f"  Total time: {total_time:.2f}s")
        
        # Check that work was distributed across threads
        thread_ids = set(r["thread_id"] for r in results)
        print(f"  Threads used: {len(thread_ids)}")
        
        # All results should be the same
        expected_result = sum(i**2 for i in range(100000))
        assert all(r["result"] == expected_result for r in results)
    
    # Run all tests
    race_value = asyncio.run(test_race_conditions())
    asyncio.run(test_thread_safe())
    asyncio.run(test_context_isolation())
    asyncio.run(test_cpu_bound())


def test_concurrent_async_python_functions(temp_project_dir, test_configs, test_session):
    """Test concurrent execution of async Python functions."""
    user_config, site_config = test_configs
    
    # Create Python file with async functions
    python_file = temp_project_dir / "python" / "concurrent_async.py"
    python_file.write_text("""
import asyncio
import time
from mxcp.runtime import config

# Track concurrent executions
active_tasks = 0
max_concurrent = 0
task_lock = asyncio.Lock()

async def async_task(task_id: int, duration: float) -> dict:
    \"\"\"Async task that tracks concurrent execution.\"\"\"
    global active_tasks, max_concurrent
    
    async with task_lock:
        active_tasks += 1
        max_concurrent = max(max_concurrent, active_tasks)
        current_active = active_tasks
    
    start_time = time.time()
    task_name = f"task_{task_id}"
    
    try:
        # Simulate async I/O
        await asyncio.sleep(duration)
        
        # Access runtime context
        api_key = config.get_secret("api_key")
        
        return {
            "task_id": task_id,
            "task_name": task_name,
            "duration": duration,
            "actual_duration": time.time() - start_time,
            "active_at_start": current_active,
            "max_concurrent_seen": max_concurrent,
            "has_secret": api_key is not None
        }
    finally:
        async with task_lock:
            active_tasks -= 1

async def parallel_subtasks(count: int) -> dict:
    \"\"\"Create multiple subtasks in parallel.\"\"\"
    start_time = time.time()
    
    # Create subtasks
    subtasks = []
    for i in range(count):
        subtask = _process_item(i)
        subtasks.append(subtask)
    
    # Wait for all subtasks
    results = await asyncio.gather(*subtasks)
    
    total_duration = time.time() - start_time
    
    return {
        "count": count,
        "total_duration": total_duration,
        "avg_duration": total_duration / count if count > 0 else 0,
        "results": results
    }

async def _process_item(item_id: int) -> dict:
    \"\"\"Process a single item.\"\"\"
    start = time.time()
    await asyncio.sleep(0.01)  # Simulate I/O
    
    # Test context is available in subtasks
    project = config.get_setting("project")
    
    return {
        "item_id": item_id,
        "duration": time.time() - start,
        "project": project
    }

async def test_async_context() -> dict:
    \"\"\"Test context variables in async functions.\"\"\"
    main_task_id = id(asyncio.current_task())
    
    # Access context in main task
    api_key = config.get_secret("api_key")
    
    # Create nested async calls
    nested1 = await _nested_context_test(1)
    nested2 = await _nested_context_test(2)
    
    # Concurrent nested calls
    concurrent_nested = await asyncio.gather(
        _nested_context_test(3),
        _nested_context_test(4),
        _nested_context_test(5)
    )
    
    return {
        "main_task_id": str(main_task_id),
        "main_has_secret": api_key is not None,
        "nested_sequential": [nested1, nested2],
        "nested_concurrent": concurrent_nested
    }

async def _nested_context_test(level: int) -> dict:
    \"\"\"Nested async function to test context propagation.\"\"\"
    task_id = id(asyncio.current_task())
    await asyncio.sleep(0.001)
    
    # Context should be available here too
    api_secret = config.get_secret("api_secret")
    
    return {
        "level": level,
        "task_id": str(task_id),
        "has_secret": api_secret is not None
    }
""")
    
    # Create tool definitions
    (temp_project_dir / "tools" / "async_task.yml").write_text("""
mxcp: 1
tool:
  name: async_task
  description: Async task with tracking
  language: python
  source:
    file: ../python/concurrent_async.py
  parameters:
    - name: task_id
      type: integer
      description: Task identifier
    - name: duration
      type: number
      description: Task duration in seconds
  return:
    type: object
""")
    
    (temp_project_dir / "tools" / "parallel_subtasks.yml").write_text("""
mxcp: 1
tool:
  name: parallel_subtasks
  description: Create parallel subtasks
  language: python
  source:
    file: ../python/concurrent_async.py
  parameters:
    - name: count
      type: integer
      description: Number of subtasks
  return:
    type: object
""")
    
    (temp_project_dir / "tools" / "test_async_context.yml").write_text("""
mxcp: 1
tool:
  name: test_async_context
  description: Test async context propagation
  language: python
  source:
    file: ../python/concurrent_async.py
  parameters: []
  return:
    type: object
""")
    
    print("\n=== Testing concurrent async functions ===")
    
    # Test 1: Concurrent async execution
    async def test_async_concurrency():
        tasks = []
        for i in range(10):
            executor = EndpointExecutor(
                EndpointType.TOOL,
                "async_task",
                user_config,
                site_config,
                test_session
            )
            # Stagger the tasks slightly
            task = executor.execute({"task_id": i, "duration": 0.05})
            tasks.append(task)
        
        start_time = time.time()
        results = await asyncio.gather(*tasks)
        total_time = time.time() - start_time
        
        print(f"\nAsync concurrency test:")
        print(f"  Tasks: {len(results)}")
        print(f"  Total time: {total_time:.2f}s")
        print(f"  Max concurrent: {max(r['max_concurrent_seen'] for r in results)}")
        
        # Should complete much faster than serial (10 * 0.05 = 0.5s)
        assert total_time < 0.2  # Allow for overhead
        
        # Should see high concurrency
        max_concurrent_seen = max(r['max_concurrent_seen'] for r in results)
        print(f"  ✓ High concurrency achieved: {max_concurrent_seen}")
        
        # All should have context
        assert all(r['has_secret'] for r in results)
    
    # Test 2: Parallel subtasks within async function
    async def test_parallel_subtasks():
        executor = EndpointExecutor(
            EndpointType.TOOL,
            "parallel_subtasks",
            user_config,
            site_config,
            test_session
        )
        
        result = await executor.execute({"count": 20})
        
        print(f"\nParallel subtasks test:")
        print(f"  Subtasks: {result['count']}")
        print(f"  Total duration: {result['total_duration']:.3f}s")
        print(f"  Average duration: {result['avg_duration']:.3f}s")
        
        # Should be much faster than serial
        assert result['total_duration'] < 0.1  # 20 * 0.01 = 0.2s serial
        
        # All subtasks should have context
        assert all(r['project'] == 'test-concurrent' for r in result['results'])
        print(f"  ✓ All subtasks had access to context")
    
    # Test 3: Context propagation in nested async
    async def test_async_context_propagation():
        executor = EndpointExecutor(
            EndpointType.TOOL,
            "test_async_context",
            user_config,
            site_config,
            test_session
        )
        
        result = await executor.execute({})
        
        print(f"\nAsync context propagation test:")
        print(f"  Main task has secret: {result['main_has_secret']}")
        print(f"  Sequential nested: {len(result['nested_sequential'])}")
        print(f"  Concurrent nested: {len(result['nested_concurrent'])}")
        
        # All levels should have context
        assert result['main_has_secret']
        assert all(r['has_secret'] for r in result['nested_sequential'])
        assert all(r['has_secret'] for r in result['nested_concurrent'])
        
        # Task IDs should be different
        all_task_ids = [result['main_task_id']]
        all_task_ids.extend(r['task_id'] for r in result['nested_sequential'])
        all_task_ids.extend(r['task_id'] for r in result['nested_concurrent'])
        
        unique_task_ids = set(all_task_ids)
        print(f"  Unique task IDs: {len(unique_task_ids)}")
        print(f"  ✓ Context propagated to all nested tasks")
    
    # Run all tests
    asyncio.run(test_async_concurrency())
    asyncio.run(test_parallel_subtasks())
    asyncio.run(test_async_context_propagation())


def test_mixed_sync_async_stress(temp_project_dir, test_configs, test_session):
    """Stress test with mixed sync/async execution."""
    user_config, site_config = test_configs
    
    # Create Python file with mixed functions
    python_file = temp_project_dir / "python" / "stress_test.py"
    python_file.write_text("""
import asyncio
import time
import random
import threading
from mxcp.runtime import config

# Shared state for stress testing
request_count = 0
error_count = 0
stats_lock = threading.Lock()

def sync_stress_endpoint(request_id: int) -> dict:
    \"\"\"Sync endpoint for stress testing.\"\"\"
    global request_count, error_count
    
    thread_id = threading.current_thread().name
    start_time = time.time()
    
    try:
        # Increment request counter
        with stats_lock:
            request_count += 1
            current_count = request_count
        
        # Random work
        work_time = random.uniform(0.001, 0.005)
        time.sleep(work_time)
        
        # Random chance of "error"
        if random.random() < 0.1:  # 10% error rate
            raise ValueError(f"Simulated error in request {request_id}")
        
        # Access context
        api_key = config.get_secret("api_key")
        
        return {
            "request_id": request_id,
            "thread_id": thread_id,
            "request_number": current_count,
            "work_time": work_time,
            "duration": time.time() - start_time,
            "has_context": api_key is not None,
            "status": "success"
        }
    except Exception as e:
        with stats_lock:
            error_count += 1
        return {
            "request_id": request_id,
            "thread_id": thread_id,
            "error": str(e),
            "status": "error"
        }

async def async_stress_endpoint(request_id: int) -> dict:
    \"\"\"Async endpoint for stress testing.\"\"\"
    global request_count, error_count
    
    task_id = str(id(asyncio.current_task()))
    start_time = time.time()
    
    try:
        # Increment counter (thread-safe even in async)
        with stats_lock:
            request_count += 1
            current_count = request_count
        
        # Random async work
        work_time = random.uniform(0.001, 0.005)
        await asyncio.sleep(work_time)
        
        # Random chance of "error"
        if random.random() < 0.1:  # 10% error rate
            raise ValueError(f"Simulated async error in request {request_id}")
        
        # Access context
        api_secret = config.get_secret("api_secret")
        
        return {
            "request_id": request_id,
            "task_id": task_id,
            "request_number": current_count,
            "work_time": work_time,
            "duration": time.time() - start_time,
            "has_context": api_secret is not None,
            "status": "success",
            "type": "async"
        }
    except Exception as e:
        with stats_lock:
            error_count += 1
        return {
            "request_id": request_id,
            "task_id": task_id,
            "error": str(e),
            "status": "error",
            "type": "async"
        }

def get_stats() -> dict:
    \"\"\"Get current statistics.\"\"\"
    with stats_lock:
        return {
            "total_requests": request_count,
            "total_errors": error_count,
            "success_rate": (request_count - error_count) / request_count if request_count > 0 else 0
        }
""")
    
    # Create tool definitions
    (temp_project_dir / "tools" / "sync_stress_endpoint.yml").write_text("""
mxcp: 1
tool:
  name: sync_stress_endpoint
  description: Sync stress test endpoint
  language: python
  source:
    file: ../python/stress_test.py
  parameters:
    - name: request_id
      type: integer
      description: Request identifier
  return:
    type: object
""")
    
    (temp_project_dir / "tools" / "async_stress_endpoint.yml").write_text("""
mxcp: 1
tool:
  name: async_stress_endpoint
  description: Async stress test endpoint
  language: python
  source:
    file: ../python/stress_test.py
  parameters:
    - name: request_id
      type: integer
      description: Request identifier
  return:
    type: object
""")
    
    (temp_project_dir / "tools" / "get_stats.yml").write_text("""
mxcp: 1
tool:
  name: get_stats
  description: Get stress test statistics
  language: python
  source:
    file: ../python/stress_test.py
  parameters: []
  return:
    type: object
""")
    
    print("\n=== Mixed sync/async stress test ===")
    
    async def run_stress_test(total_requests: int):
        # Mix of sync and async requests
        tasks = []
        
        for i in range(total_requests):
            # Alternate between sync and async
            if i % 2 == 0:
                executor = EndpointExecutor(
                    EndpointType.TOOL,
                    "sync_stress_endpoint",
                    user_config,
                    site_config,
                    test_session
                )
            else:
                executor = EndpointExecutor(
                    EndpointType.TOOL,
                    "async_stress_endpoint",
                    user_config,
                    site_config,
                    test_session
                )
            
            task = executor.execute({"request_id": i})
            tasks.append(task)
        
        start_time = time.time()
        results = await asyncio.gather(*tasks, return_exceptions=True)
        total_time = time.time() - start_time
        
        # Get final stats
        stats_executor = EndpointExecutor(
            EndpointType.TOOL,
            "get_stats",
            user_config,
            site_config,
            test_session
        )
        stats = await stats_executor.execute({})
        
        # Analyze results
        successful = [r for r in results if isinstance(r, dict) and r.get('status') == 'success']
        errors = [r for r in results if isinstance(r, dict) and r.get('status') == 'error']
        exceptions = [r for r in results if isinstance(r, Exception)]
        
        print(f"\nStress test results ({total_requests} requests):")
        print(f"  Total time: {total_time:.2f}s")
        print(f"  Requests/sec: {total_requests / total_time:.0f}")
        print(f"  Successful: {len(successful)}")
        print(f"  Application errors: {len(errors)}")
        print(f"  Exceptions: {len(exceptions)}")
        print(f"  Stats: {stats}")
        
        # Check context availability
        context_available = [r for r in successful if r.get('has_context')]
        print(f"  Context available: {len(context_available)}/{len(successful)}")
        
        # Verify reasonable success rate
        success_rate = len(successful) / total_requests
        print(f"  Success rate: {success_rate:.1%}")
        
        # Should handle most requests successfully
        assert success_rate > 0.8  # Allow for simulated errors
        
        # All successful requests should have context
        assert all(r.get('has_context') for r in successful)
        
        return results, stats
    
    # Run stress tests with increasing load
    for num_requests in [50, 100, 200]:
        print(f"\n--- Testing with {num_requests} requests ---")
        results, stats = asyncio.run(run_stress_test(num_requests))
        
        # Brief pause between tests
        time.sleep(0.1)


def test_error_handling_and_cleanup(temp_project_dir, test_configs, test_session):
    """Test error handling and cleanup in concurrent scenarios."""
    user_config, site_config = test_configs
    
    # Create Python file with functions that can fail
    python_file = temp_project_dir / "python" / "error_handling.py"
    python_file.write_text("""
import asyncio
import threading
import time
from mxcp.runtime import config

# Track resource allocation
resources_allocated = 0
resources_freed = 0
resource_lock = threading.Lock()

class MockResource:
    def __init__(self, resource_id):
        self.resource_id = resource_id
        self.closed = False
    
    def close(self):
        self.closed = True

def failing_function(fail_after: float, error_type: str = "ValueError") -> dict:
    \"\"\"Function that fails after some work.\"\"\"
    global resources_allocated, resources_freed
    
    thread_id = threading.current_thread().name
    
    # Allocate a "resource"
    with resource_lock:
        resources_allocated += 1
        resource_id = resources_allocated
    
    resource = MockResource(resource_id)
    
    try:
        # Do some work
        time.sleep(fail_after)
        
        # Fail based on error_type
        if error_type == "ValueError":
            raise ValueError(f"Simulated ValueError after {fail_after}s")
        elif error_type == "RuntimeError":
            raise RuntimeError(f"Simulated RuntimeError after {fail_after}s")
        elif error_type == "KeyError":
            raise KeyError(f"Simulated KeyError after {fail_after}s")
        else:
            # Success case
            return {
                "thread_id": thread_id,
                "resource_id": resource_id,
                "status": "success"
            }
    finally:
        # Cleanup should always happen
        resource.close()
        with resource_lock:
            resources_freed += 1

async def async_failing_function(fail_after: float, error_type: str = "ValueError") -> dict:
    \"\"\"Async function that fails after some work.\"\"\"
    global resources_allocated, resources_freed
    
    task_id = str(id(asyncio.current_task()))
    
    # Allocate a "resource"
    with resource_lock:
        resources_allocated += 1
        resource_id = resources_allocated
    
    resource = MockResource(resource_id)
    
    try:
        # Do some async work
        await asyncio.sleep(fail_after)
        
        # Access context to ensure it's available
        api_key = config.get_secret("api_key")
        
        # Fail based on error_type
        if error_type == "ValueError":
            raise ValueError(f"Async simulated ValueError after {fail_after}s")
        elif error_type == "RuntimeError":
            raise RuntimeError(f"Async simulated RuntimeError after {fail_after}s")
        elif error_type == "KeyError":
            raise KeyError(f"Async simulated KeyError after {fail_after}s")
        else:
            # Success case
            return {
                "task_id": task_id,
                "resource_id": resource_id,
                "has_context": api_key is not None,
                "status": "success"
            }
    finally:
        # Cleanup should always happen
        resource.close()
        with resource_lock:
            resources_freed += 1

def get_resource_stats() -> dict:
    \"\"\"Get current resource statistics.\"\"\"
    with resource_lock:
        return {
            "allocated": resources_allocated,
            "freed": resources_freed,
            "leaked": resources_allocated - resources_freed
        }
""")
    
    # Create tool definitions
    (temp_project_dir / "tools" / "failing_function.yml").write_text("""
mxcp: 1
tool:
  name: failing_function
  description: Function that may fail
  language: python
  source:
    file: ../python/error_handling.py
  parameters:
    - name: fail_after
      type: number
      description: Time before failure
    - name: error_type
      type: string
      description: Type of error to raise
      default: "ValueError"
  return:
    type: object
""")
    
    (temp_project_dir / "tools" / "async_failing_function.yml").write_text("""
mxcp: 1
tool:
  name: async_failing_function
  description: Async function that may fail
  language: python
  source:
    file: ../python/error_handling.py
  parameters:
    - name: fail_after
      type: number
      description: Time before failure
    - name: error_type
      type: string
      description: Type of error to raise
      default: "ValueError"
  return:
    type: object
""")
    
    (temp_project_dir / "tools" / "get_resource_stats.yml").write_text("""
mxcp: 1
tool:
  name: get_resource_stats
  description: Get resource statistics
  language: python
  source:
    file: ../python/error_handling.py
  parameters: []
  return:
    type: object
""")
    
    print("\n=== Testing error handling and cleanup ===")
    
    async def test_concurrent_failures():
        # Mix of successful and failing calls
        tasks = []
        
        # Some will succeed
        for i in range(5):
            executor = EndpointExecutor(
                EndpointType.TOOL,
                "failing_function",
                user_config,
                site_config,
                test_session
            )
            task = executor.execute({"fail_after": 0.001, "error_type": "none"})
            tasks.append(task)
        
        # Some will fail with different errors
        error_types = ["ValueError", "RuntimeError", "KeyError"]
        for i in range(15):
            executor = EndpointExecutor(
                EndpointType.TOOL,
                "failing_function" if i % 2 == 0 else "async_failing_function",
                user_config,
                site_config,
                test_session
            )
            error_type = error_types[i % len(error_types)]
            task = executor.execute({"fail_after": 0.001, "error_type": error_type})
            tasks.append(task)
        
        # Gather all results, including exceptions
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Get resource stats
        stats_executor = EndpointExecutor(
            EndpointType.TOOL,
            "get_resource_stats",
            user_config,
            site_config,
            test_session
        )
        stats = await stats_executor.execute({})
        
        # Analyze results
        successes = [r for r in results if isinstance(r, dict) and r.get('status') == 'success']
        value_errors = [r for r in results if isinstance(r, ValueError)]
        runtime_errors = [r for r in results if isinstance(r, RuntimeError)]
        key_errors = [r for r in results if isinstance(r, KeyError)]
        
        print(f"\nConcurrent failure test results:")
        print(f"  Total tasks: {len(results)}")
        print(f"  Successes: {len(successes)}")
        print(f"  ValueErrors: {len(value_errors)}")
        print(f"  RuntimeErrors: {len(runtime_errors)}")
        print(f"  KeyErrors: {len(key_errors)}")
        print(f"  Resource stats: {stats}")
        
        # Verify cleanup happened even with errors
        assert stats['leaked'] == 0, f"Resources leaked: {stats['leaked']}"
        assert stats['allocated'] == stats['freed']
        print(f"  ✓ All resources cleaned up properly")
        
        # Verify we got the expected errors
        assert len(value_errors) > 0
        assert len(runtime_errors) > 0
        assert len(key_errors) > 0
        assert len(successes) == 5
    
    asyncio.run(test_concurrent_failures())


if __name__ == "__main__":
    pytest.main([__file__, "-v"]) 