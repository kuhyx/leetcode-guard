"""Difficulty-weighted credits: Easy 1, Medium 2, Hard 4 per accepted submission.

Decided by kuhy on 2026-11-02 and applied retroactively. The signed ledger rows
are untouched (every credit still says ``amount: 1``); the weight is derived at
read time from the problem's difficulty, the same way the balance and the debt
are derived, so re-pricing is a recompute and never a rewrite.

**The difficulty source must verify like a credit does.** ``compute_balance``
reads a per-slug difficulty row, so an editable ``{"two-sum": "Easy"}`` would let
``Easy -> Hard`` quadruple every credit -- the reason ``progress_cache.json`` is
display-only. Each row is therefore a signed :class:`LedgerEntry` of kind
``difficulty`` in its own file (:data:`DIFFICULTY_FILE`), trusted by the credit
rule (:func:`leetcode_guard._balance.is_trusted`). A missing, forged, foreign or
unrecognised row means **weight 1** (fail-safe low) and is counted, then logged
as ONE aggregated warning per balance computation, never one per slug.

``pool_cache.json`` and ``statements_cache.json`` are unsigned and are read only
by :mod:`leetcode_guard._difficulty_resolve` to *write* signed rows, never on
the weight path.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import logging
from typing import TYPE_CHECKING, Final

from leetcode_guard import _constants
from leetcode_guard._balance import is_trusted
from leetcode_guard._daycost import day_key, local_today
from leetcode_guard._ledger import CREDIT, LedgerEntry, sign
from leetcode_guard._ledger_io import Ledger, load_ledger
from leetcode_guard._progress import DIFFICULTY_WEIGHTS

if TYPE_CHECKING:
    from datetime import datetime
    from pathlib import Path

_logger: Final = logging.getLogger(__name__)

KIND: Final = "difficulty"


@dataclass
class WeightTable:
    """Trusted ``slug -> difficulty`` rows, and the slugs that had none."""

    levels: dict[str, str] = field(default_factory=dict)
    unknown: set[str] = field(default_factory=set)

    def level(self, slug: str) -> str | None:
        """The trusted difficulty of ``slug``, or ``None`` when unknown."""
        return self.levels.get(slug)

    def weight(self, slug: str) -> int:
        """Credits one accepted submission of ``slug`` is worth; unknown is 1."""
        level = self.levels.get(slug)
        if level is None:
            self.unknown.add(slug)
            return 1
        return DIFFICULTY_WEIGHTS[level]

    def warn_unknown(self) -> None:
        """One aggregated warning for every slug priced as Easy for lack of a row."""
        if self.unknown:
            _logger.warning(
                "%d solved problem(s) have no trusted difficulty row and count as "
                "Easy (1 credit): run `python3 -m leetcode_guard "
                "--backfill-difficulty`",
                len(self.unknown),
            )


def difficulty_row(
    slug: str,
    level: str,
    *,
    now: datetime,
    key_file: Path | None = None,
    source: str = "pool",
) -> LedgerEntry:
    """A signed fact: LeetCode labels ``slug`` as ``level``."""
    return sign(
        LedgerEntry(
            entry_id=f"{KIND}:{slug}",
            kind=KIND,
            day=day_key(local_today(now=now)),
            created_at=now.isoformat(),
            amount=0,
            detail={"title_slug": slug, "difficulty": level, "source": source},
        ),
        key_file=key_file,
    )


def trusted_levels(ledger: Ledger) -> dict[str, str]:
    """Rows that verify (the credit rule) and name a known difficulty."""
    levels: dict[str, str] = {}
    for entry in ledger.of_kind(KIND):
        slug = entry.detail.get("title_slug")
        level = entry.detail.get("difficulty")
        if (
            slug
            and level in DIFFICULTY_WEIGHTS
            and is_trusted(entry, integrity_ok=ledger.integrity_ok)
        ):
            levels[slug] = level
    return levels


def load_weights(*, key_file: Path | None = None) -> WeightTable:
    """The weight table from the signed cache. Never touches the network."""
    ledger = load_ledger(_constants.DIFFICULTY_FILE, key_file=key_file)
    return WeightTable(levels=trusted_levels(ledger))


def credited_slugs(ledger: Ledger) -> list[str]:
    """Every problem the ledger holds a credit for, sorted (stable backfill order)."""
    return sorted(
        {
            slug
            for entry in ledger.of_kind(CREDIT)
            if (slug := entry.detail.get("title_slug"))
        }
    )
