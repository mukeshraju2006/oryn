"""Cloud client retry and timing regression tests."""

from urllib.error import URLError

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
