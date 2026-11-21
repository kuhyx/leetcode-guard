"""Helpers for the ``attempts:`` line tests (not collected as tests)."""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

from leetcode_guard import _attempt_line
from leetcode_guard._attempt_store import load
from leetcode_guard._ledger import CREDIT, LedgerEntry, sign
from leetcode_guard._ledger_entries import credit_entry
from leetcode_guard._ledger_io import Ledger, append, save_ledger
from leetcode_guard._pool_cache import CachedPool, write_cache
from leetcode_guard._submissions import AcSubmission
from leetcode_guard.tests._attempt_helpers import DAY, T0
from leetcode_guard.tests._ledger_fixtures import NOW
from leetcode_guard.tests.test_problem import make
from leetcode_guard.tests.test_theory import taught

if TYPE_CHECKING:
    from pathlib import Path

    from leetcode_guard._attempt_model import AttemptRecord
    from leetcode_guard._attempt_queries import RecentSubmission
BITS_TAUGHT = (taught("algo", "xor"), taught("algo", "masks"))
POOL = (
    make("bit-trick", topics=["bit"]),
    make("tree-walk", topics=["tree"]),
    make("plain-scan", topics=["array"]),
)


class Fetcher:
    """A scripted ``recentSubmissionList`` that counts its calls."""

    def __init__(self, answer: list[RecentSubmission] | None) -> None:
        self.answer = answer
        self.calls = 0

    def __call__(self) -> list[RecentSubmission] | None:
        self.calls += 1
        return self.answer


def line(
    key: Path,
    *,
    at: float = T0,
    fetcher: Fetcher | None = None,
) -> str:
    """One run at the fake clock ``at``; a missing fetcher must not be called."""
    return _attempt_line.attempts_line(
        clock=lambda: at,
        fetch=fetcher or Fetcher(None),
        key_file=key,
    )


def credit(sub_id: str, slug: str, at: float, key: Path, **detail: str) -> LedgerEntry:
    """A signed credit row; ``detail`` overrides or (as ``""``) keeps fields."""
    entry = credit_entry(
        AcSubmission(sub_id, slug, slug, int(at), "python3"),
        day=date(2026, 11, 21),
        now=NOW,
        key_file=key,
    )
    return sign(
        LedgerEntry(
            entry_id=detail.pop("entry_id", entry.entry_id),
            kind=detail.pop("kind", CREDIT),
            day=entry.day,
            created_at=entry.created_at,
            amount=1,
            detail={**entry.detail, **detail},
        ),
        key_file=key,
    )


def put_ledger(data_dir: Path, *entries: LedgerEntry) -> None:
    """Write a ledger holding ``entries``."""
    ledger = Ledger()
    append(ledger, list(entries))
    save_ledger(data_dir / "ledger.json", ledger)


def put_pool(data_dir: Path) -> None:
    """Cache the three-problem pool."""
    write_cache(
        data_dir / "pool_cache.json",
        CachedPool(problems=POOL, fetched_at=2**31, complete=True),
    )


def theory_of(slug: str, day: str = DAY) -> str | None:
    """The stored snapshot of one record."""
    found: AttemptRecord | None = load().get(f"{day}|{slug}")
    assert found is not None
    return found.theory_at_solve
