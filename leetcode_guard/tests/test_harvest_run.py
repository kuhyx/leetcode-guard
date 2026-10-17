"""Tests for the out-of-lock harvest (``python3 -m leetcode_guard._harvest_run``).

The failure it fixes, 2026-10-17: a sick day meant no lock window, so five
accepted submissions reached LeetCode and never the ledger -- harvesting lived
only in the lock's poll loop.
"""

from __future__ import annotations

import fcntl
from types import SimpleNamespace
from typing import TYPE_CHECKING

import pytest

from leetcode_guard import _harvest_run
from leetcode_guard._auth import AuthState
from leetcode_guard._constants import EXIT_OK
from leetcode_guard._daycost import local_today
from leetcode_guard._ledger_entries import bootstrap_entry, charge_entry
from leetcode_guard._ledger_io import Ledger, append, load_ledger, save_ledger
from leetcode_guard._settings import Client
from leetcode_guard.tests._ledger_fixtures import NOW
from leetcode_guard.tests._net_fixtures import (
    fake_post,
    null_data_result,
    recent_ac_result,
    submission_row,
)

if TYPE_CHECKING:
    from pathlib import Path

    from leetcode_guard._leetcode import GraphQLResult


def stub_client(monkeypatch: pytest.MonkeyPatch, *results: GraphQLResult) -> None:
    """Wire ``build_client`` to a scripted fake."""
    post = fake_post(*results)
    monkeypatch.setattr(
        _harvest_run,
        "build_client",
        lambda: Client(
            post=post, auth=AuthState(cookies=None, note="signed out"), username="k"
        ),
    )


def seeded_ledger(path: Path, key_file: Path) -> None:
    """A ledger past its first run, with nothing credited yet."""
    ledger = Ledger()
    entry = bootstrap_entry(day=local_today(), now=NOW, seeded=0, key_file=key_file)
    append(ledger, [entry])
    save_ledger(path, ledger)


def unlocked_decision(key_file: Path) -> SimpleNamespace:
    """What ``decide_today`` returns once the credits cover the day."""
    charge = charge_entry(local_today(), now=NOW, key_file=key_file)
    return SimpleNamespace(locked=False, charge=charge)


def test_credits_a_solve_made_with_no_lock_running(
    monkeypatch, capsys, data_dir: Path, hmac_key: Path
):
    """The 2026-10-17 failure: no lock window, the solve must still land."""
    seeded_ledger(data_dir / "ledger.json", hmac_key)
    stub_client(monkeypatch, recent_ac_result([submission_row("42", "two-sum")]))

    assert _harvest_run.main(key_file=hmac_key) == EXIT_OK

    assert load_ledger(data_dir / "ledger.json").has("ac:42")
    assert "credited 1" in capsys.readouterr().out


def test_settles_the_day_when_a_fresh_credit_covers_it(
    monkeypatch, capsys, data_dir: Path, hmac_key: Path
):
    """A solve after the last timer slot must not leave the day owed as debt."""
    seeded_ledger(data_dir / "ledger.json", hmac_key)
    stub_client(monkeypatch, recent_ac_result([submission_row("42", "two-sum")]))
    monkeypatch.setattr(
        _harvest_run, "decide_today", lambda *a, **k: unlocked_decision(hmac_key)
    )

    _harvest_run.main(key_file=hmac_key)

    ledger = load_ledger(data_dir / "ledger.json")
    assert ledger.has(f"charge:{local_today().isoformat()}")
    assert "settled today" in capsys.readouterr().out


def test_never_spends_banked_credit_without_a_fresh_solve(
    monkeypatch, data_dir: Path, hmac_key: Path
):
    """A 00:05 tick must not settle a day that may yet be marked free or sick."""
    seeded_ledger(data_dir / "ledger.json", hmac_key)
    stub_client(monkeypatch, recent_ac_result([]))
    monkeypatch.setattr(
        _harvest_run, "decide_today", lambda *a, **k: unlocked_decision(hmac_key)
    )

    _harvest_run.main(key_file=hmac_key)

    assert not load_ledger(data_dir / "ledger.json").of_kind("charge")


def test_a_still_locked_day_gets_credit_but_no_charge(
    monkeypatch, data_dir: Path, hmac_key: Path
):
    """Not enough yet: bank the credit, write no charge, open no window."""
    seeded_ledger(data_dir / "ledger.json", hmac_key)
    stub_client(monkeypatch, recent_ac_result([submission_row("42", "two-sum")]))
    monkeypatch.setattr(
        _harvest_run,
        "decide_today",
        lambda *a, **k: SimpleNamespace(locked=True, charge=None),
    )

    _harvest_run.main(key_file=hmac_key)

    ledger = load_ledger(data_dir / "ledger.json")
    assert ledger.has("ac:42")
    assert not ledger.of_kind("charge")


def test_stands_aside_while_a_lock_is_up(
    monkeypatch, capsys, data_dir: Path, hmac_key: Path
):
    """The lock saves its whole in-memory ledger; a second writer gets erased."""
    seeded_ledger(data_dir / "ledger.json", hmac_key)
    monkeypatch.setattr(
        _harvest_run, "build_client", lambda: pytest.fail("must not reach LeetCode")
    )
    with (data_dir / "instance.lock").open("a+", encoding="utf-8") as held:
        fcntl.flock(held.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        _harvest_run.main(key_file=hmac_key)

    assert "lock is up" in capsys.readouterr().out
    assert not load_ledger(data_dir / "ledger.json").of_kind("credit")


def test_stands_aside_when_a_lock_starts_during_the_probe(
    monkeypatch, capsys, data_dir: Path, hmac_key: Path
):
    """The probe is the slow part; a lock armed meanwhile owns the ledger."""
    seeded_ledger(data_dir / "ledger.json", hmac_key)
    stub_client(monkeypatch, recent_ac_result([submission_row("42", "two-sum")]))
    answers = iter([False, True])
    monkeypatch.setattr(_harvest_run, "lock_is_up", lambda _path: next(answers))

    _harvest_run.main(key_file=hmac_key)

    assert "lock is up" in capsys.readouterr().out
    assert not load_ledger(data_dir / "ledger.json").has("ac:42")


def test_never_holds_the_instance_lock(data_dir: Path):
    """Holding it would make a 09:00 run stand down and skip the day's gate."""
    path = data_dir / "instance.lock"
    assert not _harvest_run.lock_is_up(path)
    with path.open("a+", encoding="utf-8") as probe:
        fcntl.flock(probe.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)


def test_an_unopenable_lock_file_counts_as_a_lock(tmp_path: Path):
    """Cannot tell means do not write: a lock may be holding the ledger."""
    blocker = tmp_path / "not-a-dir"
    blocker.write_text("", encoding="utf-8")
    assert _harvest_run.lock_is_up(blocker / "instance.lock")


def test_a_second_harvester_stands_aside(
    monkeypatch, capsys, data_dir: Path, hmac_key: Path
):
    """The timer tick and a browser ring can overlap; only one may write."""
    seeded_ledger(data_dir / "ledger.json", hmac_key)
    monkeypatch.setattr(
        _harvest_run, "build_client", lambda: pytest.fail("must not reach LeetCode")
    )
    with (data_dir / "harvest.lock").open("a+", encoding="utf-8") as held:
        fcntl.flock(held.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        _harvest_run.main(key_file=hmac_key)

    assert "another harvest" in capsys.readouterr().out


def test_never_seeds_an_unseeded_ledger(
    monkeypatch, capsys, data_dir: Path, hmac_key: Path
):
    """Seeding is the lock's first run; a harvester seeding would mint the feed."""
    stub_client(monkeypatch, recent_ac_result([submission_row("42", "two-sum")]))

    _harvest_run.main(key_file=hmac_key)

    assert "not seeded" in capsys.readouterr().out
    assert not (data_dir / "ledger.json").exists()


def test_an_unreadable_feed_writes_nothing(
    monkeypatch, capsys, data_dir: Path, hmac_key: Path
):
    """Could not check is not "no new solves", and neither writes."""
    seeded_ledger(data_dir / "ledger.json", hmac_key)
    stub_client(monkeypatch, null_data_result())

    _harvest_run.main(key_file=hmac_key)

    assert "could not check" in capsys.readouterr().out
    assert len(load_ledger(data_dir / "ledger.json").entries) == 1


def test_known_submissions_are_not_credited_twice(
    monkeypatch, capsys, data_dir: Path, hmac_key: Path
):
    """Every tick re-reads the same 20 rows; only unseen ids mint."""
    seeded_ledger(data_dir / "ledger.json", hmac_key)
    stub_client(
        monkeypatch,
        recent_ac_result([submission_row("42", "two-sum")]),
        recent_ac_result([submission_row("42", "two-sum")]),
    )

    _harvest_run.main(key_file=hmac_key)
    _harvest_run.main(key_file=hmac_key)

    assert len(load_ledger(data_dir / "ledger.json").of_kind("credit")) == 1
    assert "nothing new" in capsys.readouterr().out


def test_does_nothing_before_the_gate_starts(monkeypatch, capsys):
    """The timer fires from install day; it costs no network until in force."""
    monkeypatch.setattr(
        _harvest_run, "GATE_START_DATE", local_today().replace(year=9999)
    )
    monkeypatch.setattr(
        _harvest_run, "build_client", lambda: pytest.fail("must not reach LeetCode")
    )

    _harvest_run.main()

    assert "not active" in capsys.readouterr().out
