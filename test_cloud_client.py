"""Cloud client retry and timing regression tests."""

import base64
import hashlib
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

    result = client.create_snapshot(3, SnapshotStub())
    assert result["id"] == 4
    assert result["_client_capture"]["omitted_project_files"] == []
    assert captured["method"] == "POST"
    assert captured["payload"]["_integrity"]["algorithm"] == "sha256"
    assert migrate_snapshot_data(captured["payload"])["application"] == "vscode"



def test_large_snapshot_uploads_every_project_file_in_verified_chunks(monkeypatch):
    import base64
    import hashlib
    import random

    client = CloudClient(base_url="https://example.invalid")
    captured = {"chunks": {}, "requests": []}
    random_bytes = random.Random(42).randbytes(4_000_000)
    encoded = base64.b64encode(random_bytes).decode("ascii")

    class SnapshotStub:
        def to_dict(self):
            return {
                "version": 5,
                "application": "vscode",
                "workspace": {"path": "/tmp/project"},
                "files": [],
                "browser_urls": [],
                "project": {
                    "root": ".",
                    "directories": [],
                    "files": [{
                        "path": "assets/large.bin",
                        "data": encoded,
                        "size": len(random_bytes),
                        "encoding": "base64",
                    }],
                },
            }

    def fake_request(url, data=None, method="GET", content_encoding=None):
        captured["requests"].append((url, method, len(data or b"")))
        if url.endswith("/snapshot-uploads") and method == "POST":
            manifest = json.loads(data.decode("utf-8"))
            captured["manifest"] = manifest
            return {"upload_id": "upload-test", "chunk_bytes": 512 * 1024}
        if "/chunks/" in url and method == "PUT":
            index = int(url.rsplit("/", 1)[1])
            item = json.loads(data.decode("utf-8"))
            chunk = base64.b64decode(item["data"])
            assert hashlib.sha256(chunk).hexdigest() == item["sha256"]
            captured["chunks"][index] = chunk
            return {"uploaded": True}
        if url.endswith("/finalize") and method == "POST":
            return {"id": 9, "snapshot_number": 1, "verified": True}
        if method == "DELETE":
            return {"cancelled": True}
        raise AssertionError(f"Unexpected request: {method} {url}")

    monkeypatch.setattr(client, "_request", fake_request)
    result = client.create_snapshot(3, SnapshotStub())

    assert result["id"] == 9
    assert result["verified"] is True
    assert result["_client_capture"]["upload_mode"] == "verified-chunked"
    assert result["_client_capture"]["omitted_project_files"] == []
    assert result["_client_capture"]["project_files_included"] == 1
    assert all(size < 800 * 1024 for _, _, size in captured["requests"])
    reconstructed = b"".join(captured["chunks"][i] for i in range(len(captured["chunks"])))
    assert len(reconstructed) == captured["manifest"]["total_bytes"]
    assert hashlib.sha256(reconstructed).hexdigest() == captured["manifest"]["sha256"]
    payload = json.loads(reconstructed.decode("utf-8"))
    assert payload["project"]["files"][0]["path"] == "assets/large.bin"
    assert payload["project"]["files"][0]["data"] == encoded
    assert "omitted_files" not in payload["project"]
    assert migrate_snapshot_data(payload)["application"] == "vscode"


def test_large_snapshot_download_uses_verified_chunks(monkeypatch):
    import math

    client = CloudClient(base_url="https://example.invalid")
    payload = {
        "version": 5,
        "application": "vscode",
        "workspace": {"path": "/tmp/project"},
        "files": [],
        "browser_urls": [],
        "project": {
            "root": ".",
            "directories": [],
            "files": [{
                "path": "large.bin",
                "data": "x" * (4 * 1024 * 1024),
                "size": 4 * 1024 * 1024,
                "encoding": "base64",
            }],
        },
    }
    raw = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    chunk_bytes = 512 * 1024
    chunk_count = math.ceil(len(raw) / chunk_bytes)
    calls = []

    def fake_request(url, data=None, method="GET", content_encoding=None):
        calls.append(url)
        if url.endswith("/download-manifest"):
            return {
                "snapshot_id": 42,
                "total_bytes": len(raw),
                "chunk_bytes": chunk_bytes,
                "chunk_count": chunk_count,
                "sha256": hashlib.sha256(raw).hexdigest(),
            }
        if "/download-chunks/" in url:
            index = int(url.rsplit("/", 1)[1])
            chunk = raw[index * chunk_bytes:(index + 1) * chunk_bytes]
            return {
                "snapshot_id": 42,
                "chunk_index": index,
                "sha256": hashlib.sha256(chunk).hexdigest(),
                "data": base64.b64encode(chunk).decode("ascii"),
            }
        raise AssertionError(f"Unexpected request: {url}")

    monkeypatch.setattr(client, "_request", fake_request)
    result = client.get_snapshot(7, 42)

    assert result["project"]["files"][0]["path"] == "large.bin"
    assert len(calls) == chunk_count + 1
    assert all("/download-chunks/" in url for url in calls[1:])
