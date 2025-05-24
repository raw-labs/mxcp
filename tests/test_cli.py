import subprocess
from pathlib import Path

def test_mxp_list_runs():
    test_repo = Path(__file__).parent / "fixtures" / "test-repo"
    result = subprocess.run(
        ["mxcp", "list"],
        cwd=test_repo,
        capture_output=True,
        text=True
    )
    assert result.returncode == 0
    assert "example" in result.stdout.lower()