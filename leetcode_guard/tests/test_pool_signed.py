"""The phase reads only an authenticated, complete pool; anything else fails closed.

The pool cache is unsigned data on disk. Before it was signed, a half-fetched
pool or a hand-edited one could push the unit machine out of SOLVE(a) and mint
theory credits for the next unit. Both are "cannot check" now: the caller holds
the last signed phase and mints nothing. The suggestion list still reads an
unverified cache, because it prices nothing.
"""

from __future__ import annotations

from datetime import datetime
import json
import logging
from typing import TYPE_CHECKING

from leetcode_guard import _constants, _phase_file
from leetcode_guard._auth import AuthState
from leetcode_guard._ledger_entries import credit_entry
from leetcode_guard._ledger_io import Ledger, append
from leetcode_guard._phase_inputs import gather_phase
from leetcode_guard._pool_cache import (
    CachedPool,
    write_cache,
)
from leetcode_guard._pool_resolve import (
    SolvedKnowledge,
    resolve_pool,
)
from leetcode_guard._theory_credit import poll_theory
from leetcode_guard.tests._ledger_fixtures import submission
from leetcode_guard.tests._theory_scenario import states, taught, world
from leetcode_guard.tests.test_problem import make

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    import pytest

    from leetcode_guard._theory_credit import TheoryPoll

NOW = datetime(2026, 11, 24, 12, 0).astimezone()
DAY = NOW.date()
SIGNED_OUT = AuthState(cookies=None, note="signed out")


def cache_path() -> Path:
    """The scratch pool cache, read at call time (``_isolate_paths`` rebinds it)."""
    return _constants.POOL_CACHE_FILE


def poll(ledger: Ledger, data_dir: Path, key: Path) -> TheoryPoll:
    """One theory poll against the scratch ledger file."""
    return poll_theory(ledger, data_dir / "ledger.json", day=DAY, now=NOW, key_file=key)


def edit_cache(mutate: Callable[[dict[str, object]], None]) -> None:
    """Hand-edit ``pool_cache.json`` the way someone with a text editor would."""
    raw = json.loads(cache_path().read_text(encoding="utf-8"))
    mutate(raw)
    cache_path().write_text(json.dumps(raw), encoding="utf-8")


def drop_signature(raw: dict[str, object]) -> None:
    """Make the cache look like every one written before signing."""
    raw.pop("hmac", None)


def mark_paid(raw: dict[str, object]) -> None:
    """Make every problem premium, so unit ``a`` has no Easy problem left."""
    rows = raw["problems"]
    assert isinstance(rows, list)
    for row in rows:
        row["paidOnly"] = True


def solve_a_then_teach_b(hmac_key: Path) -> None:
    """Unit ``a`` taught with ``a1`` unsolved: SOLVE(a); ``b1`` taught 36 minutes."""
    states(hmac_key, "a")
    taught(hmac_key, NOW, ("b1", 36))


def test_a_signed_complete_pool_decides_as_before(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, data_dir: Path, hmac_key: Path
):
    """SOLVE(a) holds while a1 is unsolved; its credit moves on to THEORY(b)."""
    world(tmp_path, monkeypatch)
    solve_a_then_teach_b(hmac_key)
    ledger = Ledger()

    held = poll(ledger, data_dir, hmac_key)
    append(
        ledger,
        [credit_entry(submission("1", "a1"), day=DAY, now=NOW, key_file=hmac_key)],
    )
    moved = poll(ledger, data_dir, hmac_key)

    assert held.state is not None
    assert (held.state.unit, held.state.phase, held.minted) == ("a", "solve", ())
    assert moved.state is not None
    assert (moved.state.unit, moved.state.phase, len(moved.minted)) == (
        "b",
        "theory",
        3,
    )


def test_an_incomplete_pool_cannot_move_the_phase(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, data_dir: Path, hmac_key: Path
):
    """A fetch that stopped half way lacks a1: that is not "a is solved"."""
    world(tmp_path, monkeypatch)
    solve_a_then_teach_b(hmac_key)
    poll(Ledger(), data_dir, hmac_key)
    before = _phase_file.PHASE_FILE.read_bytes()
    partial = CachedPool(
        (make("b1-easy", topics=["y"]),), fetched_at=0.0, complete=False
    )
    write_cache(cache_path(), partial)

    result = poll(Ledger(), data_dir, hmac_key)

    assert (result.state, result.minted) == (None, ())
    assert _phase_file.PHASE_FILE.read_bytes() == before


def test_an_edited_pool_cache_cannot_move_the_phase(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, data_dir: Path, hmac_key: Path
):
    """Marking a1 premium in the JSON must not skip the solve step."""
    world(tmp_path, monkeypatch)
    solve_a_then_teach_b(hmac_key)
    poll(Ledger(), data_dir, hmac_key)
    before = _phase_file.PHASE_FILE.read_bytes()
    edit_cache(mark_paid)

    result = poll(Ledger(), data_dir, hmac_key)

    assert (result.state, result.minted) == (None, ())
    assert _phase_file.PHASE_FILE.read_bytes() == before


def test_an_unsigned_pool_cache_cannot_move_the_phase(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    hmac_key: Path,
    caplog: pytest.LogCaptureFixture,
):
    """A cache with no signature (every cache written before signing) is unchecked."""
    world(tmp_path, monkeypatch)
    solve_a_then_teach_b(hmac_key)
    edit_cache(drop_signature)

    with caplog.at_level(logging.WARNING):
        assert gather_phase(Ledger(), key_file=hmac_key) is None

    assert "not signed" in caplog.text


def test_an_incomplete_pool_is_logged_as_cannot_check(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    hmac_key: Path,
    caplog: pytest.LogCaptureFixture,
):
    """The reason is on record, so a held phase is explainable."""
    world(tmp_path, monkeypatch)
    solve_a_then_teach_b(hmac_key)
    write_cache(
        cache_path(), CachedPool((make("a1", topics=["x"]),), 0.0, complete=False)
    )

    with caplog.at_level(logging.WARNING):
        assert gather_phase(Ledger(), key_file=hmac_key) is None

    assert "incomplete" in caplog.text


def test_the_suggestion_list_still_reads_an_unverified_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, hmac_key: Path
):
    """Display prices nothing: an unsigned or edited cache still fills the list."""
    world(tmp_path, monkeypatch)
    solved = SolvedKnowledge(auth=SIGNED_OUT, key_file=hmac_key)
    edit_cache(drop_signature)

    unsigned = resolve_pool(None, cache_path(), now=1.0, solved=solved)
    edit_cache(mark_paid)
    edited = resolve_pool(None, cache_path(), now=1.0, solved=solved)

    assert unsigned.source == edited.source == "cache"
    assert {p.title_slug for p in unsigned.problems} == {"a1", "b1-easy"}
