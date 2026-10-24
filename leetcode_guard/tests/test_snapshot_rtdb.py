"""Tests for the echo-free RTDB write the snapshot push goes through.

RTDB's REST PUT echoes the written body back unless asked not to. At ~32 KB a
push and a push a minute that is ~1.4 GB/month of the Spark plan's download
quota, which every kuhy app shares -- for a response nobody reads.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import TYPE_CHECKING

from crdt_sync import FirebaseSyncError
import pytest
import requests

from leetcode_guard import _snapshot_push, _snapshot_rtdb
from leetcode_guard._snapshot_rtdb import SilentStore

if TYPE_CHECKING:
    from pathlib import Path

PATH = "leetcode-guard/status"


class FakeResponse:
    def __init__(self, status: int, text: str = "") -> None:
        self.status_code = status
        self.ok = status < 400
        self.text = text


def test_the_write_asks_for_no_echo(monkeypatch: pytest.MonkeyPatch):
    seen: dict[str, object] = {}

    def fake_put(url: str, **kwargs: object) -> FakeResponse:
        seen["url"] = url
        seen.update(kwargs)
        return FakeResponse(204)

    monkeypatch.setattr(_snapshot_rtdb.requests, "put", fake_put)
    store = SilentStore("https://db.example/", lambda: "tok", 3.0)

    store.put_file_text(PATH, '{"schema":1}', message="m")

    assert seen["url"] == "https://db.example/leetcode-guard/status.json"
    assert seen["params"] == {"auth": "tok", "print": "silent"}
    assert seen["json"] == '{"schema":1}'
    assert seen["timeout"] == 3.0


def test_a_rejected_write_is_a_sync_error(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        _snapshot_rtdb.requests,
        "put",
        lambda *_a, **_k: FakeResponse(401, "Permission denied"),
    )
    store = SilentStore("https://db", lambda: "tok", 1.0)

    with pytest.raises(FirebaseSyncError, match="HTTP 401 Permission denied"):
        store.put_file_text(PATH, "{}", message="m")


def test_a_network_error_is_a_sync_error(monkeypatch: pytest.MonkeyPatch):
    def refuse(*_a: object, **_k: object) -> FakeResponse:
        message = "connection reset"
        raise requests.ConnectionError(message)

    monkeypatch.setattr(_snapshot_rtdb.requests, "put", refuse)
    store = SilentStore("https://db", lambda: "tok", 1.0)

    with pytest.raises(FirebaseSyncError, match="network error"):
        store.put_file_text(PATH, "{}", message="m")


def test_the_default_store_wraps_the_signed_in_client(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    config = tmp_path / "firebase.json"
    config.write_text(
        json.dumps(
            {
                "apiKey": "k",
                "databaseUrl": "https://db.example",
                "projectId": "p",
                "uid": "u",
                "email": "e@x",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(_snapshot_rtdb, "CONFIG_FILE", config)
    client = SimpleNamespace(auth=SimpleNamespace(id_token=lambda: "tok"))
    monkeypatch.setattr(_snapshot_push, "sign_in", lambda *_a, **_k: client)

    store = _snapshot_push._firebase_client()

    assert isinstance(store, SilentStore)
    assert store.database_url == "https://db.example"
    assert store.id_token() == "tok"


def test_get_json_reads_a_node(monkeypatch: pytest.MonkeyPatch):
    seen: dict[str, object] = {}

    def fake_get(url: str, **kwargs: object) -> FakeResponse:
        seen["url"] = url
        seen.update(kwargs)
        return FakeResponse(200, '{"a": "x"}')

    monkeypatch.setattr(_snapshot_rtdb.requests, "get", fake_get)
    store = SilentStore("https://db.example/", lambda: "tok", 3.0)

    assert store.get_json("leetcode-guard/app_errors") == {"a": "x"}
    assert seen["url"] == "https://db.example/leetcode-guard/app_errors.json"
    assert seen["params"] == {"auth": "tok"}


@pytest.mark.parametrize("verb", ["get", "put"])
def test_rtdb_failures_never_carry_the_token(
    monkeypatch: pytest.MonkeyPatch, verb: str
):
    def refuse(url: str, **_k: object) -> FakeResponse:
        message = f"Max retries exceeded with url: {url}?auth=SECRET"
        raise requests.ConnectionError(message)

    monkeypatch.setattr(_snapshot_rtdb.requests, verb, refuse)
    store = SilentStore("https://db", lambda: "SECRET", 1.0)

    call = (
        (lambda: store.get_json("p"))
        if verb == "get"
        else (lambda: store.put_file_text("p", "{}", message="m"))
    )
    with pytest.raises(FirebaseSyncError) as caught:
        call()
    assert "SECRET" not in str(caught.value)
    assert "ConnectionError" in str(caught.value)


def test_a_rejected_read_is_a_sync_error(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        _snapshot_rtdb.requests, "get", lambda *_a, **_k: FakeResponse(401, "no")
    )
    with pytest.raises(FirebaseSyncError, match="HTTP 401"):
        SilentStore("https://db", lambda: "t", 1.0).get_json("p")
