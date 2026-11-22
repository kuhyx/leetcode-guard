"""Minutes taught before THEORY(u) began never pay (C3 ``theory_since``, R2).

The tutor does not gate the SQL subject, so kuhy can teach it any time. Before
``theory_since`` those morning minutes paid at once when THEORY(sql) began.
"""

from __future__ import annotations

from datetime import datetime, timedelta
import json
from typing import TYPE_CHECKING

from gatelock.log_integrity import compute_entry_hmac

from leetcode_guard import _constants, _curriculum, _phase_file
from leetcode_guard._ledger_entries import credit_entry
from leetcode_guard._ledger_io import Ledger, append
from leetcode_guard._phase import PhaseState
from leetcode_guard._phase_file import phase_since, write_phase
from leetcode_guard._pool_cache import CachedPool, write_cache
from leetcode_guard._theory_credit import poll_theory
from leetcode_guard.tests._ledger_fixtures import submission
from leetcode_guard.tests._theory_scenario import states
from leetcode_guard.tests._tutor_fixtures import ALGO, teaching_row, write_tutor
from leetcode_guard.tests.test_problem import make

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

NOW = datetime(2026, 11, 24, 12, 0).astimezone()
DAY = NOW.date()
SQL = "mysql-8-for-timed-sql-coding-tests-joins-and"
SQL_UNIT = PhaseState(unit="sql", phase="theory", subject=SQL, modules=("sql-l",))


def _sql_world(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, key: Path) -> None:
    """Unit a (theory done, a1 unsolved) then unit sql; no C3 yet."""
    doc = {
        "units": [
            {"id": "a", "tags": ["x"], "tutor": {"subject": ALGO, "modules": ["a"]}},
            {
                "id": "sql",
                "tags": ["y"],
                "tutor": {"subject": SQL, "modules": ["sql-l"]},
            },
        ]
    }
    path = tmp_path / "curriculum.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    monkeypatch.setattr(_curriculum, "CURRICULUM_FILE", path)
    pool = (make("a1", topics=["x"]), make("s1", topics=["y"]))
    write_cache(
        _constants.POOL_CACHE_FILE,
        CachedPool(problems=pool, fetched_at=0.0, complete=True),
    )
    states(key, "a")


def _sql_rows(key: Path, *ends: datetime) -> None:
    """One signed 12-minute SQL teaching row ending at each of ``ends``."""
    write_tutor(
        "ledger.json",
        [
            teaching_row(
                f"sq{i}-m12", 12, ended=end, key_file=key, where=(SQL, "sql-l")
            )
            for i, end in enumerate(ends)
        ],
    )


def _poll(ledger: Ledger, data_dir: Path, key: Path, now: datetime = NOW):
    return poll_theory(ledger, data_dir / "ledger.json", day=DAY, now=now, key_file=key)


def test_sql_minutes_before_theory_began_mint_nothing(
    tmp_path, monkeypatch, data_dir: Path, hmac_key: Path
):
    """R2: 10 x 12 SQL minutes 08:00-10:00, THEORY(sql) begins at 12:00 -> 0."""
    _sql_world(tmp_path, monkeypatch, hmac_key)
    morning = NOW - timedelta(hours=4)
    _sql_rows(hmac_key, *(morning + timedelta(minutes=12 * i) for i in range(10)))
    ledger = Ledger()
    assert _poll(ledger, data_dir, hmac_key, morning).state.phase == "solve"
    append(
        ledger,
        [credit_entry(submission("1", "a1"), day=DAY, now=NOW, key_file=hmac_key)],
    )

    result = _poll(ledger, data_dir, hmac_key)

    assert (result.state.unit, result.state.phase) == ("sql", "theory")
    assert (result.minutes, result.minted) == (0, ())


def test_sql_minutes_after_theory_began_still_pay(
    tmp_path, monkeypatch, data_dir: Path, hmac_key: Path
):
    """The same day: one row before 12:00 pays nothing, two after it pay 2."""
    _sql_world(tmp_path, monkeypatch, hmac_key)
    ledger = Ledger()
    append(
        ledger,
        [credit_entry(submission("1", "a1"), day=DAY, now=NOW, key_file=hmac_key)],
    )
    _poll(ledger, data_dir, hmac_key)
    later = NOW + timedelta(minutes=30)
    _sql_rows(hmac_key, NOW - timedelta(minutes=5), later, later)

    result = _poll(ledger, data_dir, hmac_key, later + timedelta(minutes=1))

    assert (result.minutes, len(result.minted)) == (24, 2)


def _c3(detail: dict[str, object], key: Path) -> None:
    """Write a C3 row as an older guard did, signed under ``key``."""
    write_phase(SQL_UNIT, day=DAY, now=NOW, key_file=key)
    row = json.loads(_phase_file.PHASE_FILE.read_text(encoding="utf-8"))
    row["detail"] = detail
    del row["hmac"]
    row["hmac"] = compute_entry_hmac(row, key_file=key)
    _phase_file.PHASE_FILE.write_text(json.dumps(row), encoding="utf-8")


def test_sql_before_theory_a_c3_from_an_older_guard_starts_at_its_at(
    hmac_key: Path,
):
    """No ``theory_since`` on file: THEORY began at ``at``; carried into SOLVE."""
    teachable = [[SQL, "sql-l"]]
    _c3({"unit": "sql", "phase": "theory", "teachable": teachable, "at": 7.0}, hmac_key)
    assert phase_since(SQL_UNIT, hmac_key) == 7.0
    solve = PhaseState(unit="sql", phase="solve", subject=SQL, modules=("sql-l",))
    write_phase(solve, day=DAY, now=NOW, key_file=hmac_key)
    assert phase_since(solve, hmac_key) == 7.0
    _c3({"unit": "sql", "phase": "theory", "teachable": teachable}, hmac_key)
    assert phase_since(SQL_UNIT, hmac_key) is None


def test_sql_before_theory_reentering_theory_starts_over(hmac_key: Path):
    """SOLVE(u) -> THEORY(u) resets; another unit's C3 says nothing about u."""
    write_phase(SQL_UNIT, day=DAY, now=NOW, key_file=hmac_key)
    solve = PhaseState(unit="sql", phase="solve", subject=SQL, modules=("sql-l",))
    write_phase(solve, day=DAY, now=NOW + timedelta(hours=1), key_file=hmac_key)
    assert phase_since(solve, hmac_key) == NOW.timestamp()
    again = NOW + timedelta(hours=2)
    write_phase(SQL_UNIT, day=DAY, now=again, key_file=hmac_key)
    assert phase_since(SQL_UNIT, hmac_key) == again.timestamp()
    other = PhaseState(unit="a", phase="solve", subject=ALGO, modules=("a",))
    assert phase_since(other, hmac_key) is None
    write_phase(other, day=DAY, now=again, key_file=hmac_key)
    assert phase_since(other, hmac_key) == again.timestamp()
