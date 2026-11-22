"""A scratch theory-first world: curriculum, pool, signed tutor files.

Two units: ``a`` (module ``a`` of the algorithm subject, Easy ``a1``) and
``b`` (modules ``b1``/``b2``, Easy ``b1-easy``). Everything lands in the
suite's scratch dirs (``_paths_fixture``), never in ``~/.local/share``.
"""

from __future__ import annotations

from datetime import datetime, timedelta
import json
from typing import TYPE_CHECKING

from leetcode_guard import _constants, _curriculum
from leetcode_guard._phase import PhaseState
from leetcode_guard._phase_file import write_phase
from leetcode_guard._pool_cache import CachedPool, write_cache
from leetcode_guard.tests._tutor_fixtures import (
    ALGO,
    state_row,
    teaching_row,
    write_tutor,
)
from leetcode_guard.tests.test_phase import DOCUMENT as PHASE_DOCUMENT
from leetcode_guard.tests.test_problem import make

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

# The phase tests' two mapped units, without their unmapped third.
DOCUMENT = {"units": PHASE_DOCUMENT["units"][:2]}


def world(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The curriculum and the pool; no tutor files yet."""
    path = tmp_path / "curriculum.json"
    path.write_text(json.dumps(DOCUMENT), encoding="utf-8")
    monkeypatch.setattr(_curriculum, "CURRICULUM_FILE", path)
    pool = (make("a1", topics=["x"]), make("b1-easy", topics=["y"]))
    write_cache(
        _constants.POOL_CACHE_FILE,
        CachedPool(problems=pool, fetched_at=0.0, complete=True),
    )


def states(key_file: Path, *done: str, at: float = 1.0) -> None:
    """C2 with every named module done (and nothing else)."""
    rows: list[object] = [
        state_row(m, done=True, at=at, key_file=key_file) for m in done
    ]
    write_tutor("module_state.json", rows)


def taught(key_file: Path, now: datetime, *spans: tuple[str | None, int]) -> None:
    """C1: one teaching row per (module, minutes), ending a minute apart before ``now``."""
    rows: list[object] = [
        teaching_row(
            f"s{i}-m{minutes}",
            minutes,
            ended=now - timedelta(minutes=len(spans) - i),
            key_file=key_file,
            where=(ALGO, module),
        )
        for i, (module, minutes) in enumerate(spans)
    ]
    write_tutor("ledger.json", rows)


# Long before any row a test teaches: C3's ``theory_since`` for ``began``.
EARLY = datetime(2026, 1, 1).astimezone()
_MODULES = {"a": ("a",), "b": ("b1", "b2")}


def began(key_file: Path, unit: str = "a", phase: str = "theory") -> None:
    """A signed C3 saying ``unit`` entered ``phase`` at ``EARLY``.

    Minutes that ended before THEORY(u) began never pay (``theory_since``),
    so a test that teaches first and polls after states when the phase began.
    """
    state = PhaseState(
        unit=unit,
        phase="solve" if phase == "solve" else "theory",
        subject=ALGO,
        modules=_MODULES[unit],
    )
    write_phase(state, day=EARLY.date(), now=EARLY, key_file=key_file)
