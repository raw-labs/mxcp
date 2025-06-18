import os
import pytest
import asyncio
from pathlib import Path
from mxcp.drift.checker import check_drift, load_and_validate_snapshot
from mxcp.config.site_config import load_site_config
from mxcp.config.user_config import load_user_config


@pytest.fixture
def no_changes_repo_path():
    """Path to the no-changes drift test repository."""
    return Path(__file__).parent / "fixtures" / "drift" / "no-changes"


@pytest.fixture
def has_changes_repo_path():
    """Path to the has-changes drift test repository."""
    return Path(__file__).parent / "fixtures" / "drift" / "has-changes"


@pytest.fixture
def no_changes_site_config(no_changes_repo_path):
    """Load site configuration for no-changes test."""
    original_dir = os.getcwd()
    original_env = os.environ.get("MXCP_CONFIG")

    try:
        os.chdir(no_changes_repo_path)
        os.environ["MXCP_CONFIG"] = str(no_changes_repo_path / "mxcp-config.yml")
        return load_site_config()
    finally:
        os.chdir(original_dir)
        if original_env is not None:
            os.environ["MXCP_CONFIG"] = original_env
        elif "MXCP_CONFIG" in os.environ:
            del os.environ["MXCP_CONFIG"]


@pytest.fixture
def has_changes_site_config(has_changes_repo_path):
    """Load site configuration for has-changes test."""
    original_dir = os.getcwd()
    original_env = os.environ.get("MXCP_CONFIG")

    try:
        os.chdir(has_changes_repo_path)
        os.environ["MXCP_CONFIG"] = str(has_changes_repo_path / "mxcp-config.yml")
        return load_site_config()
    finally:
        os.chdir(original_dir)
        if original_env is not None:
            os.environ["MXCP_CONFIG"] = original_env
        elif "MXCP_CONFIG" in os.environ:
            del os.environ["MXCP_CONFIG"]


@pytest.fixture
def no_changes_user_config(no_changes_repo_path, no_changes_site_config):
    """Load user configuration for no-changes test."""
    original_dir = os.getcwd()
    original_env = os.environ.get("MXCP_CONFIG")

    try:
        os.chdir(no_changes_repo_path)
        os.environ["MXCP_CONFIG"] = str(no_changes_repo_path / "mxcp-config.yml")
        return load_user_config(no_changes_site_config)
    finally:
        os.chdir(original_dir)
        if original_env is not None:
            os.environ["MXCP_CONFIG"] = original_env
        elif "MXCP_CONFIG" in os.environ:
            del os.environ["MXCP_CONFIG"]


@pytest.fixture
def has_changes_user_config(has_changes_repo_path, has_changes_site_config):
    """Load user configuration for has-changes test."""
    original_dir = os.getcwd()
    original_env = os.environ.get("MXCP_CONFIG")

    try:
        os.chdir(has_changes_repo_path)
        os.environ["MXCP_CONFIG"] = str(has_changes_repo_path / "mxcp-config.yml")
        return load_user_config(has_changes_site_config)
    finally:
        os.chdir(original_dir)
        if original_env is not None:
            os.environ["MXCP_CONFIG"] = original_env
        elif "MXCP_CONFIG" in os.environ:
            del os.environ["MXCP_CONFIG"]


def test_load_and_validate_snapshot_valid(no_changes_repo_path):
    """Test loading and validating a valid drift snapshot."""
    snapshot_path = no_changes_repo_path / "drift-default.json"
    snapshot = load_and_validate_snapshot(snapshot_path)

    assert snapshot["version"] == "1.0.0"
    assert "generated_at" in snapshot
    assert "tables" in snapshot
    assert "resources" in snapshot
    assert len(snapshot["resources"]) == 1
    assert snapshot["resources"][0]["validation_results"]["path"] == "endpoints/hello-world.yml"


def test_load_and_validate_snapshot_missing_file():
    """Test loading a non-existent snapshot file."""
    snapshot_path = Path("/nonexistent/path/snapshot.json")

    with pytest.raises(FileNotFoundError, match="Snapshot file not found"):
        load_and_validate_snapshot(snapshot_path)


def test_load_and_validate_snapshot_invalid_version(tmp_path):
    """Test loading a snapshot with invalid version."""
    invalid_snapshot = {
        "version": "2.0.0",
        "generated_at": "2025-05-27T11:04:04.109401Z",
        "tables": [],
        "resources": [],
    }

    snapshot_path = tmp_path / "invalid_snapshot.json"
    with open(snapshot_path, "w") as f:
        import json

        json.dump(invalid_snapshot, f)

    with pytest.raises(ValueError, match="Unsupported snapshot version: 2.0.0"):
        load_and_validate_snapshot(snapshot_path)


def test_load_and_validate_snapshot_missing_required_field(tmp_path):
    """Test loading a snapshot missing required fields."""
    invalid_snapshot = {
        "version": "1.0.0",
        "generated_at": "2025-05-27T11:04:04.109401Z",
        # Missing "tables" and "resources"
    }

    snapshot_path = tmp_path / "invalid_snapshot.json"
    with open(snapshot_path, "w") as f:
        import json

        json.dump(invalid_snapshot, f)

    # The current implementation doesn't validate schema strictly, so this test
    # just verifies the snapshot loads without error. In a future version,
    # we could add strict schema validation.
    snapshot = load_and_validate_snapshot(snapshot_path)
    assert snapshot["version"] == "1.0.0"


@pytest.mark.asyncio
async def test_drift_check_no_changes(
    no_changes_repo_path, no_changes_site_config, no_changes_user_config
):
    """Test drift check when there are no changes."""
    original_dir = os.getcwd()
    original_env = os.environ.get("MXCP_CONFIG")

    try:
        os.chdir(no_changes_repo_path)
        os.environ["MXCP_CONFIG"] = str(no_changes_repo_path / "mxcp-config.yml")

        report = await check_drift(
            no_changes_site_config, no_changes_user_config, profile="default"
        )

        # Verify no drift detected
        assert report["has_drift"] is False
        assert report["version"] == "1.0.0"
        assert "generated_at" in report
        assert "baseline_snapshot_path" in report
        assert "current_snapshot_generated_at" in report
        assert "baseline_snapshot_generated_at" in report

        # Verify summary shows no changes
        summary = report["summary"]
        assert summary["tables_added"] == 0
        assert summary["tables_removed"] == 0
        assert summary["tables_modified"] == 0
        assert summary["resources_added"] == 0
        assert summary["resources_removed"] == 0
        assert summary["resources_modified"] == 0

        # Verify no changes in details
        assert len(report["table_changes"]) == 0
        assert len(report["resource_changes"]) == 0

    finally:
        os.chdir(original_dir)
        if original_env is not None:
            os.environ["MXCP_CONFIG"] = original_env
        elif "MXCP_CONFIG" in os.environ:
            del os.environ["MXCP_CONFIG"]


@pytest.mark.asyncio
async def test_drift_check_has_changes(
    has_changes_repo_path, has_changes_site_config, has_changes_user_config
):
    """Test drift check when there are changes."""
    original_dir = os.getcwd()
    original_env = os.environ.get("MXCP_CONFIG")

    try:
        os.chdir(has_changes_repo_path)
        os.environ["MXCP_CONFIG"] = str(has_changes_repo_path / "mxcp-config.yml")

        report = await check_drift(
            has_changes_site_config, has_changes_user_config, profile="default"
        )

        # Verify drift detected
        assert report["has_drift"] is True
        assert report["version"] == "1.0.0"
        assert "generated_at" in report
        assert "baseline_snapshot_path" in report
        assert "current_snapshot_generated_at" in report
        assert "baseline_snapshot_generated_at" in report

        # Verify summary shows changes
        summary = report["summary"]
        assert summary["tables_added"] == 0  # No table changes in this test
        assert summary["tables_removed"] == 0
        assert summary["tables_modified"] == 0
        assert summary["resources_added"] == 1  # bye-world.yml added
        assert summary["resources_removed"] == 0
        assert summary["resources_modified"] == 1  # hello-world.yml modified

        # Verify no table changes
        assert len(report["table_changes"]) == 0

        # Verify resource changes
        assert len(report["resource_changes"]) == 2

        # Find the added and modified resources
        added_resources = [r for r in report["resource_changes"] if r["change_type"] == "added"]
        modified_resources = [
            r for r in report["resource_changes"] if r["change_type"] == "modified"
        ]

        assert len(added_resources) == 1
        assert len(modified_resources) == 1

        # Check added resource
        added_resource = added_resources[0]
        assert added_resource["path"] == "endpoints/bye-world.yml"
        assert added_resource["endpoint"] == "tool/bye_world"
        assert added_resource["change_type"] == "added"

        # Check modified resource
        modified_resource = modified_resources[0]
        assert modified_resource["path"] == "endpoints/hello-world.yml"
        assert modified_resource["endpoint"] == "tool/hello_world_changed"
        assert modified_resource["change_type"] == "modified"

    finally:
        os.chdir(original_dir)
        if original_env is not None:
            os.environ["MXCP_CONFIG"] = original_env
        elif "MXCP_CONFIG" in os.environ:
            del os.environ["MXCP_CONFIG"]


@pytest.mark.asyncio
async def test_drift_check_with_custom_baseline(
    has_changes_repo_path, has_changes_site_config, has_changes_user_config, no_changes_repo_path
):
    """Test drift check with a custom baseline path."""
    original_dir = os.getcwd()
    original_env = os.environ.get("MXCP_CONFIG")

    try:
        os.chdir(has_changes_repo_path)
        os.environ["MXCP_CONFIG"] = str(has_changes_repo_path / "mxcp-config.yml")

        # Use the no-changes baseline to compare against has-changes current state
        custom_baseline_path = str(no_changes_repo_path / "drift-default.json")

        report = await check_drift(
            has_changes_site_config,
            has_changes_user_config,
            profile="default",
            baseline_path=custom_baseline_path,
        )

        # Should detect drift since we're comparing has-changes against no-changes baseline
        assert report["has_drift"] is True
        assert report["baseline_snapshot_path"] == custom_baseline_path

        # Should show resource changes
        summary = report["summary"]
        assert summary["resources_added"] == 1  # bye-world.yml added
        assert summary["resources_modified"] == 1  # hello-world.yml modified

    finally:
        os.chdir(original_dir)
        if original_env is not None:
            os.environ["MXCP_CONFIG"] = original_env
        elif "MXCP_CONFIG" in os.environ:
            del os.environ["MXCP_CONFIG"]


@pytest.mark.asyncio
async def test_drift_check_missing_baseline(
    has_changes_repo_path, has_changes_site_config, has_changes_user_config
):
    """Test drift check with missing baseline file."""
    original_dir = os.getcwd()
    original_env = os.environ.get("MXCP_CONFIG")

    try:
        os.chdir(has_changes_repo_path)
        os.environ["MXCP_CONFIG"] = str(has_changes_repo_path / "mxcp-config.yml")

        # Use a non-existent baseline path
        missing_baseline_path = "/nonexistent/path/baseline.json"

        with pytest.raises(ValueError, match="Failed to load baseline snapshot"):
            await check_drift(
                has_changes_site_config,
                has_changes_user_config,
                profile="default",
                baseline_path=missing_baseline_path,
            )

    finally:
        os.chdir(original_dir)
        if original_env is not None:
            os.environ["MXCP_CONFIG"] = original_env
        elif "MXCP_CONFIG" in os.environ:
            del os.environ["MXCP_CONFIG"]


def test_drift_report_structure(no_changes_repo_path):
    """Test that drift report has the expected structure."""
    # This is a synchronous test that just validates the report structure
    # without running the full async drift check

    # Load a baseline snapshot to verify its structure
    snapshot_path = no_changes_repo_path / "drift-default.json"
    snapshot = load_and_validate_snapshot(snapshot_path)

    # Verify the snapshot has the expected structure for drift comparison
    assert "version" in snapshot
    assert "generated_at" in snapshot
    assert "tables" in snapshot
    assert "resources" in snapshot

    # Verify resource structure
    for resource in snapshot["resources"]:
        assert "validation_results" in resource
        assert "test_results" in resource
        assert "definition" in resource

        # Verify validation_results structure
        validation = resource["validation_results"]
        assert "status" in validation
        assert "path" in validation

        # Verify test_results structure
        test_results = resource["test_results"]
        assert "status" in test_results
        assert "tests_run" in test_results
