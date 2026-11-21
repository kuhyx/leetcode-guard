#!/usr/bin/env python3
"""Prove the flag works on REAL ledger credits, with synthetic heartbeats.

``test_attempt_report.py`` builds its credits by hand, so it can only repeat
what its author believed a credit row looks like. This copies the real ledger
into a temp directory, takes three real credit rows, seeds an ``attempts.json``
beside the copy and asks the report::

    python3 -m scripts.verify_flagged_replay

* A (taught theory, 26 minute-apart beats ending at the accept): flagged with
  exactly 1500 s of active time;
* B (the same beats, theory still pending): measured, not flagged;
* C (no record): listed as unknown;
* the other side: A with only 9 beats is not flagged.

Read-only for the real data: the ledger is only copied, and the real ledger's
and ``attempts.json``'s mtimes are compared before and after. Skips loudly at
exit 0 when the ledger holds fewer than three usable credits (a missing
precondition, not a failure). Exit 1 when any assertion fails.
"""

from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path
import shutil
import sys
import tempfile
from typing import Any
from unittest import mock

from leetcode_guard import _attempt_paths, _attempt_report, _constants, _flagged_cli
from leetcode_guard._attempt_model import (
    AttemptRecord,
    Beat,
    Submission,
    day_of,
    record_key,
    to_document,
)
from leetcode_guard._attempts import Credit, credits_of, first_credits
from leetcode_guard._ledger_io import load_ledger

_EXIT_OK = 0
_EXIT_FAIL = 1
_MINUTE = 60
_LONG_RUN = 26
_SHORT_RUN = 9
_EXPECTED_ACTIVE = (_LONG_RUN - 1) * _MINUTE
_NEEDED = 3


def _records(
    credit: Credit,
    beat_count: int,
    theory: str,
    *,
    failed: bool = False,
) -> list[AttemptRecord]:
    """The day-records of one synthetic attempt ending at the credit's accept."""
    end = credit.accepted_at
    beats = [Beat(end - _MINUTE * i, "description") for i in range(beat_count)][::-1]
    subs = (
        {
            "replay-1": Submission("Wrong Answer", end - 5 * _MINUTE),
            "replay-2": Submission("Runtime Error", end - 2 * _MINUTE),
        }
        if failed
        else {}
    )
    found: dict[str, AttemptRecord] = {}
    for beat in beats:
        day = day_of(beat.at)
        found.setdefault(day, AttemptRecord(day, credit.slug)).beats.append(beat)
    for sub_id, sub in subs.items():
        day = day_of(sub.at)
        found.setdefault(day, AttemptRecord(day, credit.slug)).submissions[sub_id] = sub
    found[day_of(end)].theory_at_solve = theory
    return list(found.values())


def _seed(path: Path, *groups: list[AttemptRecord]) -> None:
    """Write the seeded ``attempts.json``."""
    merged: dict[str, AttemptRecord] = {}
    for group in groups:
        for found in group:
            merged[record_key(found.day, found.slug)] = found
    path.write_text(json.dumps(to_document(merged)), encoding="utf-8")


def _check(results: list[bool], label: str, *, passed: bool) -> None:
    """Print one PASS/FAIL line and record it."""
    print(f"{'PASS' if passed else 'FAIL'}: {label}")
    results.append(passed)


def _mtime(path: Path) -> int | None:
    """The mtime in ns, ``None`` when the file does not exist."""
    return path.stat().st_mtime_ns if path.exists() else None


def _slugs(rows: list[dict[str, Any]]) -> list[str]:
    return [row["slug"] for row in rows]


def _assert_report(workdir: Path, trio: list[Credit], results: list[bool]) -> None:
    """Seed the temp store, build the report and judge it."""
    a, b, c = trio
    attempts = workdir / "attempts.json"
    now = datetime.fromtimestamp(a.accepted_at + 3600, tz=UTC)
    _seed(
        attempts,
        _records(a, _LONG_RUN, "done", failed=True),
        _records(b, _LONG_RUN, "pending"),
    )
    with (
        mock.patch.object(_constants, "LEDGER_FILE", workdir / "ledger.json"),
        mock.patch.object(_attempt_paths, "ATTEMPTS_FILE", attempts),
    ):
        report = _attempt_report.load_report(now=now)
        flagged = {row["slug"]: row for row in report["flagged"]}
        _check(results, f"A {a.slug} is flagged", passed=a.slug in flagged)
        _check(
            results,
            "A has active_seconds == 1500",
            passed=flagged.get(a.slug, {}).get("active_seconds") == _EXPECTED_ACTIVE,
        )
        _check(
            results,
            "A's two failed submissions are counted",
            passed=flagged.get(a.slug, {}).get("failed")
            == {"Runtime Error": 1, "Wrong Answer": 1},
        )
        _check(
            results,
            f"B {b.slug} is measured and not flagged",
            passed=b.slug in _slugs(report["measured"]) and b.slug not in flagged,
        )
        _check(
            results,
            f"C {c.slug} is unknown",
            passed=c.slug in _slugs(report["unknown"])
            and c.slug not in _slugs(report["measured"]),
        )
        if a.slug in flagged:
            print(f"      sample: {_flagged_cli.flagged_line(flagged[a.slug])}")
        _seed(attempts, _records(a, _SHORT_RUN, "done"))
        short = _attempt_report.load_report(now=now)
        _check(
            results,
            "the other side: A with 9 beats is not flagged",
            passed=a.slug not in _slugs(short["flagged"])
            and a.slug in _slugs(short["measured"]),
        )


def main() -> int:
    """Run the replay; the process exit code."""
    real_ledger = _constants.LEDGER_FILE
    real_attempts = _attempt_paths.ATTEMPTS_FILE
    if not real_ledger.exists():
        print(f"SKIP: no ledger at {real_ledger}; nothing to replay")
        return _EXIT_OK
    before = (_mtime(real_ledger), _mtime(real_attempts))
    results: list[bool] = []
    with tempfile.TemporaryDirectory(prefix="flagged-replay-") as tmp:
        workdir = Path(tmp)
        shutil.copyfile(real_ledger, workdir / "ledger.json")
        earned = first_credits(credits_of(load_ledger(workdir / "ledger.json")))
        newest = sorted(earned, key=lambda credit: -credit.accepted_at)
        if len(newest) < _NEEDED:
            print(f"SKIP: only {len(newest)} usable credits, need {_NEEDED}")
            return _EXIT_OK
        _assert_report(workdir, newest[:_NEEDED], results)
    after = (_mtime(real_ledger), _mtime(real_attempts))
    _check(
        results,
        "the real ledger and attempts.json are untouched",
        passed=before == after,
    )
    return _EXIT_OK if all(results) else _EXIT_FAIL


if __name__ == "__main__":
    sys.exit(main())
