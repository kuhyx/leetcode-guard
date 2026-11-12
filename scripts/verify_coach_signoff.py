#!/usr/bin/python3
"""Check item 2 of the coach sign-off (DOCS-coach-spec.md, "kuhy's done").

Since ``--since``: >=3 distinct problems of 268/260/169/137, each Accepted
after a coach session that logged ``req`` before the first ``code``, no hint
above H1, no ``reveal``, no ``retest``; on >=2 local dates; and the Claude Stop
hook (``leetcode_no_solution_stop.py``) never fired. Items 1 and 3 are kuhy's
word, not checked here::

    /usr/bin/python3 -m scripts.verify_coach_signoff --since 2026-11-07

System interpreter and ``-m``: ``gatelock`` lives only in its user site, and
``-m`` resolves ``leetcode_guard`` from the checkout.

**Accepted = a trusted ledger ``credit``**, the balance's own rule, timed by
``submitted_at`` (LeetCode epoch; ``day`` is only the harvest day). An
unreadable HMAC key is "cannot check" (exit 2), never "not solved". An
Accepted from before ``--since`` never counts on its own.

**Session rules copy ``leetcode report``** (whole file; the first ``code``
decides req-before-code), duplicated because scripts must not import each
other and ``report._req_before_code`` is private.

**A hook fire cannot be tied to a session**: ``.blocks`` files are keyed by
Claude session id and hold prompt ids only, so ANY one modified on or after
``--since`` fails. The Coach tab's leak bounce runs in the relay and writes no
``.blocks``, so it is not seen.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import UTC, date, datetime
import logging
from pathlib import Path
import sys
from typing import TYPE_CHECKING, Any, Final

from leetcode_coach import session_log
from leetcode_guard._balance import is_trusted
from leetcode_guard._constants import LEDGER_FILE
from leetcode_guard._ledger import CREDIT, SOURCE_LEETCODE
from leetcode_guard._ledger_io import load_ledger

if TYPE_CHECKING:
    from collections.abc import Sequence

    from leetcode_guard._ledger_io import Ledger

PROBLEMS: Final = {
    "missing-number": 268,
    "single-number-iii": 260,
    "majority-element": 169,
    "single-number-ii": 137,
}
NEEDED: Final = 3
MIN_DATES: Final = 2
RUNGS: Final = ("H0", "H1", "H2", "H3")
MAX_RUNG: Final = "H1"
BLOCKS_DIR: Final = Path.home() / ".claude" / "state" / "leetcode"
EXIT_OK: Final = 0
EXIT_UNMET: Final = 1
EXIT_CANNOT_CHECK: Final = 2
_LOG: Final = logging.getLogger(__name__)


@dataclass(frozen=True)
class Session:
    """One session file judged by the report's rules.

    ``started`` is the first ``req`` (an earlier Accepted does not count);
    ``problem`` is why the session does not qualify, ``None`` when it does.
    """

    day: date
    slug: str
    rung: str
    order: str
    started: datetime | None
    problem: str | None


def _req_before_code(events: list[dict[str, Any]]) -> str:
    """``y``/``n`` by the first ``code`` event, ``-`` without one (as the report)."""
    seen_req = False
    for event in events:
        if event.get("event") == "req":
            seen_req = True
        elif event.get("event") == "code":
            return "y" if seen_req else "n"
    return "-"


def _first_req(events: list[dict[str, Any]]) -> datetime | None:
    stamps = [str(e.get("ts")) for e in events if e.get("event") == "req"]
    try:
        return datetime.fromisoformat(stamps[0]) if stamps else None
    except ValueError:
        _LOG.warning("req ts %r unreadable, session not counted", stamps[0])
        return None


def judge(path: Path, day: date, slug: str) -> Session:
    """Apply the counting rules to one session file."""
    events = session_log.read(path)
    kinds = {str(e.get("event")) for e in events}
    seen = [
        RUNGS.index(e["rung"])
        for e in events
        if e.get("event") == "rung" and e.get("rung") in RUNGS
    ]
    rung = RUNGS[max(seen)] if seen else "-"
    order = _req_before_code(events)
    reasons = [
        ("retest" in kinds, "a cold re-test"),
        ("reveal" in kinds, "reveal typed"),
        (bool(seen) and max(seen) > RUNGS.index(MAX_RUNG), f"hint {rung} > {MAX_RUNG}"),
        (order == "n", "code before req:"),
        (order == "-", "no code logged"),
    ]
    problem = next((why for hit, why in reasons if hit), None)
    return Session(day, slug, rung, order, _first_req(events), problem)


def sessions(folder: Path, since: date) -> list[Session]:
    """Every session file of the four problems dated on or after `since`."""
    found = []
    for path in sorted(folder.glob("*.jsonl")):
        stem = path.stem
        slug = stem[len("YYYY-MM-DD-") :]
        try:
            day = date.fromisoformat(stem[: len("YYYY-MM-DD")])
        except ValueError:
            _LOG.warning("%s: no date in the name, skipped", path)
            continue
        if slug in PROBLEMS and day >= since:
            found.append(judge(path, day, slug))
    return found


def _local_time(epoch: str) -> datetime | None:
    try:
        return datetime.fromtimestamp(int(epoch), tz=UTC).astimezone()
    except ValueError, OverflowError, OSError:
        _LOG.warning("credit submitted_at %r unreadable, not counted", epoch)
        return None


def accepted(ledger: Ledger, since: date) -> dict[str, list[datetime]]:
    """Local times of trusted LeetCode credits for the four, on/after `since`."""
    days: dict[str, list[datetime]] = {}
    for entry in ledger.of_kind(CREDIT):
        slug = entry.detail.get("title_slug", "")
        if slug not in PROBLEMS or entry.detail.get("source") != SOURCE_LEETCODE:
            continue
        if not is_trusted(entry, integrity_ok=ledger.integrity_ok):
            continue
        day = _local_time(entry.detail.get("submitted_at", ""))
        if day is not None and day.date() >= since:
            days.setdefault(slug, []).append(day)
    return {slug: sorted(found) for slug, found in days.items()}


def hook_fires(folder: Path, since: date) -> list[Path]:
    """``.blocks`` files the Stop hook wrote on or after `since` (local)."""
    floor = datetime.combine(since, datetime.min.time()).astimezone().timestamp()
    return sorted(p for p in folder.glob("*.blocks") if p.stat().st_mtime >= floor)


def counted(
    found: list[Session], acs: dict[str, list[datetime]]
) -> dict[str, tuple[date, Session]]:
    """Per problem: the first Accepted after a qualifying session's ``req``."""
    result: dict[str, tuple[date, Session]] = {}
    for session in sorted(found, key=lambda s: s.day):
        if session.problem is not None or session.slug in result:
            continue
        start = session.started
        later = [t for t in acs.get(session.slug, []) if start and t >= start]
        if later:
            result[session.slug] = (later[0].date(), session)
    return result


def _report_problems(
    found: list[Session], good: dict[str, tuple[date, Session]]
) -> None:
    for slug, number in PROBLEMS.items():
        mine = [s for s in found if s.slug == slug]
        for s in mine:
            verdict = "ok" if s.problem is None else f"not counted: {s.problem}"
            head = f"  {number} session {s.day} rung {s.rung}"
            print(f"{head} req-before-code {s.order}: {verdict}")
        if slug in good:
            print(f"{number} {slug}: COUNTED, Accepted {good[slug][0]}")
        elif not mine:
            print(f"{number} {slug}: not counted: no coach session since --since")
        elif all(s.problem is not None for s in mine):
            print(f"{number} {slug}: not counted: no qualifying session")
        else:
            print(f"{number} {slug}: not counted: no Accepted on/after its session")


def _args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--since", type=date.fromisoformat, required=True)
    parser.add_argument("--sessions-dir", type=Path, default=None)
    parser.add_argument("--ledger", type=Path, default=LEDGER_FILE)
    parser.add_argument("--key-file", type=Path, default=None)
    parser.add_argument("--blocks-dir", type=Path, default=BLOCKS_DIR)
    return parser.parse_args(argv)


def main(argv: Sequence[str]) -> int:
    """Print per-problem evidence and the verdict; exit 0 only if item 2 holds."""
    args = _args(argv)
    if not args.ledger.is_file():
        print(f"CANNOT CHECK: no ledger at {args.ledger}")
        return EXIT_CANNOT_CHECK
    ledger = load_ledger(args.ledger, key_file=args.key_file)
    if not ledger.integrity_ok:
        print("CANNOT CHECK: HMAC key unreadable, no credit can be trusted")
        return EXIT_CANNOT_CHECK
    found = sessions(args.sessions_dir or session_log.sessions_dir(), args.since)
    good = counted(found, accepted(ledger, args.since))
    _report_problems(found, good)
    fires = hook_fires(args.blocks_dir, args.since)
    for path in fires:
        print(f"hook fired: {path}")
    print("note: Coach-tab leak bounces run in the relay and leave no .blocks")
    dates = sorted({day for day, _ in good.values()})
    checks = [
        (len(good) < NEEDED, f"{len(good)} of {NEEDED} distinct problems"),
        (len(dates) < MIN_DATES, f"{len(dates)} of {MIN_DATES} distinct dates"),
        (bool(fires), f"Stop hook fired {len(fires)}x since {args.since}"),
    ]
    failed = [why for hit, why in checks if hit]
    if failed:
        print("FAIL: " + "; ".join(failed))
        return EXIT_UNMET
    ranked = sorted(good.items(), key=lambda kv: kv[1][0])
    rows = ", ".join(f"{PROBLEMS[k]} {d} {s.rung} req-first" for k, (d, s) in ranked)
    print(f"PASS since {args.since}: {rows}; {len(dates)} dates; hook fired 0x")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
