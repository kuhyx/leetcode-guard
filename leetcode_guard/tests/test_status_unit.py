"""``--status`` names the current unit and phase, and never mints or writes C3.

The scenario is ``_theory_scenario``'s: unit ``a`` (module ``a``, Easy ``a1``)
then unit ``b`` (modules ``b1``/``b2``, Easy ``b1-easy``). "Cannot check" must
read as unknown, never as zero (the ``ProbeStatus`` rule, applied here).
"""

from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from typing import TYPE_CHECKING

from leetcode_guard import _cli_commands, _phase_file, _status_unit
from leetcode_guard._ledger_io import append, load_ledger, save_ledger
from leetcode_guard._phase import PhaseState
from leetcode_guard._phase_file import write_phase
from leetcode_guard._status import format_status, gather_status
from leetcode_guard._theory_credit import theory_entry
from leetcode_guard.tests._theory_scenario import states, taught, world
from leetcode_guard.tests._tutor_fixtures import ALGO
from leetcode_guard.tests.test_unit_view import DAY, NOW, display_files, solved

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

    from leetcode_guard._status_model import StatusSnapshot


def snapshot(data_dir: Path, key: Path) -> StatusSnapshot:
    """``gather_status`` at :data:`NOW` over the scratch ledger."""
    return gather_status(now=NOW, ledger_path=data_dir / "ledger.json", key_file=key)


def minted(data_dir: Path, key: Path, *days_and_units: tuple[int, str]) -> None:
    """Theory credits already in the ledger: (days before DAY, unit) each."""
    ledger = load_ledger(data_dir / "ledger.json", key_file=key)
    rows = [
        theory_entry(
            (DAY - timedelta(days=back), NOW - timedelta(days=back)),
            n=n,
            unit=unit,
            minutes=12 * n,
            key_file=key,
        )
        for n, (back, unit) in enumerate(days_and_units, start=1)
    ]
    append(ledger, rows)
    save_ledger(data_dir / "ledger.json", ledger)


def test_theory_shows_the_unit_the_rate_todays_credits_and_the_learn_route(
    tmp_path, monkeypatch, data_dir: Path, hmac_key: Path
):
    """THEORY(a): 30 minutes today, two credits already minted, lessons ready."""
    world(tmp_path, monkeypatch)
    states(hmac_key)
    taught(hmac_key, NOW, ("a", 30))
    display_files("a-1")
    minted(data_dir, hmac_key, (0, "a"), (0, "a"), (1, "a"))

    text = format_status(snapshot(data_dir, hmac_key))

    assert "unit       a -- theory, 0 / 1 Easy solved" in text
    assert "theory     30 min today, 12 min = 1 credit, 2 credits minted today" in text
    assert f"learn      tutor --route /learn/{ALGO}/a" in text


def test_a_status_read_never_mints_and_never_writes_the_phase_file(
    tmp_path, monkeypatch, data_dir: Path, hmac_key: Path
):
    """36 minutes would mint 3 credits in a poll; a status read mints none."""
    world(tmp_path, monkeypatch)
    states(hmac_key)
    taught(hmac_key, NOW, ("a", 36))
    save_ledger(data_dir / "ledger.json", load_ledger(data_dir / "ledger.json"))
    before = (data_dir / "ledger.json").read_bytes()

    unit = snapshot(data_dir, hmac_key).unit

    assert unit.minutes == 36
    assert unit.credits_today == 0
    assert (data_dir / "ledger.json").read_bytes() == before
    assert not _phase_file.PHASE_FILE.exists()


def test_lessons_not_ready_route_to_the_plan_screen_like_the_lock(
    tmp_path, monkeypatch, data_dir: Path, hmac_key: Path
):
    """No card for the module: the lock's learn button opens the plan; so does this."""
    world(tmp_path, monkeypatch)
    states(hmac_key)
    display_files(cards={})

    text = format_status(snapshot(data_dir, hmac_key))

    assert f"learn      tutor --route /plan/{ALGO}" in text


def test_solve_shows_the_units_problems_and_no_learn_route(
    tmp_path, monkeypatch, data_dir: Path, hmac_key: Path
):
    """SOLVE(a): theory done, a1 open; minutes after the flip count 0."""
    world(tmp_path, monkeypatch)
    states(hmac_key, "a")
    taught(hmac_key, NOW, ("a", 30))

    text = format_status(snapshot(data_dir, hmac_key))

    assert "unit       a -- solve, 0 / 1 Easy solved" in text
    assert "theory     0 min today, 12 min = 1 credit, 0 credits minted today" in text
    assert "learn " not in text


def test_every_unit_finished_shows_none(
    tmp_path, monkeypatch, data_dir: Path, hmac_key: Path
):
    """Phase none: no unit, no learn route, the credits line still there."""
    world(tmp_path, monkeypatch)
    states(hmac_key, "a", "b1", "b2")
    solved(data_dir, hmac_key, "a1", "b1-easy")

    text = format_status(snapshot(data_dir, hmac_key))

    assert "unit       none -- every unit is finished" in text
    assert "learn " not in text


def test_an_unreadable_tutor_ledger_reads_unknown_minutes_not_zero(
    tmp_path, monkeypatch, data_dir: Path, hmac_key: Path
):
    """C2 readable, C1 missing: the lock shows 0, the status says unknown."""
    world(tmp_path, monkeypatch)
    states(hmac_key)

    status = snapshot(data_dir, hmac_key)

    assert status.unit.minutes is None
    assert "theory     unknown min today" in format_status(status)
    assert _status_unit.unit_dict(status.unit)["theory_minutes_today"] is None


def test_unreadable_tutor_cards_read_unknown(
    tmp_path, monkeypatch, data_dir: Path, hmac_key: Path
):
    """A torn cards.json: the card counts are null, never 0 of 0."""
    world(tmp_path, monkeypatch)
    states(hmac_key)
    display_files()
    (tmp_path / "tutor" / "subjects" / ALGO / "cards.json").write_text("{")

    data = _status_unit.unit_dict(snapshot(data_dir, hmac_key).unit)

    assert (data["cards_taught"], data["cards_total"]) == (None, None)
    assert data["phase"] == "theory"


def test_cannot_check_holds_the_signed_phase_with_unknown_counts(
    tmp_path, monkeypatch, data_dir: Path, hmac_key: Path
):
    """No C2: the last signed C3 phase is shown, its counts as unknown."""
    world(tmp_path, monkeypatch)
    held = PhaseState(unit="b", phase="solve")
    write_phase(held, day=DAY, now=NOW, key_file=hmac_key)

    status = snapshot(data_dir, hmac_key)
    data = _status_unit.unit_dict(status.unit)

    assert "unit       b -- solve (held: could not check), unknown Easy solved" in (
        format_status(status)
    )
    assert (data["source"], data["solved"], data["total"]) == ("held", None, None)
    assert data["theory_minutes_today"] is None


def test_nothing_readable_at_all_says_unknown(data_dir: Path, hmac_key: Path):
    """No curriculum, no C2, no C3: unknown, never "every unit is finished"."""
    status = snapshot(data_dir, hmac_key)

    assert status.unit.source == "unknown"
    assert "unit       unknown -- could not check" in format_status(status)


def test_forged_and_past_theory_credits_are_not_todays(
    tmp_path, monkeypatch, data_dir: Path, hmac_key: Path
):
    """Only trusted ``theory:<today>:`` rows count; a forged one never does."""
    world(tmp_path, monkeypatch)
    states(hmac_key)
    minted(data_dir, hmac_key, (0, "a"), (2, "a"))
    ledger = load_ledger(data_dir / "ledger.json", key_file=hmac_key)
    forged = theory_entry((DAY, NOW), n=9, unit="a", minutes=99, key_file=hmac_key)
    append(ledger, [replace(forged, signature="0" * 64)])
    save_ledger(data_dir / "ledger.json", ledger)

    unit = snapshot(data_dir, hmac_key).unit

    assert (unit.credits_today, unit.credits_total) == (1, 2)


def test_cmd_status_prints_the_unit_lines(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    data_dir: Path,
    hmac_key: Path,
):
    """Through the real ``--status`` command: asserted on stdout, not the exit code."""
    world(tmp_path, monkeypatch)
    states(hmac_key, "a")
    real = _cli_commands.gather_status
    monkeypatch.setattr(
        _cli_commands,
        "gather_status",
        lambda: real(now=NOW, ledger_path=data_dir / "ledger.json", key_file=hmac_key),
    )

    _cli_commands.cmd_status()

    assert "unit       a -- solve, 0 / 1 Easy solved" in capsys.readouterr().out
