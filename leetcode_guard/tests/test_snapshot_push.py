"""Tests for publishing the snapshot to RTDB, and for its two triggers.

A push is display-only: every failure is a warning and a ``PushResult``, and
nothing here may raise into the harvest that calls it.
"""

from __future__ import annotations

from datetime import UTC, datetime
import json
from typing import TYPE_CHECKING

from crdt_sync import ConfigError, FirebaseSyncError
import pytest

from leetcode_guard import (
    _cli,
    _harvest_run,
    _snapshot_push,
    _status_full,
    _status_timer,
)
from leetcode_guard._snapshot_push import (
    SNAPSHOT_PATH,
    PushResult,
    cmd_push_snapshot,
    gather_snapshot,
    push_quietly,
    push_snapshot,
)

if TYPE_CHECKING:
    from pathlib import Path


BEAT = {"schema": 1, "generated_at": "2026-10-23T15:00:00+02:00"}


class FakeStore:
    """Records ``put_file_text`` calls, or fails them."""

    def __init__(self, error: Exception | None = None) -> None:
        self.writes: list[tuple[str, str]] = []
        self.error = error

    def put_file_text(self, path: str, text: str, *, message: str) -> None:
        if self.error is not None:
            raise self.error
        self.writes.append((path, text))


@pytest.fixture
def quiet_timer(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        _status_full,
        "gather_timer",
        lambda: _status_timer.TimerStatus(enabled=True, next_fire="x", detail="y"),
    )


@pytest.fixture
def offline_profile(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        _snapshot_push, "refresh_profile", lambda *, now, credit_count: None
    )


def test_a_push_writes_one_text_leaf():
    store = FakeStore()

    result = push_snapshot(
        {"schema": 1, "profile": None, "generated_at": "t"}, connect=lambda: store
    )

    assert result.pushed
    assert store.writes[0][0] == SNAPSHOT_PATH == "leetcode-guard/status"
    assert json.loads(store.writes[0][1]) == {
        "schema": 1,
        "profile": None,
        "generated_at": "t",
    }
    assert str(len(store.writes[0][1])) in result.reason


@pytest.mark.parametrize(
    "error",
    [ConfigError("no config"), FirebaseSyncError("HTTP 500"), OSError("disk")],
)
def test_a_failed_push_is_a_warning_not_a_raise(
    error: Exception, caplog: pytest.LogCaptureFixture
):
    result = push_snapshot(BEAT, connect=lambda: FakeStore(error))

    assert not result.pushed
    assert "snapshot push failed" in caplog.text


def test_a_failed_connect_is_a_warning_not_a_raise(caplog: pytest.LogCaptureFixture):
    def connect():
        msg = "missing firebase.json"
        raise ConfigError(msg)

    assert not push_snapshot(BEAT, connect=connect).pushed
    assert "missing firebase.json" in caplog.text


def test_the_default_connect_is_blocked_in_tests():
    with pytest.raises(AssertionError, match="Firebase"):
        push_snapshot(BEAT)


def test_gather_reads_everything_and_writes_no_ledger(
    data_dir: Path, quiet_timer: None, offline_profile: None
):
    now = datetime(2026, 8, 10, 12, 0, tzinfo=UTC)

    snap = gather_snapshot(now=now)

    assert snap["schema"] == 1
    assert snap["status"]["day"] == "2026-08-10"
    assert snap["profile"] is None
    assert snap["progress"] is None
    assert snap["coach"]["problems"] == []
    assert snap["coach"]["how_to"]["first_command"].startswith("leetcode --cluster ")
    assert not (data_dir / "ledger.json").exists()


def test_push_quietly_pushes_the_gathered_snapshot(
    quiet_timer: None, offline_profile: None
):
    store = FakeStore()

    result = push_quietly(connect=lambda: store)

    assert result.pushed
    assert json.loads(store.writes[0][1])["schema"] == 1


def test_push_quietly_never_raises(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
):
    def explode(**_kwargs: object) -> dict[str, object]:
        message = "boom"
        raise RuntimeError(message)

    monkeypatch.setattr(_snapshot_push, "gather_snapshot", explode)

    result = push_quietly(connect=FakeStore)

    assert result == PushResult(pushed=False, reason="snapshot push raised", size=0)
    assert "snapshot push raised" in caplog.text


def test_the_cli_prints_the_outcome(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    monkeypatch.setattr(
        _snapshot_push,
        "push_quietly",
        lambda: PushResult(pushed=True, reason="pushed 9 bytes", size=9),
    )

    assert _cli.main(["--push-snapshot"]) == 0
    assert "pushed 9 bytes" in capsys.readouterr().out


def test_the_cli_exits_nonzero_on_failure(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    monkeypatch.setattr(
        _snapshot_push,
        "push_quietly",
        lambda: PushResult(pushed=False, reason="snapshot push failed: x", size=0),
    )

    assert cmd_push_snapshot() == 1
    assert "snapshot push failed: x" in capsys.readouterr().out


def test_every_harvest_run_pushes_even_when_it_does_nothing(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    """``generated_at`` is the app's heartbeat, so a no-op minute still pushes."""
    calls: list[str] = []
    monkeypatch.setattr(_harvest_run, "run_harvest", lambda **_k: "nothing new")

    def fake_push() -> PushResult:
        calls.append("push")
        return PushResult(pushed=True, reason="pushed 3 bytes", size=3)

    monkeypatch.setattr(_snapshot_push, "push_quietly", fake_push)

    assert _harvest_run.main() == 0
    out = capsys.readouterr().out
    assert calls == ["push"]
    assert "nothing new" in out
    assert "snapshot: pushed 3 bytes" in out
