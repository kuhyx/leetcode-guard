"""The lock's unit view (SPEC C5): what each phase shows, and that it never raises.

The scenario is ``_theory_scenario``'s: unit ``a`` (module ``a``, Easy ``a1``)
then unit ``b`` (modules ``b1``/``b2``, Easy ``b1-easy``).
"""

from __future__ import annotations

from datetime import datetime
import json
import logging
from typing import TYPE_CHECKING

from leetcode_guard import _theory, _theory_credit, _unit_view
from leetcode_guard._ledger_entries import credit_entry
from leetcode_guard._ledger_io import Ledger, append, save_ledger
from leetcode_guard._phase import PhaseState
from leetcode_guard._phase_file import write_phase
from leetcode_guard._phase_view import PhaseView
from leetcode_guard._unit_view import unit_view
from leetcode_guard.tests._ledger_fixtures import submission
from leetcode_guard.tests._theory_scenario import began, states, taught, world
from leetcode_guard.tests._tutor_fixtures import ALGO

if TYPE_CHECKING:
    from pathlib import Path


NOW = datetime(2026, 11, 24, 12, 0).astimezone()
DAY = NOW.date()
CARDS = {
    "a-1": {"module": "a", "suspended": False},
    "a-2": {"module": "a", "suspended": False},
    "b1-1": {"module": "b1", "suspended": False},
}


def view(data_dir: Path, key: Path) -> PhaseView:
    """One repaint's view, today being :data:`DAY`."""
    return unit_view(data_dir / "ledger.json", key_file=key, today=lambda: DAY)()


def solved(data_dir: Path, key: Path, *slugs: str) -> None:
    """A guard ledger holding a trusted credit for each slug."""
    ledger = Ledger()
    entries = [
        credit_entry(submission(str(i), slug), day=DAY, now=NOW, key_file=key)
        for i, slug in enumerate(slugs)
    ]
    append(ledger, entries)
    save_ledger(data_dir / "ledger.json", ledger)


def display_files(*taught_cards: str, cards: object = None) -> None:
    """The tutor's UNSIGNED ``cards.json`` and ``log.jsonl`` for the subject."""
    root = _theory.TUTOR_DATA_DIR
    (root / "subjects" / ALGO).mkdir(parents=True, exist_ok=True)
    document = CARDS if cards is None else cards
    (root / "subjects" / ALGO / "cards.json").write_text(
        json.dumps(document), encoding="utf-8"
    )
    lines = "".join(
        json.dumps({"k": "taught", "s": ALGO, "c": card}) + "\n"
        for card in taught_cards
    )
    (root / "log.jsonl").write_text(lines, encoding="utf-8")


def test_theory_leads_with_the_unit_its_cards_and_todays_minutes(
    tmp_path, monkeypatch, data_dir: Path, hmac_key: Path
):
    """THEORY(a): learn a's module; 1 of 2 cards taught; 30 minutes today."""
    world(tmp_path, monkeypatch)
    states(hmac_key)
    began(hmac_key)
    taught(hmac_key, NOW, ("a", 10), ("a", 20), ("b1", 7))
    display_files("a-1")

    shown = view(data_dir, hmac_key)

    assert shown == PhaseView(
        unit="a",
        phase="theory",
        cards_taught=1,
        cards_total=2,
        lessons_ready=True,
        minutes_per_credit=_theory_credit.MINUTES_PER_CREDIT,
        theory_minutes_today=30,
        solved=0,
        total=1,
        learn_target=(ALGO, "a"),
    )


def test_the_rate_is_the_minting_constant(
    tmp_path, monkeypatch, data_dir: Path, hmac_key: Path
):
    """One number, owned by the minting: change it there and the lock follows."""
    world(tmp_path, monkeypatch)
    states(hmac_key)
    began(hmac_key)
    monkeypatch.setattr(_unit_view, "MINUTES_PER_CREDIT", 7)

    assert view(data_dir, hmac_key).minutes_per_credit == 7


def test_a_multi_module_unit_targets_its_first_module_not_done(
    tmp_path, monkeypatch, data_dir: Path, hmac_key: Path
):
    """THEORY(b) with ``b1`` done: the target is ``b2``, which has no cards yet."""
    world(tmp_path, monkeypatch)
    states(hmac_key, "a", "b1")
    solved(data_dir, hmac_key, "a1")
    display_files("b1-1")

    shown = view(data_dir, hmac_key)

    assert (shown.unit, shown.phase) == ("b", "theory")
    assert shown.learn_target == (ALGO, "b2")
    assert (shown.cards_taught, shown.cards_total) == (1, 1)
    assert not shown.lessons_ready  # b2 has no card: the plan screen, not a lesson


def test_solve_offers_no_theory_and_counts_the_units_problems(
    tmp_path, monkeypatch, data_dir: Path, hmac_key: Path
):
    """SOLVE(a): no learn target; minutes after the flip never count."""
    world(tmp_path, monkeypatch)
    states(hmac_key, "a")  # done at t=1.0, long before today's teaching
    taught(hmac_key, NOW, ("a", 30))
    display_files("a-1", "a-2")

    shown = view(data_dir, hmac_key)

    assert (shown.unit, shown.phase) == ("a", "solve")
    assert shown.learn_target is None
    assert not shown.lessons_ready
    assert (shown.solved, shown.total) == (0, 1)
    assert shown.theory_minutes_today == 0


def test_every_unit_finished_is_none_with_no_unit(
    tmp_path, monkeypatch, data_dir: Path, hmac_key: Path
):
    """``unit`` is "" and phase "none"; there are no cards to count."""
    world(tmp_path, monkeypatch)
    states(hmac_key, "a", "b1", "b2")
    solved(data_dir, hmac_key, "a1", "b1-easy")
    display_files()

    shown = view(data_dir, hmac_key)

    assert (shown.unit, shown.phase, shown.learn_target) == ("", "none", None)
    assert (shown.cards_taught, shown.cards_total) == (None, None)
    assert (shown.solved, shown.total) == (0, 0)


def test_unreadable_tutor_display_files_read_as_no_cards(
    tmp_path, monkeypatch, caplog, data_dir: Path, hmac_key: Path
):
    """A torn ``cards.json``: cards None, a warning, and the phase still shown."""
    world(tmp_path, monkeypatch)
    states(hmac_key)
    began(hmac_key)
    display_files()
    (_theory.TUTOR_DATA_DIR / "subjects" / ALGO / "cards.json").write_text("{")

    with caplog.at_level(logging.WARNING):
        shown = view(data_dir, hmac_key)

    assert (shown.unit, shown.phase) == ("a", "theory")
    assert (shown.cards_taught, shown.cards_total, shown.lessons_ready) == (
        None,
        None,
        False,
    )
    assert caplog.records


def test_an_unreadable_tutor_ledger_shows_zero_minutes(
    tmp_path, monkeypatch, data_dir: Path, hmac_key: Path
):
    """C2 readable, C1 missing: the minting would pay nothing, the view shows 0."""
    world(tmp_path, monkeypatch)
    states(hmac_key)
    began(hmac_key)

    assert view(data_dir, hmac_key).theory_minutes_today == 0


def test_cannot_check_holds_the_last_signed_phase(
    tmp_path, monkeypatch, data_dir: Path, hmac_key: Path
):
    """No C2 file: the C3 file the guard last signed decides, with no cards."""
    world(tmp_path, monkeypatch)
    display_files("a-1")
    held = PhaseState(unit="a", phase="theory", subject=ALGO, modules=("a",))
    write_phase(held, day=DAY, now=NOW, key_file=hmac_key)

    shown = view(data_dir, hmac_key)

    assert (shown.unit, shown.phase, shown.learn_target) == ("a", "theory", (ALGO, "a"))
    assert (shown.cards_taught, shown.theory_minutes_today) == (None, 0)


def test_nothing_signed_at_all_shows_todays_list(data_dir: Path, hmac_key: Path):
    """No curriculum, no C2, no C3: phase "none", the list as it is today."""
    shown = view(data_dir, hmac_key)

    assert (shown.unit, shown.phase, shown.cards_total) == ("", "none", None)
