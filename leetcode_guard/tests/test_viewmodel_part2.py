"""Continued from :mod:`test_viewmodel`: the debt on the lock surface."""

from __future__ import annotations

from datetime import timedelta

from leetcode_guard import _glyphs as g
from leetcode_guard._debt import Debt
from leetcode_guard._gate import DayContext, decide
from leetcode_guard._ledger_io import Ledger
from leetcode_guard._viewmodel import build_viewmodel
from leetcode_guard._viewmodel_source import ViewSource
from leetcode_guard.tests._ledger_fixtures import (
    MONDAY,
    NOW,
    ledger_with_credits,
)
from leetcode_guard.tests.test_viewmodel import (
    CHECKED_AT,
    OK_PROBE,
    SIGNED_OUT,
    pool_of,
)

OWING = Debt(owed=9, repaid=2, missed_days=7)


def test_the_surface_explains_a_surcharged_price(hmac_key):
    """A quota that silently doubled reads as a bug, so the balance line
    spells the surcharge out and the debt itself sits beside it."""
    decision = decide(
        Ledger(), day=MONDAY, now=NOW, key_file=hmac_key, context=DayContext(debt=OWING)
    )

    model = build_viewmodel(
        decision,
        ViewSource(pool_of(), SIGNED_OUT, limit=10),
        OK_PROBE,
        checked_at=CHECKED_AT,
    )

    assert model.headline == g.OWED * 2
    assert f"{g.TODAY} 2 (1+1{g.DEBT})" in model.balance_line
    assert model.balance_line.endswith(f"{g.DEBT} 7")


def test_no_debt_note_when_on_track(hmac_key):
    decision = decide(
        Ledger(), day=MONDAY + timedelta(days=1), now=NOW, key_file=hmac_key
    )

    model = build_viewmodel(
        decision,
        ViewSource(pool_of(), SIGNED_OUT, limit=10),
        OK_PROBE,
        checked_at=CHECKED_AT,
    )

    assert model.balance_line == f"{g.CREDIT} 0{g.SEP}{g.TODAY} 1"
    assert g.DEBT not in model.balance_line


def test_the_status_line_credits_a_solve_that_freed_a_slot(hmac_key):
    """A row that vanishes silently takes the only confirmation with it.

    The acknowledgement moves to the status line rather than holding the row,
    because the slot is the scarce thing -- that is the whole point of the
    fix. It still has to name the problem (a title is content), or a debt-day
    lock looks like it ignored the first solve.
    """
    decision = decide(
        Ledger(), day=MONDAY, now=NOW, key_file=hmac_key, context=DayContext(debt=OWING)
    )

    model = build_viewmodel(
        decision,
        ViewSource(
            pool_of("two-sum", "add-two-numbers"),
            SIGNED_OUT,
            limit=10,
            solved_slugs=frozenset({"two-sum"}),
        ),
        OK_PROBE,
        checked_at=CHECKED_AT,
    )

    assert model.status_line == f"{g.SOLVED} Two Sum{g.SEP}{g.WATCHING} 12:04:31"
    assert model.headline == g.OWED * 2
    assert [line.label for line in model.problems] == ["1  Add Two Numbers"]


def test_the_last_owed_solve_leaves_one_circle(hmac_key):
    decision = decide(Ledger(), day=MONDAY, now=NOW, key_file=hmac_key)

    model = build_viewmodel(
        decision,
        ViewSource(
            pool_of("two-sum"),
            SIGNED_OUT,
            limit=10,
            solved_slugs=frozenset({"two-sum"}),
        ),
        OK_PROBE,
        checked_at=CHECKED_AT,
    )

    assert model.status_line.startswith(f"{g.SOLVED} Two Sum{g.SEP}")
    assert model.headline == g.OWED


def test_an_unlocked_surface_credits_the_solve_without_demanding_another(hmac_key):
    """``needed`` is zero the moment the solve lands, and the lingering
    unlocked screen must not still be asking for one."""
    ledger = ledger_with_credits(1, day=MONDAY, key_file=hmac_key)
    decision = decide(ledger, day=MONDAY, now=NOW, key_file=hmac_key)

    model = build_viewmodel(
        decision,
        ViewSource(
            pool_of("two-sum"),
            SIGNED_OUT,
            limit=10,
            solved_slugs=frozenset({"two-sum"}),
        ),
        OK_PROBE,
        checked_at=CHECKED_AT,
    )

    assert not decision.locked
    assert model.status_line.startswith(f"{g.SOLVED} Two Sum{g.SEP}")
    assert g.OWED not in model.headline


def test_the_status_line_names_two_solves_and_counts_the_rest(hmac_key):
    """A week of debt means several solves per lock, and the line persists.

    Naming all of them measured 2109px wide against a 1366px panel -- on a
    place-centred surface, which shears off both edges rather than clipping
    one. Two names and a count stays inside the wrap.
    """
    decision = decide(
        Ledger(), day=MONDAY, now=NOW, key_file=hmac_key, context=DayContext(debt=OWING)
    )
    slugs = ("two-sum", "add-two-numbers", "longest-substring", "median-of-arrays")

    model = build_viewmodel(
        decision,
        ViewSource(
            pool_of(*slugs, "valid-parentheses"),
            SIGNED_OUT,
            limit=10,
            solved_slugs=frozenset(slugs),
        ),
        OK_PROBE,
        checked_at=CHECKED_AT,
    )

    assert model.status_line.startswith(
        f"{g.SOLVED} Two Sum, Add Two Numbers +2{g.SEP}"
    )
