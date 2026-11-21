"""Active time, windows and the flag of one solve (pure, display-only)."""

from __future__ import annotations

import pytest

from leetcode_guard import _attempts
from leetcode_guard._attempt_model import Beat, Submission
from leetcode_guard._ledger import SEEN, LedgerEntry
from leetcode_guard._ledger_io import Ledger
from leetcode_guard.tests._flagged_fixtures import (
    DAY_SECONDS,
    MINUTE,
    T0,
    beat_run,
    record_of,
)

SLUG = "two-sum"


def solve(history, *, at: int = T0, cleared=frozenset()) -> _attempts.Solve:
    """Measure the standard credit over ``history``."""
    return _attempts.measure(_attempts.Credit(SLUG, at), history, cleared=cleared)


def test_the_constants_are_named():
    """The thresholds are read as ``mod.CONST`` so a script can redirect them."""
    assert _attempts.FLAG_SECONDS == 20 * MINUTE
    assert _attempts.FAST_SECONDS == 10 * MINUTE
    assert _attempts.GAP_SECONDS == 5 * MINUTE
    assert _attempts.WINDOW_DAYS == 28


def test_active_time_sums_the_gaps_up_to_five_minutes():
    """A gap of exactly 300 s counts; 301 s does not."""
    assert _attempts.active_seconds([0, 60, 360], 360) == 360
    assert _attempts.active_seconds([0, 60, 361], 361) == 60


def test_the_accept_time_closes_the_last_gap():
    """Beats up to T, then T itself: the tail counts when it is short."""
    assert _attempts.active_seconds([0, 60], 120) == 120
    assert _attempts.active_seconds([0, 60], 61 + _attempts.GAP_SECONDS) == 60


def test_no_beats_is_zero_active_time():
    """Nothing to chain: the lone end point has no neighbour."""
    assert _attempts.active_seconds([], T0) == 0


def test_unsorted_beats_are_ordered_first():
    """Beats from two day-records arrive in no particular order."""
    assert _attempts.active_seconds([120, 0, 60], 120) == 120


def test_the_earliest_credit_of_a_slug_is_the_solve():
    """A repeat accept of the same slug is ignored, whatever order they came in."""
    earned = [
        _attempts.Credit("a", 500),
        _attempts.Credit("b", 100),
        _attempts.Credit("a", 300),
        _attempts.Credit("a", 900),
    ]

    firsts = {item.slug: item.accepted_at for item in _attempts.first_credits(earned)}

    assert firsts == {"a": 300, "b": 100}


def _credit_entry(entry_id: str, kind: str, detail: dict[str, str]) -> LedgerEntry:
    return LedgerEntry(entry_id, kind, "2026-08-10", "x", 1, detail=detail)


def test_credits_come_from_credit_rows_with_a_slug_and_a_numeric_time():
    """Rows missing either field, or of another kind, are skipped."""
    ledger = Ledger()
    rows = [
        _credit_entry("ac:1", "credit", {"title_slug": "a", "submitted_at": "100"}),
        _credit_entry("ac:2", "credit", {"submitted_at": "100"}),
        _credit_entry("ac:3", "credit", {"title_slug": "", "submitted_at": "100"}),
        _credit_entry("ac:4", "credit", {"title_slug": "d"}),
        _credit_entry("ac:5", "credit", {"title_slug": "e", "submitted_at": "soon"}),
        _credit_entry("ac:6", SEEN, {"title_slug": "f", "submitted_at": "100"}),
    ]
    ledger.entries = {row.entry_id: row for row in rows}

    assert _attempts.credits_of(ledger) == [_attempts.Credit("a", 100)]


def test_a_solve_without_a_heartbeat_is_unknown():
    """No beat in the window: never measured, so never flagged."""
    found = solve([record_of(SLUG, [], theory="done")])

    assert not found.measured
    assert not found.flagged
    assert found.span_seconds is None
    assert found.active_seconds == 0


def test_a_solve_with_no_record_at_all_is_unknown_with_unknown_theory():
    """Nothing on disk for the slug."""
    found = solve([])

    assert not found.measured
    assert found.theory == "unknown"


def test_beats_and_submissions_after_the_accept_are_outside_the_window():
    """Only what happened up to T belongs to the solve."""
    beats = [*beat_run(T0, 3), Beat(T0 + 60, "description")]
    later = {"9": Submission("Wrong Answer", T0 + 30)}

    found = solve([record_of(SLUG, beats, submissions=later)])

    assert found.active_seconds == 2 * MINUTE
    assert found.failed == {}


def test_a_beat_exactly_at_the_accept_time_is_inside_the_window():
    """The window is ``<= T``."""
    found = solve([record_of(SLUG, [Beat(T0, "description")])])

    assert found.measured
    assert found.active_seconds == 0


def test_an_attempt_may_span_two_days():
    """Beats from the day before count, and the span starts on T's own day."""
    yesterday = T0 - DAY_SECONDS
    history = [
        record_of(SLUG, beat_run(yesterday, 5), at=yesterday),
        record_of(SLUG, beat_run(T0, 4), at=T0, theory="done"),
    ]

    found = solve(history)

    assert found.active_seconds == (4 + 3) * MINUTE
    assert found.span_seconds == 3 * MINUTE
    assert found.accepted_at == T0
    assert found.theory == "done"


def test_the_span_is_none_when_t_s_day_has_no_beat_up_to_t():
    """Beats only on an earlier day give no same-day span."""
    yesterday = T0 - DAY_SECONDS
    found = solve([record_of(SLUG, beat_run(yesterday, 3), at=yesterday)])

    assert found.measured
    assert found.span_seconds is None


def test_time_is_attributed_to_the_tab_that_starts_each_gap():
    """Four tabs, always four keys; a long gap is attributed to nobody."""
    beats = [
        Beat(T0 - 600, "description"),
        Beat(T0 - 540, "editorial"),
        Beat(T0 - 200, "solutions"),
        Beat(T0 - 140, "submissions"),
    ]

    found = solve([record_of(SLUG, beats)])

    assert found.tab_seconds == {
        "description": 60,
        "editorial": 0,
        "solutions": 60,
        "submissions": 140,
    }
    assert found.active_seconds == 260


def test_an_unknown_tab_counts_as_active_but_has_no_bucket():
    """The store parses any tab string; only the four known ones are reported."""
    found = solve([record_of(SLUG, [Beat(T0 - 60, "weird")])])

    assert found.active_seconds == 60
    assert sum(found.tab_seconds.values()) == 0


def test_failed_submissions_are_counted_by_status_and_accepted_is_not_one():
    """Every non-Accepted status in the window, by its own string."""
    subs = {
        "1": Submission("Wrong Answer", T0 - 300),
        "2": Submission("Wrong Answer", T0 - 200),
        "3": Submission("Runtime Error", T0 - 100),
        "4": Submission("Accepted", T0),
    }

    found = solve([record_of(SLUG, beat_run(T0, 3), submissions=subs)])

    assert found.failed == {"Runtime Error": 1, "Wrong Answer": 2}


def test_time_to_the_first_submission_cuts_the_window_at_it():
    """Active time up to the earliest submission, not up to T."""
    subs = {"1": Submission("Wrong Answer", T0 - 600), "2": Submission("Accepted", T0)}

    found = solve([record_of(SLUG, beat_run(T0, 21), submissions=subs)])

    assert found.active_seconds == 20 * MINUTE
    assert found.first_submission_active_seconds == 20 * MINUTE - 600


def test_with_no_submission_the_first_submission_time_is_the_whole_solve():
    """No cut-off: ``T`` itself."""
    found = solve([record_of(SLUG, beat_run(T0, 4))])

    assert found.first_submission_active_seconds == found.active_seconds == 180


def test_theory_comes_from_the_record_of_the_accept_day():
    """A snapshot on another day's record is not the solve's."""
    yesterday = T0 - DAY_SECONDS
    history = [
        record_of(SLUG, beat_run(yesterday, 2), at=yesterday, theory="pending"),
        record_of(SLUG, beat_run(T0, 2)),
    ]

    assert solve(history).theory == "unknown"


def _long_solve(minutes: int, theory: str, *, cleared=frozenset()) -> _attempts.Solve:
    return solve(
        [record_of(SLUG, beat_run(T0, minutes + 1), theory=theory)], cleared=cleared
    )


def test_a_long_solve_of_taught_theory_is_flagged():
    """Over 20 minutes active and the unit was taught."""
    found = _long_solve(21, "done")

    assert found.active_seconds == 21 * MINUTE
    assert found.flagged


@pytest.mark.parametrize(
    ("minutes", "theory", "cleared"),
    [
        (20, "done", frozenset()),
        (21, "pending", frozenset()),
        (21, "none", frozenset()),
        (21, "unknown", frozenset()),
        (21, "done", frozenset({SLUG})),
    ],
)
def test_the_flag_needs_all_three_conditions(minutes, theory, cleared):
    """Exactly 20 minutes, untaught theory, or a cleared slug: not flagged."""
    assert not _long_solve(minutes, theory, cleared=cleared).flagged
