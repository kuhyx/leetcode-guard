"""The harvester's display-only ``attempts:`` line.

Two jobs per run, neither of which may touch the ledger or the exit code:
fix the theory state at the moment of a solve, and (only while a problem tab is
being watched) record every recent submission, failures included.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from leetcode_guard import _attempt_line, _harvest_run
from leetcode_guard._attempt_queries import RecentSubmission
from leetcode_guard._attempt_store import add_beat, load
from leetcode_guard._auth import AuthState
from leetcode_guard._constants import EXIT_OK
from leetcode_guard._ledger_io import load_ledger
from leetcode_guard._settings import Client
from leetcode_guard.tests._attempt_helpers import DAY, SECONDS_PER_DAY, T0
from leetcode_guard.tests._attempt_line_helpers import (
    BITS_TAUGHT,
    Fetcher,
    credit,
    line,
    put_ledger,
    put_pool,
)
from leetcode_guard.tests._recent_submissions_fixtures import (
    recent_submission_row,
    recent_submissions_result,
)
from leetcode_guard.tests.test_theory import tutor_dir
from leetcode_guard.tests.test_theory_surface import use

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

    from leetcode_guard._leetcode import GraphQLResult


def test_a_run_with_nothing_to_do_is_idle_and_never_touches_the_network(
    hmac_key: Path,
):
    """No beat, no solve: no call, nothing written."""
    fetcher = Fetcher([])

    assert line(hmac_key, fetcher=fetcher) == "idle"
    assert fetcher.calls == 0
    assert load() == {}


def test_a_stale_beat_makes_no_network_call(hmac_key: Path):
    """Exactly 120 s old is stale: the window is under 120 s."""
    add_beat("two-sum", "description", now=T0)
    fetcher = Fetcher([])

    assert line(hmac_key, at=T0 + 120, fetcher=fetcher) == "idle"
    assert fetcher.calls == 0


def test_a_fresh_beat_fetches_once_and_merges_every_status(hmac_key: Path):
    """Failures are the point: all statuses land, in the day of their timestamp."""
    add_beat("two-sum", "description", now=T0)
    fetcher = Fetcher(
        [
            RecentSubmission("1", "two-sum", "Wrong Answer", T0 - 50),
            RecentSubmission("2", "two-sum", "Accepted", T0 - 10),
            RecentSubmission("3", "add-two-numbers", "Runtime Error", T0 - 5),
        ]
    )

    assert line(hmac_key, at=T0 + 119, fetcher=fetcher) == "3 submissions"
    assert fetcher.calls == 1
    two_sum = load()[f"{DAY}|two-sum"]
    assert {i: s.status for i, s in two_sum.submissions.items()} == {
        "1": "Wrong Answer",
        "2": "Accepted",
    }
    assert f"{DAY}|add-two-numbers" in load()

    assert line(hmac_key, at=T0 + 119, fetcher=fetcher) == "0 submissions"


def test_the_default_fetch_uses_the_harvesters_client_and_username(
    monkeypatch: pytest.MonkeyPatch, hmac_key: Path
):
    """No injected fetch: the real one asks LeetCode as the configured user."""
    asked: list[object] = []

    def post(_query: str, variables: dict[str, object]) -> GraphQLResult:
        asked.append(variables)
        return recent_submissions_result(
            [recent_submission_row("1", "two-sum", timestamp=T0)]
        )

    monkeypatch.setattr(
        _attempt_line,
        "build_client",
        lambda: Client(post=post, auth=AuthState(cookies=None, note=""), username="k"),
    )
    add_beat("two-sum", "description", now=T0)

    out = _attempt_line.attempts_line(clock=lambda: T0 + 1, key_file=hmac_key)

    assert out == "1 submission"
    assert asked == [{"username": "k", "limit": 20}]


def test_the_newest_beat_of_any_record_decides(hmac_key: Path):
    """The whole file counts, not one problem: an old record does not hide a new one."""
    add_beat("two-sum", "description", now=T0 - 3 * SECONDS_PER_DAY)
    add_beat("valid-parentheses", "editorial", now=T0)
    fetcher = Fetcher([])

    assert line(hmac_key, at=T0 + 30, fetcher=fetcher) == "0 submissions"
    assert fetcher.calls == 1


def test_could_not_check_merges_nothing_and_says_so(
    hmac_key: Path, caplog: pytest.LogCaptureFixture
):
    """Silence from LeetCode is not an empty list."""
    add_beat("two-sum", "description", now=T0)
    fetcher = Fetcher(None)

    with caplog.at_level(logging.WARNING):
        assert line(hmac_key, at=T0 + 1, fetcher=fetcher) == "could not check"

    assert fetcher.calls == 1
    assert not load()[f"{DAY}|two-sum"].submissions
    assert "recent submissions" in caplog.text


def test_the_two_jobs_report_together_and_the_ledger_is_untouched(
    hmac_key: Path, data_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """A watched tab and a fresh solve in one run; the ledger file is byte-identical."""
    use(tmp_path, monkeypatch, tutor_dir(tmp_path / "t", *BITS_TAUGHT))
    put_pool(data_dir)
    put_ledger(data_dir, credit("5", "bit-trick", T0 - 60, hmac_key))
    before = (data_dir / "ledger.json").read_bytes()
    add_beat("bit-trick", "description", now=T0)
    fetcher = Fetcher(
        [
            RecentSubmission("4", "bit-trick", "Wrong Answer", T0 - 100),
            RecentSubmission("5", "bit-trick", "Accepted", T0 - 60),
        ]
    )

    assert line(hmac_key, at=T0 + 5, fetcher=fetcher) == "2 submissions, 1 snapshot"

    assert (data_dir / "ledger.json").read_bytes() == before
    assert load_ledger(data_dir / "ledger.json", key_file=hmac_key).has("ac:5")


def test_main_prints_the_line_and_still_exits_ok(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    hmac_key: Path,
):
    """Whatever the line does, the harvester's code and its other lines hold."""
    monkeypatch.setattr(_harvest_run, "run_harvest", lambda **_: "harvest ok")

    assert _harvest_run.main(key_file=hmac_key) == EXIT_OK

    out = capsys.readouterr().out.splitlines()
    assert out[0] == "harvest ok"
    assert "attempts: idle" in out


def test_main_survives_a_line_that_raises(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
    hmac_key: Path,
):
    """A bug in the display-only line costs the line, never the exit code."""

    def explode(**_: object) -> str:
        message = "boom"
        raise RuntimeError(message)

    monkeypatch.setattr(_harvest_run, "run_harvest", lambda **_: "harvest ok")
    monkeypatch.setattr(_attempt_line, "attempts_line", explode)

    with caplog.at_level(logging.WARNING):
        assert _harvest_run.main(key_file=hmac_key) == EXIT_OK

    assert "attempts: unavailable (RuntimeError)" in capsys.readouterr().out
    assert "attempts line unavailable" in caplog.text
