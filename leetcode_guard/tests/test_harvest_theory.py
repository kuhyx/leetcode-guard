"""The one-minute harvester mints theory credits, even when LeetCode is down."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from leetcode_guard import _harvest_run
from leetcode_guard._daycost import local_today
from leetcode_guard._ledger_io import load_ledger
from leetcode_guard._phase_file import read_phase
from leetcode_guard.tests._net_fixtures import (
    null_data_result,
    recent_ac_result,
    submission_row,
)
from leetcode_guard.tests._theory_scenario import states, taught, world
from leetcode_guard.tests.test_harvest_run import (
    seeded_ledger,
    stub_client,
    unlocked_decision,
)

if TYPE_CHECKING:
    from pathlib import Path


def test_theory_minutes_credit_and_settle_while_leetcode_cannot_be_checked(
    tmp_path, monkeypatch, capsys, data_dir: Path, hmac_key: Path
):
    """A LeetCode outage must not hold back a separately signed source."""
    seeded_ledger(data_dir / "ledger.json", hmac_key)
    world(tmp_path, monkeypatch)
    states(hmac_key)
    taught(hmac_key, datetime.now().astimezone(), ("a", 30))
    stub_client(monkeypatch, null_data_result())
    seen: list[str] = []

    def paid(ledger, **_kwargs):
        seen.extend(ledger.entries)
        return unlocked_decision(hmac_key)

    monkeypatch.setattr(_harvest_run, "decide_today", paid)

    _harvest_run.main(key_file=hmac_key)

    out = capsys.readouterr().out
    assert "could not check" in out
    assert "; theory credited 2; settled today" in out
    ids = load_ledger(data_dir / "ledger.json", key_file=hmac_key).entries
    assert f"theory:{local_today()}:2" in ids
    assert f"charge:{local_today()}" in ids
    assert f"theory:{local_today()}:1" in seen  # the decision saw the new credit


def test_no_theory_and_no_solve_settles_nothing(
    tmp_path, monkeypatch, capsys, data_dir: Path, hmac_key: Path
):
    """Nothing minted: the line is the solve line alone and no charge is written."""
    seeded_ledger(data_dir / "ledger.json", hmac_key)
    world(tmp_path, monkeypatch)
    states(hmac_key)
    stub_client(monkeypatch, recent_ac_result([]))

    _harvest_run.main(key_file=hmac_key)

    assert "nothing new (0 known)\n" in capsys.readouterr().out
    assert len(load_ledger(data_dir / "ledger.json").entries) == 1


def test_a_solve_that_finishes_the_unit_moves_the_phase_on_in_the_same_run(
    tmp_path, monkeypatch, capsys, data_dir: Path, hmac_key: Path
):
    """SOLVE(a) and a's last Easy accepted: this run's C3 already says THEORY(b).

    The tutor reads C3 to know what it may teach; a phase decided before the
    run's solves were credited left it refusing unit b for one more minute
    (e2e case e, 2026-11-22). Today's minutes on b pay in the same run too.
    """
    seeded_ledger(data_dir / "ledger.json", hmac_key)
    world(tmp_path, monkeypatch)
    states(hmac_key, "a")
    taught(hmac_key, datetime.now().astimezone(), ("b1", 12))
    stub_client(monkeypatch, recent_ac_result([submission_row("42", "a1")]))

    _harvest_run.main(key_file=hmac_key)

    phase = read_phase(hmac_key)
    assert phase is not None
    assert (phase.unit, phase.phase, phase.modules) == ("b", "theory", ("b1", "b2"))
    assert "credited 1; theory credited 1" in capsys.readouterr().out
    ids = load_ledger(data_dir / "ledger.json", key_file=hmac_key).entries
    assert {"ac:42", f"theory:{local_today()}:1"} <= set(ids)
