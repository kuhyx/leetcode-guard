"""Continued from :mod:`leetcode_guard.tests.test_lock_study`, split for the 250-line cap."""

from __future__ import annotations

from dataclasses import replace
import logging
from types import SimpleNamespace
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest

from leetcode_guard._daycost import local_today
from leetcode_guard._gatelock_internals import arming, set_arming, vt_disabled
from leetcode_guard._ledger_entries import credit_entry
from leetcode_guard._ledger_io import append
from leetcode_guard.tests._guard_factories import (
    UNVERIFIABLE,
    guard_with_fresh_solves,
)
from leetcode_guard.tests._ledger_fixtures import submission
from leetcode_guard.tests.test_lock_study import (
    URL,
    locked_guard,
)

if TYPE_CHECKING:
    from pathlib import Path

    from leetcode_guard._gate import GateDecision


@pytest.mark.usefixtures("no_spawn")
def test_a_real_solve_while_studying_puts_the_lock_back_first(
    tmp_path: Path, hmac_key: Path
):
    """The primary exit. The unlocked screen has to land on a surface that is
    actually mapped, or the good news flashes onto a hidden window."""
    guard = guard_with_fresh_solves(tmp_path, hmac_key, demo_mode=False)
    # Both are read-only handles onto the frozen arming bundle, so the bundle
    # is swapped for one carrying mocks.
    set_arming(
        guard.lock,
        replace(arming(guard.lock), recovery=MagicMock(), detector=MagicMock()),
    )
    guard.open_problem(URL)
    strip = guard.strip
    assert guard.session().active

    guard.on_poll_result(guard.check())

    assert not guard.session().active
    strip.window.destroy.assert_called_once()
    guard.lock.root.grab_set_global.assert_called()
    assert not guard.decision().locked


@pytest.mark.usefixtures("no_spawn")
def test_closing_during_study_restores_vt_bookkeeping(tmp_path: Path, hmac_key: Path):
    """Suspend cleared gatelock's ``_vt_disabled`` to match reality. Leaving in
    study mode re-locks nothing (a restart resumes it), so VT switching must
    stay restored and the flag must still say so: the machine never exits with
    VT switching disabled."""
    guard = locked_guard(tmp_path, hmac_key, demo_mode=False)
    guard.open_problem(URL)
    assert vt_disabled(guard.lock) is False

    guard.on_close()

    assert vt_disabled(guard.lock) is False
    assert guard.session().active  # nothing re-locked on the way out


@pytest.mark.usefixtures("no_spawn")
def test_an_unverifiable_poll_during_study_leaves_it_running(
    tmp_path: Path, hmac_key: Path
):
    """A blind check is not a reason to yank the browser away mid-problem."""
    guard = locked_guard(tmp_path, hmac_key, poll_probe=UNVERIFIABLE)
    guard.open_problem(URL)

    guard.on_poll_result(UNVERIFIABLE)

    assert guard.session().active


@pytest.mark.usefixtures("no_spawn")
def test_the_strip_text_reports_what_is_owed_and_earned(tmp_path: Path, hmac_key: Path):
    """The study strip carries the problems still owed and the credits earned
    today -- and no time."""
    guard = locked_guard(tmp_path, hmac_key)

    text = guard.strip_text()

    assert text.needed >= 1
    assert text.hollow == text.needed
    assert text.earned == 0
    assert not hasattr(text, "elapsed_seconds")


@pytest.mark.usefixtures("no_spawn")
def test_the_strip_fills_a_dot_for_each_credit_earned_today(
    tmp_path: Path, hmac_key: Path
):
    """A credit recorded today for any reason is one filled dot, after a refresh."""
    guard = locked_guard(tmp_path, hmac_key)
    now = guard.deps.moment()
    append(
        guard.ledger,
        [
            credit_entry(
                submission("won"),
                day=local_today(now=now),
                now=now,
                key_file=hmac_key,
            )
        ],
    )
    guard.refresh_strip()

    assert guard.strip_text().earned == 1


@pytest.mark.usefixtures("no_spawn")
def test_the_strip_falls_back_to_the_first_output_when_none_is_primary(
    tmp_path: Path, hmac_key: Path
):
    """A desk with no output flagged primary still gets a strip somewhere
    visible rather than none at all."""
    guard = locked_guard(tmp_path, hmac_key)
    only = guard.lock.surfaces.infos()[0]
    plain = SimpleNamespace(
        output_name=only.output_name, rect=only.rect, index=0, is_primary=False
    )
    only_plain = MagicMock()
    only_plain.infos.return_value = (plain,)
    set_arming(guard.lock, replace(arming(guard.lock), surfaces=only_plain))

    assert guard.primary_rect() is plain.rect


def test_dropping_a_strip_that_was_never_built_is_harmless(
    tmp_path: Path, hmac_key: Path
):
    """Dropping a strip before any was built leaves no strip and raises nothing."""
    guard = locked_guard(tmp_path, hmac_key)

    guard.drop_strip()

    assert guard.strip is None


def test_a_launcher_that_raises_never_strands_the_machine_unlocked(
    tmp_path: Path, hmac_key: Path, monkeypatch, caplog
):
    """The grab is already released by the time the browser is spawned, so
    anything escaping there skips the rollback and walks away from an open
    machine. `launch` promises not to raise; this asserts the caller does not
    depend on that promise being kept."""
    monkeypatch.setattr(
        "leetcode_guard._lock_study.find_opener", lambda: "/usr/bin/xdg-open"
    )

    def exploding_launch(_url):
        message = "embedded null byte"
        raise ValueError(message)

    monkeypatch.setattr("leetcode_guard._lock_study.launch", exploding_launch)
    guard = locked_guard(tmp_path, hmac_key, demo_mode=False)

    with caplog.at_level(logging.ERROR):
        guard.open_problem(URL)

    assert not guard.session().active, "study mode must not stay active"
    guard.lock.root.grab_set_global.assert_called()
    assert caplog.records


@pytest.mark.usefixtures("no_spawn")
def test_the_strip_tick_does_not_redecide_every_second(
    tmp_path: Path, hmac_key: Path, monkeypatch: pytest.MonkeyPatch
):
    """decide_today runs once per refresh, not on every 1 s strip tick."""
    guard = locked_guard(tmp_path, hmac_key, poll_probe=UNVERIFIABLE)
    real = guard.decision
    calls: list[int] = []

    def counting() -> GateDecision:
        calls.append(1)
        return real()

    monkeypatch.setattr(guard, "decision", counting)
    earned_reads: list[int] = []

    def counting_earned(*_args: object, **_kwargs: object) -> tuple[int, int]:
        earned_reads.append(1)
        return 1, 0

    monkeypatch.setattr("leetcode_guard._lock_study.strip_counts", counting_earned)
    first = guard.strip_text()
    guard.strip_text()
    guard.strip_text()
    assert len(calls) == 1
    assert len(earned_reads) == 1
    guard.refresh_strip()
    again = guard.strip_text()
    assert len(calls) == 2
    assert len(earned_reads) == 2
    assert again.needed == first.needed
