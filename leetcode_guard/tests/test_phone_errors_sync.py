"""Tests for the harvester's phone-error step: fetch, mirror, notify once.

Nothing here may touch gating or credits: every failure is a warning and a
line in the harvest's journal, never an exception out of ``main``.
"""

from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING

from crdt_sync import FirebaseSyncError
import pytest

from leetcode_guard import _e2e, _harvest_run, _phone_errors_sync
from leetcode_guard._phone_errors import read_mirror
from leetcode_guard._snapshot_push import FIREBASE_APP
from leetcode_guard.tests._memory_remote import MemoryRemote
from leetcode_guard.tests.test_phone_errors import DEVICE, entry, node

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path


# Taken at import, before the suite-wide rail stubs them
# (``_snapshot_fixtures``): the tests below are about the real ones.
real_sync_quietly = _phone_errors_sync.sync_quietly
real_send_notification = _phone_errors_sync.send_notification


class Recorder:
    """Stands in for ``send_notification``."""

    def __init__(self, *, ok: bool = True) -> None:
        self.sent: list[tuple[str, str]] = []
        self.ok = ok

    def __call__(self, title: str, body: str) -> bool:
        self.sent.append((title, body))
        return self.ok


def fetched(raw: object) -> Callable[[], object]:
    """Return a fetcher that yields ``raw``."""
    return lambda: raw


def test_a_new_error_notifies_once(tmp_path: Path):
    """A first-seen error notifies once; a re-read of it does not."""
    path = tmp_path / "phone_errors.json"
    notify = Recorder()

    first = _phone_errors_sync.sync_phone_errors(
        fetched(node(entry())), notify=notify, path=path
    )
    second = _phone_errors_sync.sync_phone_errors(
        fetched(node(entry(count=9))), notify=notify, path=path
    )

    assert first == "1 kept, 1 new"
    assert second == "1 kept, 0 new"
    assert len(notify.sent) == 1
    title, body = notify.sent[0]
    assert title == _phone_errors_sync.TITLE
    assert "Offline: can't reach Firebase" in body
    errors, notified = read_mirror(path)
    assert errors[0].count == 9
    assert notified == {f"{DEVICE}|2026-10-24T11:05:00.000Z"}


def test_the_same_message_seen_afresh_is_new_again(tmp_path: Path):
    """A new first-seen stamp makes the same message notify again."""
    path = tmp_path / "phone_errors.json"
    notify = Recorder()
    _phone_errors_sync.sync_phone_errors(
        fetched(node(entry())), notify=notify, path=path
    )

    again = entry(first_seen="2026-10-25T08:00:00.000Z")
    _phone_errors_sync.sync_phone_errors(fetched(node(again)), notify=notify, path=path)

    assert len(notify.sent) == 2
    # Keys of errors the phone no longer keeps are dropped, not hoarded.
    assert read_mirror(path)[1] == {f"{DEVICE}|2026-10-25T08:00:00.000Z"}


def test_an_unwritable_mirror_notifies_nothing(tmp_path: Path):
    """Without a written mirror nothing is notified (no repeat spam)."""
    blocker = tmp_path / "file"
    blocker.write_text("", encoding="utf-8")
    notify = Recorder()

    line = _phone_errors_sync.sync_phone_errors(
        fetched(node(entry())), notify=notify, path=blocker / "x.json"
    )

    assert line == "mirror not written; not notifying"
    assert notify.sent == []


def test_an_empty_node_is_quiet(tmp_path: Path):
    """An empty phone node keeps nothing and notifies nothing."""
    notify = Recorder()
    line = _phone_errors_sync.sync_phone_errors(
        fetched(None), notify=notify, path=tmp_path / "p.json"
    )
    assert line == "0 kept, 0 new"
    assert notify.sent == []


def test_quietly_turns_any_failure_into_a_line(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
):
    """A fetch failure becomes a redacted status line, never an exception."""

    def explode() -> object:
        """Fail the fetch with a secret-bearing URL."""
        message = "https://db/x.json?auth=SECRET"
        raise FirebaseSyncError(message)

    monkeypatch.setattr(_phone_errors_sync, "fetch_phone_errors", explode)

    line = real_sync_quietly()

    assert line == "unavailable (FirebaseSyncError)"
    assert "SECRET" not in line
    assert "phone errors unavailable" in caplog.text


@pytest.mark.usefixtures("data_dir")
def test_quietly_syncs_through_the_real_parts(monkeypatch: pytest.MonkeyPatch):
    """The quiet wrapper runs the real sync and notifies the new error."""
    notify = Recorder()
    monkeypatch.setattr(
        _phone_errors_sync, "fetch_phone_errors", fetched(node(entry()))
    )
    monkeypatch.setattr(_phone_errors_sync, "send_notification", notify)

    assert real_sync_quietly() == "1 kept, 1 new"
    assert len(notify.sent) == 1


def test_the_fetch_reads_app_errors_with_the_pushers_session(
    monkeypatch: pytest.MonkeyPatch,
):
    """The fetch signs in as the pusher and reads the sealed node."""
    signed_in: list[object] = []
    remote = MemoryRemote()

    def sign_in(app: str, **_k: object) -> MemoryRemote:
        """Record the credential cache asked for."""
        signed_in.append(app)
        return remote

    monkeypatch.setattr(_phone_errors_sync, "sign_in", sign_in)

    assert _phone_errors_sync.fetch_phone_errors() == {}
    assert signed_in == [FIREBASE_APP]
    assert _phone_errors_sync.APP_ERRORS_PATH == "leetcode-guard/app_errors-e2e"


def test_a_locked_device_reads_nothing_and_says_so(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
):
    """No passphrase: an "unavailable" line, no request past the sign-in."""
    _e2e.PASSWORD_PATH.unlink()
    remote = MemoryRemote()
    monkeypatch.setattr(_phone_errors_sync, "sign_in", lambda *_a, **_k: remote)
    monkeypatch.setattr(
        _phone_errors_sync, "send_notification", lambda *_a: pytest.fail("notified")
    )

    assert real_sync_quietly() == "unavailable (E2eLockedError)"
    assert remote.writes == []
    assert "E2eLockedError" in caplog.text


def test_notify_send_success_and_failures(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
):
    """notify-send reports success, non-zero exit, timeout and absence."""
    runs: list[list[str]] = []

    def run(argv: list[str], **_k: object) -> subprocess.CompletedProcess[str]:
        """Record argv and exit 0 first, then 1."""
        runs.append(argv)
        return subprocess.CompletedProcess(argv, len(runs) - 1, "", "")

    monkeypatch.setattr(_phone_errors_sync.shutil, "which", lambda _n: "/bin/ns")
    monkeypatch.setattr(_phone_errors_sync.subprocess, "run", run)
    assert real_send_notification("t", "b")
    assert runs[0][0] == "/bin/ns"
    assert not real_send_notification("t", "b")
    assert "notify-send exited 1" in caplog.text

    def hang(*_a: object, **_k: object) -> object:
        """Simulate notify-send timing out."""
        cmd = "ns"
        raise subprocess.TimeoutExpired(cmd, 5)

    monkeypatch.setattr(_phone_errors_sync.subprocess, "run", hang)
    assert not real_send_notification("t", "b")
    monkeypatch.setattr(_phone_errors_sync.shutil, "which", lambda _n: None)
    assert not real_send_notification("t", "b")
    assert "notify-send not found" in caplog.text


def test_the_harvest_prints_the_phone_line(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    """The harvest prints the phone-errors status line."""
    monkeypatch.setattr(_phone_errors_sync, "sync_quietly", lambda: "1 kept, 0 new")
    monkeypatch.setattr(_harvest_run, "run_harvest", lambda **_k: "harvested")

    _harvest_run.main()

    assert "phone errors: 1 kept, 0 new" in capsys.readouterr().out


def test_a_broken_phone_step_never_stops_the_harvest(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
):
    """A crashing phone step is logged redacted and the harvest still exits 0."""

    def explode() -> str:
        """Crash the phone step with a secret in the message."""
        message = "boom at https://db/x.json?auth=SECRET"
        raise RuntimeError(message)

    monkeypatch.setattr(_phone_errors_sync, "sync_quietly", explode)
    monkeypatch.setattr(_harvest_run, "run_harvest", lambda **_k: "harvested")

    assert _harvest_run.main() == 0
    assert "phone errors: unavailable (RuntimeError)" in capsys.readouterr().out
    assert "phone errors unavailable" in caplog.text
    assert "SECRET" not in caplog.text
