"""Snapshot integrity verification tests."""

import hashlib
import json

import pytest

from oryn.core.snapshot import migrate_snapshot_data


def with_integrity(payload):
    canonical = json.dumps(payload, separators=(",", ":"), ensure_ascii=False, sort_keys=True).encode("utf-8")
    result = dict(payload)
    result["_integrity"] = {
        "algorithm": "sha256",
        "digest": hashlib.sha256(canonical).hexdigest(),
    }
    return result


def test_valid_snapshot_integrity_is_accepted():
    payload = with_integrity({
        "version": 5,
        "application": "vscode",
        "workspace": {"path": "/tmp/project"},
        "files": [],
        "browser_urls": [],
    })
    assert migrate_snapshot_data(payload)["application"] == "vscode"


def test_tampered_snapshot_integrity_is_rejected():
    payload = with_integrity({
        "version": 5,
        "application": "vscode",
        "workspace": {"path": "/tmp/project"},
        "files": [],
        "browser_urls": [],
    })
    payload["workspace"]["path"] = "/tmp/changed"
    with pytest.raises(ValueError, match="integrity check failed"):
        migrate_snapshot_data(payload)


def test_malformed_integrity_metadata_is_rejected():
    with pytest.raises(ValueError, match="integrity metadata"):
        migrate_snapshot_data({"version": 5, "_integrity": "invalid"})
