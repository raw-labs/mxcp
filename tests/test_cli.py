import subprocess

def test_raw_list_runs():
    result = subprocess.run(["raw", "list"], capture_output=True, text=True)
    assert result.returncode == 0
    assert "hello" in result.stdout.lower()