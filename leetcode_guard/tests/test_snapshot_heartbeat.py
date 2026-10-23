"""Tests for the content-deduplicated push and the per-minute heartbeat.

Writing the whole ~32 KB snapshot every minute was ~46 MB/day. The full node
is now written only when its content -- everything but ``generated_at`` --
changed since the last successful write; a ~30-byte heartbeat carries the
per-minute freshness instead.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from leetcode_guard import _snapshot_dedup
from leetcode_guard._snapshot_dedup import (
    content_hash,
    read_pushed_hash,
    write_pushed_hash,
)
from leetcode_guard._snapshot_push import HEARTBEAT_PATH, SNAPSHOT_PATH, push_snapshot

if TYPE_CHECKING:
    from pathlib import Path


class FakeStore:
    def __init__(self, fail_on: str | None = None) -> None:
        self.writes: list[tuple[str, str]] = []
        self.fail_on = fail_on

    def put_file_text(self, path: str, text: str, *, message: str) -> None:
        if path == self.fail_on:
            from crdt_sync import FirebaseSyncError

            message = f"HTTP 500 on {path}"
            raise FirebaseSyncError(message)
        self.writes.append((path, text))


def snap(minute: int, credits_: int = 1) -> dict[str, object]:
    return {
        "schema": 1,
        "generated_at": f"2026-10-23T15:{minute:02d}:00+02:00",
        "status": {"credits": credits_},
    }


def test_the_hash_ignores_only_generated_at():
    assert content_hash(snap(1)) == content_hash(snap(2))
    assert content_hash(snap(1)) != content_hash(snap(1, credits_=2))


def test_first_push_writes_the_snapshot_then_the_heartbeat(data_dir: Path):
    store = FakeStore()

    result = push_snapshot(snap(1), connect=lambda: store)

    assert [path for path, _ in store.writes] == [SNAPSHOT_PATH, HEARTBEAT_PATH]
    assert HEARTBEAT_PATH == "leetcode-guard/heartbeat"
    assert json.loads(store.writes[0][1])["generated_at"].endswith("15:01:00+02:00")
    assert store.writes[1][1] == "2026-10-23T15:01:00+02:00"
    assert result.pushed
    assert "heartbeat" in result.reason


def test_unchanged_content_writes_only_the_heartbeat(data_dir: Path):
    push_snapshot(snap(1), connect=FakeStore)
    store = FakeStore()

    result = push_snapshot(snap(2), connect=lambda: store)

    assert store.writes == [(HEARTBEAT_PATH, "2026-10-23T15:02:00+02:00")]
    assert result.pushed
    assert result.reason.startswith("unchanged")


def test_changed_content_writes_the_snapshot_again(data_dir: Path):
    push_snapshot(snap(1), connect=FakeStore)
    store = FakeStore()

    push_snapshot(snap(2, credits_=5), connect=lambda: store)

    assert [path for path, _ in store.writes] == [SNAPSHOT_PATH, HEARTBEAT_PATH]


def test_a_failed_snapshot_write_records_nothing_and_beats_nothing(data_dir: Path):
    """A fresh heartbeat over stale content would hide the failure from the app."""
    failing = FakeStore(fail_on=SNAPSHOT_PATH)

    result = push_snapshot(snap(1), connect=lambda: failing)

    assert not result.pushed
    assert failing.writes == []
    assert read_pushed_hash() is None
    retry = FakeStore()
    push_snapshot(snap(2), connect=lambda: retry)
    assert [path for path, _ in retry.writes] == [SNAPSHOT_PATH, HEARTBEAT_PATH]


def test_a_failed_heartbeat_is_reported(
    data_dir: Path, caplog: pytest.LogCaptureFixture
):
    result = push_snapshot(snap(1), connect=lambda: FakeStore(fail_on=HEARTBEAT_PATH))

    assert not result.pushed
    assert "snapshot push failed" in caplog.text
    # The snapshot itself landed, so the next minute need not resend it.
    assert read_pushed_hash() == content_hash(snap(1))


def test_the_state_file_is_redirected(tmp_path: Path):
    assert _snapshot_dedup.PUSH_STATE_FILE.is_relative_to(tmp_path)


@pytest.mark.parametrize("text", ["{not json", "[]", '{"hash": 5}'])
def test_an_unusable_state_file_means_resend(
    tmp_path: Path, text: str, caplog: pytest.LogCaptureFixture
):
    path = tmp_path / "state.json"
    path.write_text(text, encoding="utf-8")

    assert read_pushed_hash(path) is None
    assert "snapshot push state" in caplog.text


def test_the_state_round_trips(tmp_path: Path):
    path = tmp_path / "state.json"

    assert write_pushed_hash("abc", path)
    assert read_pushed_hash(path) == "abc"


def test_an_unwritable_state_file_is_a_warning(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
):
    blocker = tmp_path / "file"
    blocker.write_text("x", encoding="utf-8")

    assert not write_pushed_hash("abc", blocker / "state.json")
    assert "could not record" in caplog.text
