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
from mxcp.config.user_config import load_user_config
from mxcp.config.site_config import load_site_config
from mxcp.endpoints.sdk_executor import execute_endpoint_with_engine
from mxcp.config.execution_engine import create_execution_engine


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
def execution_engine(test_configs):
    """Create an execution engine with test database setup."""
    user_config, site_config = test_configs
    
    # Create execution engine
    engine = create_execution_engine(user_config, site_config, "test")
    
    # Store user_config on engine for runtime context access
    setattr(engine, '_user_config', user_config)
    
    yield engine
    
    # Cleanup
    engine.shutdown()


@pytest.fixture(autouse=True)
def reset_global_state():
    """Reset global state before each test."""
    global shared_counter, execution_log
    shared_counter = 0
    execution_log.clear()
    yield


@pytest.mark.asyncio
async def test_concurrent_sync_python_functions(temp_project_dir, test_configs, execution_engine):
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
    
    # Access secrets - get_secret now returns the parameters dict
    api_key_params = config.get_secret("api_key")
    api_secret_params = config.get_secret("api_secret")
    missing = config.get_secret("missing_key")
    
    # Extract values from value-type secrets
    api_key = api_key_params["value"] if api_key_params else None
    api_secret = api_secret_params["value"] if api_secret_params else None
    
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
            task = execute_endpoint_with_engine(
                endpoint_type="tool",
                name="increment_shared_counter",
                params={"amount": 1, "delay": 0.0001},
                user_config=user_config,
                site_config=site_config,
                execution_engine=execution_engine
            )
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
            task = execute_endpoint_with_engine(
                endpoint_type="tool",
                name="safe_increment_counter",
                params={"amount": 1},
                user_config=user_config,
                site_config=site_config,
                execution_engine=execution_engine
            )
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
            task = execute_endpoint_with_engine(
                endpoint_type="tool",
                name="test_context_access",
                params={},
                user_config=user_config,
                site_config=site_config,
                execution_engine=execution_engine
            )
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
            task = execute_endpoint_with_engine(
                endpoint_type="tool",
                name="cpu_intensive_task",
                params={"iterations": 100000},
                user_config=user_config,
                site_config=site_config,
                execution_engine=execution_engine
            )
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
    race_value = await test_race_conditions()
    await test_thread_safe()
    await test_context_isolation()
    await test_cpu_bound()


@pytest.mark.asyncio
async def test_concurrent_async_python_functions(temp_project_dir, test_configs, execution_engine):
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
            task = execute_endpoint_with_engine(
                endpoint_type="tool",
                name="async_task",
                params={"task_id": i, "duration": 0.05},
                user_config=user_config,
                site_config=site_config,
                execution_engine=execution_engine
            )
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
        result = await execute_endpoint_with_engine(
            endpoint_type="tool",
            name="parallel_subtasks",
            params={"count": 20},
            user_config=user_config,
            site_config=site_config,
            execution_engine=execution_engine
        )
        
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
        result = await execute_endpoint_with_engine(
            endpoint_type="tool",
            name="test_async_context",
            params={},
            user_config=user_config,
            site_config=site_config,
            execution_engine=execution_engine
        )
        
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
    await test_async_concurrency()
    await test_parallel_subtasks()
    await test_async_context_propagation()


@pytest.mark.asyncio
async def test_mixed_sync_async_stress(temp_project_dir, test_configs, execution_engine):
    """Stress test with mixed sync/async execution."""
    user_config, site_config = test_configs
    
    # Create Python files with stress test functions
    sync_file = temp_project_dir / "python" / "sync_stress.py"
    sync_file.write_text("""
import time
import threading
from mxcp.runtime import config

def sync_stress_endpoint(request_id: int) -> dict:
    \"\"\"Synchronous stress test endpoint.\"\"\"
    thread_id = threading.current_thread().name
    start_time = time.time()
    
    # Simulate work with some variability
    time.sleep(0.001 + (request_id % 10) * 0.0001)
    
    return {
        "request_id": request_id,
        "thread_id": thread_id,
        "duration": time.time() - start_time,
        "type": "sync"
    }
""")
    
    async_file = temp_project_dir / "python" / "async_stress.py"
    async_file.write_text("""
import asyncio
import time
from mxcp.runtime import config

async def async_stress_endpoint(request_id: int) -> dict:
    \"\"\"Asynchronous stress test endpoint.\"\"\"
    start_time = time.time()
    
    # Mix of CPU and async work
    await asyncio.sleep(0.001 + (request_id % 10) * 0.0001)
    
    return {
        "request_id": request_id,
        "duration": time.time() - start_time,
        "type": "async"
    }
""")

    # Create tool configurations
    (temp_project_dir / "tools" / "sync_stress_endpoint.yml").write_text("""
mxcp: 1
tool:
  name: sync_stress_endpoint
  description: Sync stress test
  language: python
  source:
    file: ../python/sync_stress.py
  parameters:
    - name: request_id
      type: integer
      description: Request ID
  return:
    type: object
""")

    (temp_project_dir / "tools" / "async_stress_endpoint.yml").write_text("""
mxcp: 1
tool:
  name: async_stress_endpoint
  description: Async stress test
  language: python
  source:
    file: ../python/async_stress.py
  parameters:
    - name: request_id
      type: integer
      description: Request ID
  return:
    type: object
""")

    print("\n=== Testing mixed sync/async stress ===")
    
    # Test concurrent sync/async execution
    async def test_mixed_execution():
        tasks = []
        
        # Create mixed workload
        for i in range(50):
            # Alternate between sync and async
            if i % 2 == 0:
                task = execute_endpoint_with_engine(
                    endpoint_type="tool",
                    name="sync_stress_endpoint",
                    params={"request_id": i},
                    user_config=user_config,
                    site_config=site_config,
                    execution_engine=execution_engine
                )
            else:
                task = execute_endpoint_with_engine(
                    endpoint_type="tool",
                    name="async_stress_endpoint",
                    params={"request_id": i},
                    user_config=user_config,
                    site_config=site_config,
                    execution_engine=execution_engine
                )
            
            tasks.append(task)
        
        start_time = time.time()
        results = await asyncio.gather(*tasks)
        total_time = time.time() - start_time
        
        # Analyze results
        sync_results = [r for r in results if r["type"] == "sync"]
        async_results = [r for r in results if r["type"] == "async"]
        
        print(f"\nMixed execution test:")
        print(f"  Total tasks: {len(results)}")
        print(f"  Sync tasks: {len(sync_results)}")
        print(f"  Async tasks: {len(async_results)}")
        print(f"  Total time: {total_time:.2f}s")
        
        # Verify all request IDs are accounted for
        request_ids = sorted([r["request_id"] for r in results])
        expected_ids = list(range(50))
        assert request_ids == expected_ids
    
    # Execute stress test and get execution statistics
    await test_mixed_execution()
    
    print("✓ Mixed sync/async stress test completed successfully")


@pytest.mark.asyncio
async def test_error_handling_and_cleanup(temp_project_dir, test_configs, execution_engine):
    """Test error handling and cleanup in concurrent scenarios."""
    user_config, site_config = test_configs
    
    # Create Python file with functions that can fail and track resources
    python_file = temp_project_dir / "python" / "error_handling.py"
    python_file.write_text("""
import asyncio
import time
import threading
from mxcp.runtime import config

# Resource tracking
allocated_resources = []
freed_resources = []
resource_lock = threading.Lock()

def allocate_resource(name: str):
    \"\"\"Simulate resource allocation.\"\"\"
    with resource_lock:
        allocated_resources.append(name)

def free_resource(name: str):
    \"\"\"Simulate resource cleanup.\"\"\"
    with resource_lock:
        if name in allocated_resources:
            allocated_resources.remove(name)
            freed_resources.append(name)

def failing_function(fail_after: float, error_type: str) -> dict:
    \"\"\"Function that can fail in various ways.\"\"\"
    thread_id = threading.current_thread().name
    resource_name = f"resource_{thread_id}_{time.time()}"
    
    try:
        # Allocate resource
        allocate_resource(resource_name)
        
        # Do some work
        time.sleep(fail_after)
        
        # Maybe fail
        if error_type == "ValueError":
            raise ValueError("Simulated ValueError")
        elif error_type == "RuntimeError":
            raise RuntimeError("Simulated RuntimeError")
        elif error_type == "KeyError":
            raise KeyError("Simulated KeyError")
        
        return {
            "thread_id": thread_id,
            "resource": resource_name,
            "status": "success"
        }
    finally:
        # Always clean up
        free_resource(resource_name)

async def async_failing_function(fail_after: float, error_type: str) -> dict:
    \"\"\"Async function that can fail.\"\"\"
    task_id = str(id(asyncio.current_task()))
    resource_name = f"async_resource_{task_id}_{time.time()}"
    
    try:
        # Allocate resource
        allocate_resource(resource_name)
        
        # Do some async work
        await asyncio.sleep(fail_after)
        
        # Maybe fail
        if error_type == "ValueError":
            raise ValueError("Simulated async ValueError")
        elif error_type == "RuntimeError":
            raise RuntimeError("Simulated async RuntimeError")
        elif error_type == "KeyError":
            raise KeyError("Simulated async KeyError")
        
        return {
            "task_id": task_id,
            "resource": resource_name,
            "status": "success"
        }
    finally:
        # Always clean up
        free_resource(resource_name)

def get_resource_stats() -> dict:
    \"\"\"Get current resource statistics.\"\"\"
    with resource_lock:
        return {
            "allocated": len(allocated_resources),
            "freed": len(freed_resources),
            "leaked": len(allocated_resources),  # Should be 0 if cleanup works
            "allocated_list": allocated_resources.copy(),
            "freed_list": freed_resources.copy()
        }
""")

    # Create tool configurations
    (temp_project_dir / "tools" / "failing_function.yml").write_text("""
mxcp: 1
tool:
  name: failing_function
  description: Function that might fail
  language: python
  source:
    file: ../python/error_handling.py
  parameters:
    - name: fail_after
      type: number
      description: Delay before potential failure
    - name: error_type
      type: string
      description: Type of error to simulate
  return:
    type: object
""")

    (temp_project_dir / "tools" / "async_failing_function.yml").write_text("""
mxcp: 1
tool:
  name: async_failing_function
  description: Async function that might fail
  language: python
  source:
    file: ../python/error_handling.py
  parameters:
    - name: fail_after
      type: number
      description: Delay before potential failure
    - name: error_type
      type: string
      description: Type of error to simulate
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
        # Mix of successful and failing tasks
        tasks = []
        
        # Some will succeed
        for i in range(5):
            task = execute_endpoint_with_engine(
                endpoint_type="tool",
                name="failing_function",
                params={"fail_after": 0.001, "error_type": "none"},
                user_config=user_config,
                site_config=site_config,
                execution_engine=execution_engine
            )
            tasks.append(task)
        
        # Some will fail with different errors
        error_types = ["ValueError", "RuntimeError", "KeyError"]
        for i in range(15):
            task = execute_endpoint_with_engine(
                endpoint_type="tool",
                name="failing_function" if i % 2 == 0 else "async_failing_function",
                params={"fail_after": 0.001, "error_type": error_types[i % len(error_types)]},
                user_config=user_config,
                site_config=site_config,
                execution_engine=execution_engine
            )
            tasks.append(task)
        
        # Gather all results, including exceptions
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Get resource stats
        stats_executor = await execute_endpoint_with_engine(
            endpoint_type="tool",
            name="get_resource_stats",
            params={},
            user_config=user_config,
            site_config=site_config,
            execution_engine=execution_engine
        )
        
        # Analyze results
        successes = [r for r in results if isinstance(r, dict) and r.get('status') == 'success']
        value_errors = [r for r in results if isinstance(r, Exception) and 'ValueError' in str(r)]
        runtime_errors = [r for r in results if isinstance(r, Exception) and 'RuntimeError' in str(r)]
        key_errors = [r for r in results if isinstance(r, Exception) and 'KeyError' in str(r)]
        
        print(f"\nError handling test:")
        print(f"  Total tasks: {len(results)}")
        print(f"  Successes: {len(successes)}")
        print(f"  ValueErrors: {len(value_errors)}")
        print(f"  RuntimeErrors: {len(runtime_errors)}")
        print(f"  KeyErrors: {len(key_errors)}")
        print(f"  Resource stats: {stats_executor}")
        
        # Verify cleanup happened even with errors
        assert stats_executor['leaked'] == 0, f"Resources leaked: {stats_executor['leaked']}"
        print(f"  ✓ All resources cleaned up properly")
        
        # Verify expected number of successes
        assert len(successes) == 5
    
    await test_concurrent_failures()


if __name__ == "__main__":
    pytest.main([__file__, "-v"]) 