from __future__ import annotations

import re
from pathlib import Path


def test_no_dict_model_unions_in_server_code() -> None:
    """Ensure server code no longer declares dict|Model type unions."""
    repo_root = Path(__file__).resolve().parents[2]
    server_dir = repo_root / "src" / "mxcp" / "server"
    pattern = re.compile(r"dict\[str,\s*Any\]\s*\|\s*(?!None\b)[A-Z]")

    violations: list[str] = []

    for path in server_dir.rglob("*.py"):
        text = path.read_text()
        for match in pattern.finditer(text):
            violations.append(f"{path.relative_to(repo_root)}: {match.group(0)}")

    assert (
        not violations
    ), "Disallowed dict|Model unions found:\n" + "\n".join(f"- {entry}" for entry in violations)

