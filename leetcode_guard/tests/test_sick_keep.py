"""Sick days that keep lockers (sickdays 0.2.0): a kept leetcode is a normal day.

A sick day stands this gate down only when ``leetcode`` is not in its keep
set. The missed-ring date of a workday penalty belongs to the ``alarm``
switch; the penalty date belongs to leetcode, because leetcode is what the
penalty charges.
"""

from __future__ import annotations

from datetime import date
import json
from typing import TYPE_CHECKING

from gatelock.log_integrity import compute_entry_hmac
import pytest
import sickdays

from leetcode_guard import _gate_today, _status_projection, _workday_penalty
from leetcode_guard._daycost import day_cost
from leetcode_guard._gate import GateState
from leetcode_guard._ledger_io import Ledger
from leetcode_guard._status_full import explain_not_triggered
from leetcode_guard._workday_penalty import workday_penalty_for
from leetcode_guard.tests._ledger_fixtures import MONDAY, NOW, TUESDAY, WEDNESDAY
from leetcode_guard.tests.test_projection import SAT
from leetcode_guard.tests.test_status_gather import full_for

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

KEEP_LEETCODE = frozenset({sickdays.LOCKER_LEETCODE})
KEEP_ALARM = frozenset({sickdays.LOCKER_ALARM})
KEEP_NOTHING: frozenset[str] = frozenset()


def sick_with(
    monkeypatch: pytest.MonkeyPatch, keep_by_day: Mapping[date, frozenset[str]]
) -> None:
    """Fake the pool: these days are sick, each keeping the given lockers.

    ``is_sick_day`` is faked too, so code still asking the 0.1.0 question sees
    the day as sick -- and stands down where a kept locker must not.
    """

    def stands_down(locker: str, day: date, **_kw: object) -> bool:
        assert locker in sickdays.LOCKERS
        return day in keep_by_day and locker not in keep_by_day[day]

    def is_sick_day(day: date, **_kw: object) -> bool:
        return day in keep_by_day

    def kept_lockers(day: date, **_kw: object) -> frozenset[str]:
        return keep_by_day.get(day, KEEP_NOTHING)

    monkeypatch.setattr(sickdays, "stands_down", stands_down)
    monkeypatch.setattr(sickdays, "is_sick_day", is_sick_day)
    monkeypatch.setattr(sickdays, "kept_lockers", kept_lockers)


def every_day_sick(monkeypatch: pytest.MonkeyPatch, keep: frozenset[str]) -> None:
    """Fake a pool where every day is sick and keeps ``keep``."""

    def stands_down(locker: str, _day: date | None = None, **_kw: object) -> bool:
        return locker not in keep

    monkeypatch.setattr(sickdays, "stands_down", stands_down)
    monkeypatch.setattr(sickdays, "is_sick_day", lambda *_a, **_k: True)


@pytest.fixture
def penalty_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """Write wake-alarm's signed penalty file: ``penalty_file(penalty, issued)``."""
    key = tmp_path / "hmac.key"
    key.write_bytes(b"1" * 32)
    import gatelock.log_integrity

    monkeypatch.setattr(gatelock.log_integrity, "DEFAULT_HMAC_KEY_FILE", key)

    def _write(penalty: date, issued: date) -> None:
        entry: dict[str, object] = {
            "penalty_date": penalty.isoformat(),
            "issued_date": issued.isoformat(),
        }
        entry["hmac"] = compute_entry_hmac(entry)
        _workday_penalty.WORKDAY_PENALTY_FILE.write_text(json.dumps(entry))

    return _write


def test_a_sick_day_keeping_leetcode_locks_like_any_day():
    today = date.today()
    sickdays.add_sick_day(today, keep=KEEP_LEETCODE, is_free=lambda _day: False)

    decision = _gate_today.decide_today(Ledger(), day=today, now=NOW)

    assert decision.state is not GateState.UNLOCKED_SICK_DAY
    assert decision.locked


def test_a_sick_day_keeping_only_other_lockers_still_stands_down():
    today = date.today()
    keep = (sickdays.LOCKER_WORKOUT, sickdays.LOCKER_ALARM)
    sickdays.add_sick_day(today, keep=keep, is_free=lambda _day: False)

    decision = _gate_today.decide_today(Ledger(), day=today, now=NOW)

    assert decision.state is GateState.UNLOCKED_SICK_DAY


def test_a_kept_past_sick_day_with_no_charge_is_owed(debt_starts, monkeypatch):
    debt_starts(MONDAY)
    sick_with(monkeypatch, {MONDAY: KEEP_LEETCODE, TUESDAY: KEEP_ALARM})

    decision = _gate_today.decide_today(Ledger(), day=WEDNESDAY, now=NOW)

    assert decision.debt.missed_days == 1
    assert decision.debt.owed == day_cost(MONDAY)


def test_a_missed_ring_on_a_sick_day_keeping_the_alarm_still_penalises(
    penalty_file, monkeypatch
):
    penalty_file(WEDNESDAY, TUESDAY)

    sick_with(monkeypatch, {TUESDAY: KEEP_ALARM})
    assert workday_penalty_for(WEDNESDAY) is True

    sick_with(monkeypatch, {TUESDAY: KEEP_LEETCODE})
    assert workday_penalty_for(WEDNESDAY) is False


def test_the_penalty_day_follows_the_leetcode_switch(penalty_file, monkeypatch):
    penalty_file(WEDNESDAY, TUESDAY)
    plain = _gate_today.decide_today(Ledger(), day=WEDNESDAY, now=NOW)

    sick_with(monkeypatch, {WEDNESDAY: KEEP_LEETCODE})
    kept = _gate_today.decide_today(Ledger(), day=WEDNESDAY, now=NOW)
    sick_with(monkeypatch, {WEDNESDAY: KEEP_ALARM})
    off = _gate_today.decide_today(Ledger(), day=WEDNESDAY, now=NOW)

    assert plain.cost > day_cost(WEDNESDAY)
    assert (kept.cost, kept.locked) == (plain.cost, True)
    assert off.state is GateState.UNLOCKED_SICK_DAY
    assert off.cost == day_cost(WEDNESDAY)


@pytest.mark.parametrize(
    ("keep", "off"), [(KEEP_LEETCODE, False), (KEEP_ALARM, True), (KEEP_NOTHING, True)]
)
def test_the_what_if_counts_a_kept_day_as_gated(monkeypatch, keep, off):
    every_day_sick(monkeypatch, keep)
    monkeypatch.setattr(_status_projection.freedays, "is_free_day", lambda _d: False)

    assert _status_projection._is_off_day(SAT) is off


def test_the_projection_counts_a_kept_sick_day_as_gated(
    data_dir: Path, hmac_key: Path, monkeypatch
):
    from leetcode_guard._status import gather_status

    snapshot = gather_status(ledger_path=data_dir / "ledger.json", key_file=hmac_key)
    every_day_sick(monkeypatch, KEEP_LEETCODE)

    report = _status_projection.build_report(
        snapshot, None, _status_projection.ProjectionInputs("31.12.2999")
    )

    assert report.projection is not None
    assert report.projection.sick_days == 0
    assert report.projection.gated_days > 0


@pytest.mark.parametrize(("keep", "said"), [(KEEP_LEETCODE, True), (KEEP_ALARM, False)])
def test_status_says_a_kept_sick_day_is_ordinary(
    data_dir: Path, hmac_key: Path, monkeypatch, keep, said
):
    sick_with(monkeypatch, {MONDAY: keep})

    lines = explain_not_triggered(full_for(data_dir, hmac_key))

    assert any("keeps leetcode" in line for line in lines) is said


def test_a_keep_edit_never_reaches_the_real_pool(tmp_path: Path):
    today = date.today()
    sickdays.add_sick_day(today, is_free=lambda _day: False)
    sickdays.set_kept_lockers(today, KEEP_LEETCODE)

    assert (tmp_path / "sickdays").is_dir()
    assert sickdays.kept_lockers(today) == KEEP_LEETCODE
