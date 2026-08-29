"""The rest of the data the status view shows.

:mod:`leetcode_guard._status` answers "would the gate lock right now?".  This
module answers everything else a person actually wants when they open the
window: what have I solved, what have I spent, how much escape budget is left,
how stale are the caches, and is the timer even armed.

Everything here is read-only and offline. Nothing fetches, nothing writes.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import logging
from typing import TYPE_CHECKING, Final

from leetcode_guard._daycost import parse_day
from leetcode_guard._ledger import BOOTSTRAP, CHARGE, CREDIT, SEEN

if TYPE_CHECKING:
    from datetime import date
    from pathlib import Path

    from gatelock import EscapeTracker

    from leetcode_guard._ledger_io import Ledger

_logger: Final = logging.getLogger(__name__)

_SECONDS_PER_DAY: Final = 86_400


@dataclass(frozen=True)
class Solve:
    """One credited submission, for the "what have I done" list."""

    day: str
    title_slug: str
    lang: str
    entry_id: str


@dataclass(frozen=True)
class LedgerStats:
    """Everything the ledger file contains, counted."""

    total_entries: int
    credits_earned: int
    charges_spent: int
    seen_markers: int
    bootstrapped: bool
    solves_today: int
    solves_last_7_days: int
    recent_solves: tuple[Solve, ...]
    charged_days: tuple[str, ...]
    first_entry_day: str | None


def _credit_solves(ledger: Ledger) -> list[Solve]:
    """Every credited submission, newest first."""
    solves = [
        Solve(
            day=entry.day,
            title_slug=entry.detail.get("title_slug", "?"),
            lang=entry.detail.get("lang", ""),
            entry_id=entry.entry_id,
        )
        for entry in ledger.of_kind(CREDIT)
    ]
    solves.sort(key=lambda item: item.day, reverse=True)
    return solves


def gather_ledger_stats(ledger: Ledger, *, today: date, limit: int = 15) -> LedgerStats:
    """Summarise the ledger for display."""
    solves = _credit_solves(ledger)
    charges = ledger.of_kind(CHARGE)
    charged_days = tuple(sorted((entry.day for entry in charges), reverse=True))

    week_ago = today.toordinal() - 7
    in_week = 0
    today_count = 0
    for solve in solves:
        parsed = parse_day(solve.day)
        if parsed is None:
            continue
        if parsed == today:
            today_count += 1
        if parsed.toordinal() > week_ago:
            in_week += 1

    days = sorted(entry.day for entry in ledger.entries.values())
    return LedgerStats(
        total_entries=len(ledger.entries),
        credits_earned=sum(entry.amount for entry in ledger.of_kind(CREDIT)),
        charges_spent=sum(entry.amount for entry in charges),
        seen_markers=len(ledger.of_kind(SEEN)),
        bootstrapped=bool(ledger.of_kind(BOOTSTRAP)),
        solves_today=today_count,
        solves_last_7_days=in_week,
        recent_solves=tuple(solves[:limit]),
        charged_days=charged_days[:limit],
        first_entry_day=days[0] if days else None,
    )


@dataclass(frozen=True)
class BudgetStatus:
    """How much of a rolling escape budget is left."""

    label: str
    used_7: int
    used_30: int
    used_90: int
    limit_7: int
    limit_30: int
    limit_90: int
    exhausted: bool
    next_wait_seconds: int

    @property
    def summary(self) -> str:
        """One line, in the shape gatelock itself prints."""
        return (
            f"{self.label}: {self.used_7}/{self.limit_7} per 7d, "
            f"{self.used_30}/{self.limit_30} per 30d, "
            f"{self.used_90}/{self.limit_90} per 90d"
        )


def gather_budget(tracker: EscapeTracker, label: str) -> BudgetStatus:
    """Read one tracker's rolling usage."""
    policy = tracker.policy
    return BudgetStatus(
        label=label,
        used_7=tracker.count_in_window(7),
        used_30=tracker.count_in_window(30),
        used_90=tracker.count_in_window(90),
        limit_7=policy.budget_per_7_days,
        limit_30=policy.budget_per_30_days,
        limit_90=policy.budget_per_90_days,
        exhausted=tracker.is_budget_exhausted(),
        next_wait_seconds=tracker.compute_lockout_seconds(),
    )


@dataclass(frozen=True)
class CacheStatus:
    """How fresh an on-disk cache is."""

    name: str
    exists: bool
    entries: int
    age_days: float | None

    @property
    def summary(self) -> str:
        """One human line."""
        if not self.exists:
            return f"{self.name}: none"
        age = (
            "unknown age" if self.age_days is None else f"{self.age_days:.1f} days old"
        )
        return f"{self.name}: {self.entries} entries, {age}"


def _cache_age_days(fetched_at: object, *, now: float) -> float | None:
    """How old a ``fetched_at`` stamp is, in days."""
    if isinstance(fetched_at, bool) or not isinstance(fetched_at, (int, float)):
        return None
    return max(0.0, (now - float(fetched_at)) / _SECONDS_PER_DAY)


def gather_cache(path: Path, name: str, key: str, *, now: float) -> CacheStatus:
    """Inspect one JSON cache without parsing its rows.

    Deliberately shallow: this is a status panel, so a corrupt cache should
    show as "unreadable" rather than take the window down with it.
    """
    if not path.exists():
        return CacheStatus(name=name, exists=False, entries=0, age_days=None)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        _logger.warning("cache %s at %s is unreadable: %s", name, path, exc)
        return CacheStatus(name=name, exists=True, entries=0, age_days=None)
    if not isinstance(raw, dict):
        return CacheStatus(name=name, exists=True, entries=0, age_days=None)
    rows = raw.get(key)
    return CacheStatus(
        name=name,
        exists=True,
        entries=len(rows) if isinstance(rows, list) else 0,
        age_days=_cache_age_days(raw.get("fetched_at"), now=now),
    )
