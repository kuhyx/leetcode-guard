"""The one-minute harvester signs progress, under its own four rules.

It writes only in a run that minted a credit, never while a lock is up, never
in the run that creates the ledger, and never on a day the gate stands down or
defers. A row that cannot be written costs the row and nothing else.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import earned_time
import freedays

from leetcode_guard import _harvest_run
from leetcode_guard._daycost import day_cost, local_today
from leetcode_guard._ledger import to_json
from leetcode_guard._ledger_entries import credit_entry
from leetcode_guard._ledger_io import append, load_ledger, save_ledger
from leetcode_guard.tests._ledger_fixtures import NOW, submission
from leetcode_guard.tests._net_fixtures import recent_ac_result, submission_row
from leetcode_guard.tests.test_harvest_run import seeded_ledger, stub_client

if TYPE_CHECKING:
    from pathlib import Path


def rows(data_dir: Path, key: Path) -> list[str]:
    """Every progress row id in the live (test) ledger."""
    ledger = load_ledger(data_dir / "ledger.json", key_file=key)
    return [entry.entry_id for entry in ledger.of_kind("progress")]


def today_price() -> int:
    """What today costs on an ordinary day."""
    return day_cost(local_today())


def test_a_solve_that_leaves_the_day_short_signs_progress(
    monkeypatch, data_dir: Path, hmac_key: Path
):
    """One credit minted, still short: done 1 of the day's price."""
    seeded_ledger(data_dir / "ledger.json", hmac_key)
    stub_client(monkeypatch, recent_ac_result([submission_row("42", "two-sum")]))

    _harvest_run.main(key_file=hmac_key)

    assert rows(data_dir, hmac_key) == [f"progress:{local_today()}:1:{today_price()}"]
    ledger = load_ledger(data_dir / "ledger.json", key_file=hmac_key)
    row = to_json(next(iter(ledger.of_kind("progress"))))
    assert earned_time.verified(row, hmac_key.read_bytes().strip())
    assert ledger.has("ac:42")
    assert not ledger.of_kind("charge")


def test_a_harvest_that_minted_nothing_writes_no_progress(
    monkeypatch, data_dir: Path, hmac_key: Path
):
    """Banked credit alone never signs: only a run that minted does."""
    seeded_ledger(data_dir / "ledger.json", hmac_key)
    ledger = load_ledger(data_dir / "ledger.json", key_file=hmac_key)
    banked = credit_entry(
        submission("old"), day=local_today(), now=NOW, key_file=hmac_key
    )
    append(ledger, [banked])
    save_ledger(data_dir / "ledger.json", ledger)
    stub_client(monkeypatch, recent_ac_result([submission_row("old", "two-sum")]))

    _harvest_run.main(key_file=hmac_key)

    assert rows(data_dir, hmac_key) == []


def test_the_run_that_has_no_ledger_writes_no_progress(
    monkeypatch, capsys, data_dir: Path, hmac_key: Path
):
    """``rm ledger.json`` earns nothing: the harvester will not even seed."""
    stub_client(monkeypatch, recent_ac_result([submission_row("42", "two-sum")]))

    _harvest_run.main(key_file=hmac_key)

    assert not (data_dir / "ledger.json").exists()
    assert "not seeded" in capsys.readouterr().out


def test_after_a_deleted_ledger_progress_waits_for_a_minted_credit(
    monkeypatch, data_dir: Path, hmac_key: Path
):
    """A re-seeded ledger has no progress until a credit is minted."""
    seeded_ledger(data_dir / "ledger.json", hmac_key)
    stub_client(monkeypatch, recent_ac_result([]))

    _harvest_run.main(key_file=hmac_key)

    assert rows(data_dir, hmac_key) == []


def test_a_free_day_gets_no_progress(monkeypatch, data_dir: Path, hmac_key: Path):
    """A stood-down day has no price to be partway through."""
    seeded_ledger(data_dir / "ledger.json", hmac_key)
    stub_client(monkeypatch, recent_ac_result([submission_row("42", "two-sum")]))
    monkeypatch.setattr(freedays, "is_free_day", lambda _day: True)

    _harvest_run.main(key_file=hmac_key)

    assert rows(data_dir, hmac_key) == []


def test_a_deferred_gate_gets_no_progress(monkeypatch, data_dir: Path, hmac_key: Path):
    """While the morning session defers the gate, the credit lands, no row."""
    seeded_ledger(data_dir / "ledger.json", hmac_key)
    stub_client(monkeypatch, recent_ac_result([submission_row("42", "two-sum")]))
    monkeypatch.setattr(
        _harvest_run, "defer_for_morning_session", lambda _now: "morning session"
    )

    _harvest_run.main(key_file=hmac_key)

    assert rows(data_dir, hmac_key) == []
    assert load_ledger(data_dir / "ledger.json", key_file=hmac_key).has("ac:42")


def test_a_night_lockdown_defers_progress_too(
    monkeypatch, data_dir: Path, hmac_key: Path
):
    """The gate does not re-arm after tonight's lockdown, so nothing to prove."""
    seeded_ledger(data_dir / "ledger.json", hmac_key)
    stub_client(monkeypatch, recent_ac_result([submission_row("42", "two-sum")]))
    monkeypatch.setattr(
        _harvest_run, "defer_for_evening_lockdown", lambda _now: "night lockdown"
    )

    _harvest_run.main(key_file=hmac_key)

    assert rows(data_dir, hmac_key) == []


def test_a_row_that_cannot_be_built_costs_only_the_row(
    monkeypatch, capsys, data_dir: Path, hmac_key: Path, caplog
):
    """The credit is in the ledger and the run still reports it; a warning says why."""
    seeded_ledger(data_dir / "ledger.json", hmac_key)
    stub_client(monkeypatch, recent_ac_result([submission_row("42", "two-sum")]))

    def boom(**_kwargs: object) -> None:
        message = "row builder broke"
        raise ValueError(message)

    monkeypatch.setattr("leetcode_guard._gate_progress.progress_entry", boom)

    with caplog.at_level(logging.WARNING):
        _harvest_run.main(key_file=hmac_key)

    assert load_ledger(data_dir / "ledger.json", key_file=hmac_key).has("ac:42")
    assert "credited 1" in capsys.readouterr().out
    assert any(r.levelno >= logging.WARNING for r in caplog.records)
    assert rows(data_dir, hmac_key) == []
