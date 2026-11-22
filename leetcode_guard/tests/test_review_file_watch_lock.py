"""The review file watch, wired into the lock's own watch loop."""

from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace
from typing import TYPE_CHECKING

import pytest

from leetcode_guard.tests._phase_fixtures import SOLVE
from leetcode_guard.tests._review_first_fixtures import (
    install_tutor,
    review_guard,
    write_module_due,
)

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path


@pytest.fixture(autouse=True)
def _tutor(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    return install_tutor(monkeypatch)


def _no_stat(why: str) -> SimpleNamespace:
    """An ``os`` for the watch module alone (patching the real one hits other threads)."""

    def stat(*_args: object) -> None:
        pytest.fail(f"os.stat called: {why}")

    return SimpleNamespace(stat=stat)


def _watch_step(guard) -> Callable[[], None]:
    """The poller's own watch callback, as the Tk loop would run it."""
    jobs = [c.args[1] for c in guard.root.after.call_args_list if len(c.args) > 1]
    return next(job for job in jobs if getattr(job, "__name__", "") == "_watch")


def test_a_rewritten_file_brings_the_lock_poll_forward(
    tmp_path: Path, hmac_key: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The lock's real wiring: the rewrite makes the poller check, once."""
    write_module_due(hmac_key, [1])
    guard = review_guard(tmp_path, hmac_key)
    clock = [5000.0]
    monkeypatch.setattr(
        "leetcode_guard._review_file_watch.time.monotonic", lambda: clock[0]
    )
    asked: list[int] = []
    monkeypatch.setattr(guard.poller, "check_now", lambda: asked.append(1))
    step = _watch_step(guard)
    step()
    write_module_due(hmac_key, [1, 2])
    clock[0] += 1.0

    step()

    assert asked == [1]


def test_the_demo_never_looks_at_the_file(
    tmp_path: Path, hmac_key: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Demo mode: no ``stat`` at all."""
    guard = review_guard(tmp_path, hmac_key, demo_mode=True)

    assert guard.run_state.phases.file_watch() is False
    with monkeypatch.context() as scoped:
        scoped.setattr("leetcode_guard._review_file_watch.os", _no_stat("demo"))
        assert guard.run_state.phases.file_watch() is False


def test_no_review_targets_means_no_stat(
    tmp_path: Path, hmac_key: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A SOLVE view with no mapped module has nothing to review."""
    guard = review_guard(tmp_path, hmac_key)
    guard.run_state.phases.view = replace(SOLVE, review_targets=())
    with monkeypatch.context() as scoped:
        scoped.setattr("leetcode_guard._review_file_watch.os", _no_stat("no targets"))
        assert guard.run_state.phases.file_watch() is False
