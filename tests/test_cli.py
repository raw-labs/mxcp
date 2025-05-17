import subprocess
from pathlib import Path

def test_raw_list_runs():
    test_repo = Path(__file__).parent / "fixtures" / "test-repo"
    result = subprocess.run(
        ["raw", "list"],
        cwd=test_repo,
        capture_output=True,
        text=True
    )
    assert result.returncode == 0
    assert "hello" in result.stdout.lower()