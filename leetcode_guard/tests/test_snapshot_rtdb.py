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
from leetcode_guard._snapshot_push import SNAPSHOT_PATH, _firebase_client
from leetcode_guard._snapshot_rtdb import SilentStore
from leetcode_guard.tests._memory_remote import MemoryRemote

if TYPE_CHECKING:
    from pathlib import Path

PATH = "leetcode-guard/snapshot-e2e/status"


class FakeResponse:
    """The slice of ``requests.Response`` the store reads."""

    def __init__(self, status: int, text: str = "") -> None:
        self.status_code = status
        self.ok = status < 400
        self.text = text


def test_the_write_asks_for_no_echo(monkeypatch: pytest.MonkeyPatch):
    """The PUT goes to the node's .json URL with ``print=silent``."""
    seen: dict[str, object] = {}

    def fake_put(url: str, **kwargs: object) -> FakeResponse:
        """Record the PUT and answer 204."""
        seen["url"] = url
        seen.update(kwargs)
        return FakeResponse(204)

    monkeypatch.setattr(_snapshot_rtdb.requests, "put", fake_put)
    store = SilentStore("https://db.example/", lambda: "tok", 3.0, MemoryRemote())

    store.put_file_text(PATH, '{"schema":1}', message="m")

    assert seen["url"] == "https://db.example/leetcode-guard/snapshot-e2e/status.json"
    assert seen["params"] == {"auth": "tok", "print": "silent"}
    assert seen["json"] == '{"schema":1}'
    assert seen["timeout"] == 3.0


def test_a_rejected_write_is_a_sync_error(monkeypatch: pytest.MonkeyPatch):
    """An HTTP error on write raises FirebaseSyncError with the status."""
    monkeypatch.setattr(
        _snapshot_rtdb.requests,
        "put",
        lambda *_a, **_k: FakeResponse(401, "Permission denied"),
    )
    store = SilentStore("https://db", lambda: "tok", 1.0, MemoryRemote())

    with pytest.raises(FirebaseSyncError, match="HTTP 401 Permission denied"):
        store.put_file_text(PATH, "{}", message="m")


def test_a_network_error_is_a_sync_error(monkeypatch: pytest.MonkeyPatch):
    """A connection error on write raises FirebaseSyncError."""

    def refuse(*_a: object, **_k: object) -> FakeResponse:
        """Fail the request with a connection reset."""
        message = "connection reset"
        raise requests.ConnectionError(message)

    monkeypatch.setattr(_snapshot_rtdb.requests, "put", refuse)
    store = SilentStore("https://db", lambda: "tok", 1.0, MemoryRemote())

    with pytest.raises(FirebaseSyncError, match="network error"):
        store.put_file_text(PATH, "{}", message="m")


def test_the_default_store_wraps_the_signed_in_client(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    """The default writer seals, then writes silently over the session."""
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
    remote = MemoryRemote()
    client = SimpleNamespace(
        auth=SimpleNamespace(id_token=lambda: "tok"),
        list_directory=remote.list_directory,
        get_file_text=remote.get_file_text,
        put_file_text=remote.put_file_text,
        delete_file=remote.delete_file,
    )
    monkeypatch.setattr(_snapshot_push, "sign_in", lambda *_a, **_k: client)
    sent: list[tuple[str, object]] = []

    def fake_put(url: str, **kwargs: object) -> FakeResponse:
        """Record what went over the wire and answer 204."""
        sent.append((url, kwargs["json"]))
        return FakeResponse(204)

    monkeypatch.setattr(_snapshot_rtdb.requests, "put", fake_put)

    _firebase_client().put_file_text(SNAPSHOT_PATH, '{"schema":1}', message="m")

    assert len(sent) == 1
    url, body = sent[0]
    assert url == f"https://db.example/{SNAPSHOT_PATH}.json"
    assert "schema" not in str(body)


def test_reads_go_to_the_signed_in_client():
    """Every read and delete is the client's: only the write is silent."""
    remote = MemoryRemote()
    remote.data["a/b"] = "x"
    store = SilentStore("https://db", lambda: "t", 1.0, remote)

    assert store.list_directory("a") == ["b"]
    assert store.get_file_text("a/b") == "x"
    store.delete_file("a/b")
    assert remote.data == {}


def test_rtdb_failures_never_carry_the_token(monkeypatch: pytest.MonkeyPatch):
    """A write failure does not leak the auth token."""

    def refuse(url: str, **_k: object) -> FakeResponse:
        """Fail with an error message that embeds the token."""
        message = f"Max retries exceeded with url: {url}?auth=SECRET"
        raise requests.ConnectionError(message)

    monkeypatch.setattr(_snapshot_rtdb.requests, "put", refuse)
    store = SilentStore("https://db", lambda: "SECRET", 1.0, MemoryRemote())

    with pytest.raises(FirebaseSyncError) as caught:
        store.put_file_text("p", "{}", message="m")
    assert "SECRET" not in str(caught.value)
    assert "ConnectionError" in str(caught.value)
