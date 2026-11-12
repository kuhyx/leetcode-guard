"""Tests for the local snapshot file and the ``status_hash`` node.

The desktop app reads ``~/.local/share/leetcode_guard/snapshot.json`` with no
Firebase at all, so it is written on every push attempt -- before the network
is touched, so an offline minute still refreshes it. The phone polls the tiny
heartbeat plus ``status_hash`` and downloads the ~49 KB status
only when the hash moved, so the hash is written with every full write.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from crdt_sync import ConfigError
import pytest

from leetcode_guard import _snapshot_local
from leetcode_guard._snapshot_dedup import content_hash, read_pushed_hash
from leetcode_guard._snapshot_local import write_local_snapshot
from leetcode_guard._snapshot_push import (
    HEARTBEAT_PATH,
    SNAPSHOT_PATH,
    STATUS_HASH_PATH,
    push_snapshot,
)
from leetcode_guard.tests.test_snapshot_heartbeat import FakeStore, snap

if TYPE_CHECKING:
    from pathlib import Path


def _local() -> dict[str, object]:
    """Read the redirected local snapshot file back as JSON."""
    loaded: dict[str, object] = json.loads(
        _snapshot_local.LOCAL_SNAPSHOT_FILE.read_text(encoding="utf-8")
    )
    return loaded


def test_the_local_file_is_redirected(tmp_path: Path):
    """The local snapshot path is snapshot.json under the test's tmp dir."""
    assert _snapshot_local.LOCAL_SNAPSHOT_FILE.is_relative_to(tmp_path)
    assert _snapshot_local.LOCAL_SNAPSHOT_FILE.name == "snapshot.json"


@pytest.mark.usefixtures("data_dir")
def test_a_push_writes_the_local_file():
    """A push mirrors the snapshot to the local file."""
    push_snapshot(snap(1), connect=FakeStore)

    assert _local() == snap(1)


@pytest.mark.usefixtures("data_dir")
def test_an_unchanged_push_still_refreshes_the_local_file():
    """The desktop has no heartbeat: the file's own generated_at is its freshness."""
    push_snapshot(snap(1), connect=FakeStore)
    push_snapshot(snap(2), connect=FakeStore)

    assert _local() == snap(2)


@pytest.mark.usefixtures("data_dir")
def test_an_offline_push_still_writes_the_local_file():
    """The local file is written before the network, so offline still refreshes it."""

    def offline() -> FakeStore:
        """Fail to connect the way a machine with no network does."""
        message = "no network"
        raise ConfigError(message)

    result = push_snapshot(snap(3), connect=offline)

    assert not result.pushed
    assert _local() == snap(3)


def test_a_failed_local_write_is_a_warning_and_the_push_goes_on(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, caplog: pytest.LogCaptureFixture
):
    """An unwritable local file only warns; the Firebase push still happens."""
    blocker = tmp_path / "file"
    blocker.write_text("x", encoding="utf-8")
    monkeypatch.setattr(_snapshot_local, "LOCAL_SNAPSHOT_FILE", blocker / "s.json")
    store = FakeStore()

    result = push_snapshot(snap(1), connect=lambda: store)

    assert result.pushed
    assert "could not write the local snapshot" in caplog.text
    assert store.writes[0][0] == SNAPSHOT_PATH


def test_the_local_write_reports_success(tmp_path: Path):
    """A local write creates missing parent dirs and returns True."""
    target = tmp_path / "deep" / "snapshot.json"

    assert write_local_snapshot(snap(4), target)
    assert json.loads(target.read_text(encoding="utf-8")) == snap(4)


@pytest.mark.usefixtures("data_dir")
def test_a_full_write_publishes_its_hash_between_status_and_heartbeat():
    """A full write puts the content hash at status_hash, between status and beat."""
    store = FakeStore()

    push_snapshot(snap(1), connect=lambda: store)

    assert STATUS_HASH_PATH == "leetcode-guard/snapshot-e2e/status_hash"
    assert [path for path, _ in store.writes] == [
        SNAPSHOT_PATH,
        STATUS_HASH_PATH,
        HEARTBEAT_PATH,
    ]
    assert dict(store.writes)[STATUS_HASH_PATH] == content_hash(snap(1))


@pytest.mark.usefixtures("data_dir")
def test_an_unchanged_push_does_not_rewrite_the_hash():
    """An unchanged push leaves status_hash alone and writes only the beat."""
    push_snapshot(snap(1), connect=FakeStore)
    store = FakeStore()

    push_snapshot(snap(2), connect=lambda: store)

    assert [path for path, _ in store.writes] == [HEARTBEAT_PATH]


@pytest.mark.usefixtures("data_dir")
def test_a_failed_hash_write_resends_both_next_time():
    """Recording the push before the hash lands would leave the phone's hash stale."""
    failing = FakeStore(fail_on=STATUS_HASH_PATH)

    result = push_snapshot(snap(1), connect=lambda: failing)

    assert not result.pushed
    assert read_pushed_hash(target=SNAPSHOT_PATH) is None
    retry = FakeStore()
    push_snapshot(snap(2), connect=lambda: retry)
    assert [path for path, _ in retry.writes] == [
        SNAPSHOT_PATH,
        STATUS_HASH_PATH,
        HEARTBEAT_PATH,
    ]
