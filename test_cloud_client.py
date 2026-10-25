"""Cloud client retry and timing regression tests."""

import json
from urllib.error import URLError

from oryn.core.snapshot import migrate_snapshot_data

import pytest

from oryn.cloud.client import CloudClient


class FakeResponse:
    status = 200
    headers = {"X-Oryn-Process-Time": "0.012"}

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return b'{"ok":true}'


def test_get_request_retries_once_and_records_timing(monkeypatch):
    calls = []
    def fake_urlopen(request, timeout):
        calls.append((request, timeout))
        if len(calls) == 1:
            raise URLError("temporary network failure")
        return FakeResponse()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    monkeypatch.setattr("time.sleep", lambda _seconds: None)
    client = CloudClient(base_url="https://example.invalid")

    assert client.list_workspaces() == {"ok": True}
    assert len(calls) == 2
    assert client.last_request_metrics["method"] == "GET"
    assert client.last_request_metrics["server_seconds"] == 0.012
    assert client.last_request_metrics["response_bytes"] == len(b'{"ok":true}')


def test_mutating_request_is_not_retried(monkeypatch):
    calls = []
    def fake_urlopen(request, timeout):
        calls.append(request)
        raise URLError("temporary network failure")

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    monkeypatch.setattr("time.sleep", lambda _seconds: None)
    client = CloudClient(base_url="https://example.invalid")

    with pytest.raises(URLError):
        client.create_workspace("Example")
    assert len(calls) == 1



def test_snapshot_upload_adds_a_valid_integrity_checksum(monkeypatch):
    client = CloudClient(base_url="https://example.invalid")
    captured = {}

    def fake_request(url, data=None, method="GET", content_encoding=None):
        captured["payload"] = json.loads(data.decode("utf-8"))
        captured["method"] = method
        captured["encoding"] = content_encoding
        return {"id": 4}

    monkeypatch.setattr(client, "_request", fake_request)

    class SnapshotStub:
        def to_dict(self):
            return {
                "version": 5,
                "application": "vscode",
                "workspace": {"path": "/tmp/project"},
                "files": [],
                "browser_urls": [],
            }

    assert client.create_snapshot(3, SnapshotStub()) == {"id": 4}
    assert captured["method"] == "POST"
    assert captured["payload"]["_integrity"]["algorithm"] == "sha256"
    assert migrate_snapshot_data(captured["payload"])["application"] == "vscode"
