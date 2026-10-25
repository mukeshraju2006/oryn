"""Snapshot payload migration tests."""

import pytest

from oryn.core.snapshot import migrate_snapshot_data


def test_legacy_snapshot_gets_missing_browser_urls_without_mutating_source():
    legacy = {
        "version": 4,
        "application": "vscode",
        "workspace": {"path": "/tmp/project"},
        "files": [],
    }
    migrated = migrate_snapshot_data(legacy)
    assert migrated["browser_urls"] == []
    assert migrated["version"] == 4
    assert "browser_urls" not in legacy


def test_current_snapshot_keeps_browser_urls():
    payload = {"version": 5, "browser_urls": ["https://example.com"], "files": []}
    assert migrate_snapshot_data(payload)["browser_urls"] == ["https://example.com"]


@pytest.mark.parametrize("payload", [
    {"version": 0},
    {"version": True},
    {"version": 6},
    {"version": 5, "browser_urls": "not-a-list"},
    {"version": 5, "files": {}},
    {"version": 5, "workspace": []},
])
def test_invalid_or_future_snapshot_payload_is_rejected(payload):
    with pytest.raises(ValueError):
        migrate_snapshot_data(payload)
