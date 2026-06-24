"""Encoding regression test for the endpoint loader core stack.

Background
----------
Tool/resource/prompt definition files are authored as UTF-8. The loader reads
them with ``open(f)`` (text mode, no ``encoding=``). In text mode Python decodes
the bytes using ``locale.getpreferredencoding(False)`` *before* PyYAML ever sees
them. On Windows with a Western locale that default is cp1252 (Windows-1252), so
a UTF-8 file containing non-ASCII characters in a description gets silently
mangled into mojibake (or raises ``UnicodeDecodeError``).

This test exercises the real core stack:

    open(f) -> yaml.safe_load -> EndpointDefinitionModel.model_validate
            -> model.tool.description

It writes a tool YAML as UTF-8 with non-ASCII characters in the description and
asserts the description survives a round trip through the loader.

Where it runs
-------------
* On a platform whose default text encoding is already UTF-8 (Linux/macOS CI,
  or any interpreter in UTF-8 mode) the bug cannot manifest, so the test SKIPS
  rather than reporting a misleading pass.
* On Windows with a cp1252 default it RUNS: it fails (mojibake or
  UnicodeDecodeError) before the fix, and passes once the loader opens files
  with ``encoding="utf-8"``.

Run it from Windows with:  pytest tests/server/test_endpoint_loader_encoding.py -v
"""

import locale
import os

import pytest

from mxcp.server.core.config.models import SiteConfigModel
from mxcp.server.definitions.endpoints.loader import EndpointLoader

# A description with characters that are multi-byte in UTF-8 and corrupt cleanly
# under cp1252 (every constituent byte is defined in cp1252, so we get mojibake
# rather than a hard decode error — which makes the equality assertion precise).
NON_ASCII_DESCRIPTION = "Summarize café revenue — uses “smart” rounding © 2026"


def _default_encoding_is_utf8() -> bool:
    return locale.getpreferredencoding(False).lower().replace("-", "") == "utf8"


@pytest.mark.skipif(
    _default_encoding_is_utf8(),
    reason=(
        "Platform default text encoding is UTF-8, so the cp1252 mis-decode "
        "cannot occur here. Run this on Windows (cp1252 locale) to exercise it."
    ),
)
def test_tool_description_survives_utf8_round_trip(tmp_path, monkeypatch):
    """A UTF-8 tool description must load unchanged through the endpoint loader."""
    # --- Arrange: a minimal mxcp project on disk ---------------------------
    (tmp_path / "mxcp-site.yml").write_text(
        "mxcp: 1\nproject: enc_test\nprofile: default\n",
        encoding="utf-8",
    )
    tools_dir = tmp_path / "tools"
    tools_dir.mkdir()

    tool_yaml = (
        "mxcp: 1\n"
        "tool:\n"
        "  name: summarize\n"
        f"  description: {NON_ASCII_DESCRIPTION!r}\n"
    )
    # Write the definition explicitly as UTF-8, exactly as an editor would.
    (tools_dir / "summarize.yml").write_text(tool_yaml, encoding="utf-8")

    # find_repo_root() walks up from the cwd looking for mxcp-site.yml.
    monkeypatch.chdir(tmp_path)

    site_config = SiteConfigModel(project="enc_test", profile="default")
    loader = EndpointLoader(site_config)

    # --- Act: run the real core stack --------------------------------------
    result = loader.load_endpoint("tool", "summarize")

    # --- Assert ------------------------------------------------------------
    assert result is not None, "loader returned None — endpoint failed to load"
    _path, model = result
    assert model.tool is not None
    assert model.tool.description == NON_ASCII_DESCRIPTION, (
        "Tool description was corrupted on the way through the loader.\n"
        f"  expected: {NON_ASCII_DESCRIPTION!r}\n"
        f"  got:      {model.tool.description!r}\n"
        "This is the UTF-8-read-as-cp1252 bug: open() needs encoding='utf-8'."
    )


@pytest.mark.skipif(
    _default_encoding_is_utf8(),
    reason="Platform default is UTF-8; cp1252 mis-decode cannot occur here.",
)
def test_discover_tools_preserves_utf8_description(tmp_path, monkeypatch):
    """Same bug via the discovery path (discover_tools -> _discover_in_directory)."""
    (tmp_path / "mxcp-site.yml").write_text(
        "mxcp: 1\nproject: enc_test\nprofile: default\n",
        encoding="utf-8",
    )
    tools_dir = tmp_path / "tools"
    tools_dir.mkdir()
    (tools_dir / "summarize.yml").write_text(
        "mxcp: 1\n"
        "tool:\n"
        "  name: summarize\n"
        f"  description: {NON_ASCII_DESCRIPTION!r}\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    loader = EndpointLoader(SiteConfigModel(project="enc_test", profile="default"))
    discovered = loader.discover_tools()

    # Exactly one file, loaded without error.
    assert len(discovered) == 1
    _path, model, error = discovered[0]
    assert error is None, f"loader reported an error: {error}"
    assert model is not None and model.tool is not None
    assert model.tool.description == NON_ASCII_DESCRIPTION


def test_environment_report():
    """Always-on: print the encoding context so a Windows run is self-documenting.

    Not an assertion — it makes the skip/run decision auditable in CI logs, so a
    green result can't be mistaken for 'tested but passed' when it was skipped.
    """
    print()
    print(f"locale.getpreferredencoding(False) = {locale.getpreferredencoding(False)!r}")
    print(f"PYTHONUTF8 = {os.environ.get('PYTHONUTF8')!r}")
    print(f"sys default encoding utf-8? {_default_encoding_is_utf8()}")
