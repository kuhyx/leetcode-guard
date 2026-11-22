"""The current unit's unsolved Easy problems lead the list in THEORY and SOLVE.

In "none" (and whenever the phase cannot be known) the order is exactly the
one before stage 4: ``rank_pool`` with the curriculum's block key.
"""

from __future__ import annotations

from datetime import datetime
import logging
from typing import TYPE_CHECKING

from leetcode_guard import _unit_rank
from leetcode_guard._curriculum import load_curriculum
from leetcode_guard._phase import PhaseState
from leetcode_guard._phase_file import write_phase
from leetcode_guard._pool_cache import CachedPool, write_cache
from leetcode_guard._pool_resolve import SolvedKnowledge, resolve_pool
from leetcode_guard._problem import rank_pool
from leetcode_guard._theory import load_blocks
from leetcode_guard.tests._theory_scenario import states, world
from leetcode_guard.tests._tutor_fixtures import ALGO
from leetcode_guard.tests.test_pool_resolve import SIGNED_OUT, path_of
from leetcode_guard.tests.test_problem import make

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

NOW = datetime(2026, 11, 24, 12, 0).astimezone()
POOL = (
    make("free-easy", topics=["q"], ac_rate=90.0),  # no unit: today it leads
    make("b1-easy", topics=["y"], ac_rate=95.0),
    make("a-hard", topics=["x"], difficulty="Hard"),
    make("a1", topics=["x"], ac_rate=10.0),
    make("a2", topics=["x"], ac_rate=20.0),
    make("a-medium", topics=["x"], difficulty="Medium", ac_rate=99.0),
)
TODAY = ["free-easy", "a2", "a1", "b1-easy", "a-medium", "a-hard"]
"""Before stage 4: Easy first, taught blocks before waiting ones, acceptance."""


def order(tmp_path: Path, key: Path, *solved: str) -> list[str]:
    """Resolve :data:`POOL` cache-only, verifying against ``key``."""
    write_cache(
        path_of(tmp_path), CachedPool(problems=POOL, fetched_at=0.0, complete=True)
    )
    resolution = resolve_pool(
        None,
        path_of(tmp_path),
        now=0.0,
        solved=SolvedKnowledge(auth=SIGNED_OUT, slugs=frozenset(solved), key_file=key),
        ttl=1_000.0,
    )
    return [p.title_slug for p in resolution.problems]


def held(key: Path, state: PhaseState) -> None:
    """The last signed phase (C3)."""
    write_phase(state, day=NOW.date(), now=NOW, key_file=key)


def test_the_scenario_reproduces_todays_order(tmp_path, monkeypatch):
    """The baseline itself: ``rank_pool`` with the block key, nothing else."""
    world(tmp_path, monkeypatch)
    blocks = load_blocks()
    assert blocks is not None

    ranked = rank_pool(POOL, block=blocks.key)

    assert [p.title_slug for p in ranked] == TODAY


def test_theory_puts_the_units_easy_problems_first(
    tmp_path, monkeypatch, hmac_key: Path
):
    """THEORY(a): a's Easy problems lead; a's Medium/Hard keep their places."""
    world(tmp_path, monkeypatch)
    states(hmac_key)

    assert order(tmp_path, hmac_key) == [
        "a2",
        "a1",
        "free-easy",
        "b1-easy",
        "a-medium",
        "a-hard",
    ]


def test_solve_puts_the_units_unsolved_easy_problems_first(
    tmp_path, monkeypatch, hmac_key: Path
):
    """SOLVE(b): the solved a-problems are gone, b's Easy leads."""
    world(tmp_path, monkeypatch)
    states(hmac_key, "a", "b1", "b2")
    shown = order(tmp_path, hmac_key, "a1", "a2")

    assert shown[0] == "b1-easy"
    assert shown == ["b1-easy", "free-easy", "a-medium", "a-hard"]


def test_none_is_exactly_todays_order(tmp_path, monkeypatch, hmac_key: Path):
    """Every unit finished: the stage-4 key changes nothing."""
    world(tmp_path, monkeypatch)
    states(hmac_key, "a", "b1", "b2")
    solved = ("a1", "a2", "b1-easy")
    blocks = load_blocks()
    assert blocks is not None

    expected = rank_pool(POOL, solved_slugs=frozenset(solved), block=blocks.key)

    assert order(tmp_path, hmac_key, *solved) == [p.title_slug for p in expected]


def test_cannot_check_ranks_by_the_last_signed_phase(
    tmp_path, monkeypatch, hmac_key: Path
):
    """No C2 file: C3 says THEORY(a), so a still leads (header and rows agree)."""
    world(tmp_path, monkeypatch)
    held(hmac_key, PhaseState(unit="a", phase="theory", subject=ALGO, modules=("a",)))

    assert order(tmp_path, hmac_key)[:2] == ["a2", "a1"]


def test_no_signed_phase_at_all_is_todays_order(tmp_path, monkeypatch, hmac_key: Path):
    """No C2 and no C3: nothing to lead with."""
    world(tmp_path, monkeypatch)

    assert order(tmp_path, hmac_key) == TODAY


def test_a_held_unit_the_curriculum_no_longer_has_is_todays_order(
    tmp_path, monkeypatch, hmac_key: Path
):
    """A stale C3 naming a removed unit leads with nothing."""
    world(tmp_path, monkeypatch)
    held(hmac_key, PhaseState(unit="gone", phase="solve"))

    assert order(tmp_path, hmac_key) == TODAY


def test_no_curriculum_is_the_plain_order(hmac_key: Path, tmp_path: Path):
    """No curriculum file: no blocks, no focus, the acceptance order."""
    assert load_curriculum() is None

    assert order(tmp_path, hmac_key) == [
        "b1-easy",
        "free-easy",
        "a2",
        "a1",
        "a-medium",
        "a-hard",
    ]


def test_a_bug_in_the_focus_costs_the_ordering_never_the_list(
    tmp_path, monkeypatch: pytest.MonkeyPatch, caplog, hmac_key: Path
):
    """The fence around the display-side ordering catches it, logged."""
    world(tmp_path, monkeypatch)

    def boom(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError

    monkeypatch.setattr(_unit_rank, "phase_of", boom)
    with caplog.at_level(logging.WARNING):
        shown = order(tmp_path, hmac_key)

    assert sorted(shown) == sorted(TODAY)
    assert any(r.exc_info for r in caplog.records)
