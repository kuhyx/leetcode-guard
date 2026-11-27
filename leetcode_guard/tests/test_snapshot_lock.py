"""The snapshot's ``status.lock`` block: exactly the rows the PC lock shows.

The phone's Status tab used to list ``pool.problems[:limit]`` with no unit
filter, no easy-only, no solved-slug removal and no review row, so it showed a
different list from the lock. Both now go through ``_viewmodel.lock_rows``;
these tests hold the two side by side over one ``ViewSource``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from leetcode_guard import _snapshot_lock, _status, _viewmodel_lines
from leetcode_guard._gate import decide
from leetcode_guard._ledger_io import Ledger
from leetcode_guard._review_due import UNKNOWN
from leetcode_guard._snapshot_lock import lock_block
from leetcode_guard._status import verdict_of
from leetcode_guard._status_unit import UnitStatus
from leetcode_guard._viewmodel import build_viewmodel
from leetcode_guard._viewmodel_source import ViewSource
from leetcode_guard.tests._ledger_fixtures import (
    MONDAY,
    NOW,
)
from leetcode_guard.tests._phase_fixtures import NONE, SOLVE, THEORY
from leetcode_guard.tests._review_first_fixtures import (
    DUE,
    ROUTE,
    SOLVE_R,
    T_MS,
    write_module_due,
)
from leetcode_guard.tests.test_snapshot import a_snapshot
from leetcode_guard.tests.test_solve_easy_only import EASY, pool
from leetcode_guard.tests.test_status import seed_pool
from leetcode_guard.tests.test_viewmodel import CHECKED_AT, OK_PROBE, SIGNED_OUT

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture(autouse=True)
def _fresh_warning_latch() -> None:
    _viewmodel_lines.WARNED.clear()


LOCKED = decide(Ledger(), day=MONDAY, now=NOW)


def source(phase=NONE, *, solved=frozenset(), review=None) -> ViewSource:
    """One source for both sides: the whole pool, as the lock lists it."""
    the_pool = pool()
    return ViewSource(
        the_pool,
        SIGNED_OUT,
        limit=len(the_pool.problems),
        solved_slugs=solved,
        phase=phase,
        review=review,
    )


def lock_urls(view_source: ViewSource) -> list[str]:
    """What each of the lock's rows opens, in its order."""
    model = build_viewmodel(LOCKED, view_source, OK_PROBE, checked_at=CHECKED_AT)
    return [line.url for line in model.problems]


def snapshot_urls(block: dict) -> list[str]:
    """What each of the snapshot's rows opens, in its order."""
    return [row.get("url") or row["route"] for row in block["rows"]]


@pytest.mark.parametrize(
    ("phase", "solved"),
    [
        pytest.param(NONE, frozenset(), id="no-unit"),
        pytest.param(THEORY, frozenset(), id="unit-filter"),
        pytest.param(SOLVE, frozenset(), id="easy-only"),
        pytest.param(SOLVE, frozenset({EASY[0], EASY[5]}), id="solved-removed"),
    ],
)
def test_the_snapshot_rows_are_the_lock_rows(phase, solved: frozenset[str]):
    """Same rows, same order, for every screen."""
    view_source = source(phase, solved=solved)

    block = lock_block(verdict_of(LOCKED), view_source)

    assert snapshot_urls(block) == lock_urls(view_source)
    assert all(row["kind"] == "problem" for row in block["rows"])
    assert not {f"https://leetcode.com/problems/{s}/" for s in solved} & set(
        snapshot_urls(block)
    )


def test_a_problem_row_carries_its_title_difficulty_and_url():
    """The raw title from the pool, never the lock's numbered label."""
    first = pool().problems[0]

    row = lock_block(verdict_of(LOCKED), source(SOLVE))["rows"][0]

    assert row == {
        "kind": "problem",
        "title": first.title,
        "difficulty": "Easy",
        "url": f"https://leetcode.com/problems/{first.title_slug}/",
    }


def test_due_cards_replace_the_solve_rows_with_one_review_row():
    """Review first, as the lock paints it."""
    view_source = source(SOLVE_R, review=DUE)

    block = lock_block(verdict_of(LOCKED), view_source)

    assert block["rows"] == [{"kind": "review", "count": 3, "route": ROUTE}]
    assert snapshot_urls(block) == lock_urls(view_source)


def test_cannot_check_the_review_keeps_the_solve_rows():
    """``UNKNOWN`` is not "due": the SOLVE rows stay, on both sides."""
    view_source = source(SOLVE_R, review=UNKNOWN)

    block = lock_block(verdict_of(LOCKED), view_source)

    assert snapshot_urls(block) == lock_urls(view_source)
    assert block["rows"][0]["kind"] == "problem"


def test_theory_gives_the_learn_route_the_lock_button_opens():
    """The card's route; unit and phase as the lock's screen has them."""
    block = lock_block(verdict_of(LOCKED), source(THEORY))

    assert block["phase"] == "theory"
    assert block["unit"] == "prefix-sums"
    assert block["learn_route"] == (
        "/learn/leetcode-easy-algorithms-in-typescript/prefix-sums"
    )


@pytest.mark.parametrize("phase", [NONE, SOLVE], ids=["none", "solve"])
def test_no_theory_screen_has_no_learn_route(phase):
    """SOLVE and the plain list have no learn button."""
    block = lock_block(verdict_of(LOCKED), source(phase))

    assert block["learn_route"] is None
    assert block["phase"] == phase.phase
    assert block["unit"] == ("" if phase is NONE else "prefix-sums")


def test_the_snapshot_carries_the_lock_block_from_live_reads(
    monkeypatch: pytest.MonkeyPatch, data_dir: Path, hmac_key: Path
):
    """End to end: the unit read, the signed due file and the pool cache."""
    unit = UnitStatus(
        view=SOLVE_R, source="live", minutes=0, credits_today=0, credits_total=0
    )
    monkeypatch.setattr(_status, "gather_unit", lambda *_a, **_k: unit)
    monkeypatch.setattr(_snapshot_lock, "find_tutor", lambda: "/x/tutor")
    write_module_due(hmac_key, [T_MS - 1000])

    lock = a_snapshot(data_dir, hmac_key)["status"]["lock"]

    assert lock == {
        "unpaid": False,
        "unit": "prefix-sums",
        "phase": "solve",
        "learn_route": None,
        "rows": [{"kind": "review", "count": 1, "route": ROUTE}],
    }


def test_the_snapshot_lists_the_pool_cache_minus_the_ledger_solves(
    monkeypatch: pytest.MonkeyPatch, data_dir: Path, hmac_key: Path
):
    """No phase: the cached pool in order, without ``two-sum`` (credited)."""
    unit = UnitStatus(NONE, "unknown", None, 0, 0)
    monkeypatch.setattr(_status, "gather_unit", lambda *_a, **_k: unit)
    seed_pool(data_dir / "pool_cache.json", "two-sum", "climbing-stairs", "fizz")

    lock = a_snapshot(data_dir, hmac_key)["status"]["lock"]

    assert [row["url"] for row in lock["rows"]] == [
        "https://leetcode.com/problems/climbing-stairs/",
        "https://leetcode.com/problems/fizz/",
    ]
    assert (lock["phase"], lock["unit"], lock["unpaid"]) == ("none", "", False)
