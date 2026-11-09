"""The read-only status snapshot's shape, grouped by what each part answers.

Split out of ``_status`` so the snapshot is a handful of small records rather
than one 28-field bag: the gate's verdict, the ledger's balance and the
suggestion pool each come from a different source and are read together. The
MCP server still sees the original flat keys -- ``_status.snapshot_dict``
spreads these groups back out, key for key.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from leetcode_guard._debt import Debt


@dataclass(frozen=True)
class Suggestion:
    """One suggested problem, flattened for display and for MCP."""

    title: str
    difficulty: str
    ac_rate: float
    url: str


@dataclass(frozen=True)
class Verdict:
    """The gate's answer for today."""

    state: str
    locked: bool
    reason: str
    needed: int
    charged_today: bool


@dataclass(frozen=True)
class BalanceView:
    """The ledger's balance, and how much of the ledger could be trusted."""

    credits: int
    charged: int
    available: int
    integrity_ok: bool
    tampered: int
    discounted: int
    unparsable: int
    solves: dict[str, int] = field(default_factory=dict)
    """Counted submissions by difficulty plus ``unknown``; see ``Balance.solves``."""


@dataclass(frozen=True)
class PoolView:
    """Where the suggestions came from, and whether cookies filtered them."""

    auth_present: bool
    auth_note: str
    source: str
    notes: tuple[str, ...]
    suggestions: tuple[Suggestion, ...]


@dataclass(frozen=True)
class StatusSnapshot:
    """Everything the gate knows, without touching the network."""

    day: str
    weekday: str
    cost: int
    """Today's full price: the day plus any debt surcharge."""

    debt: Debt
    """The full missed-day position (owed, repaid, outstanding, missed days)."""

    surcharge: int
    """The part of ``cost`` that is debt repayment."""

    clock_trusted: bool
    verdict: Verdict
    balance: BalanceView
    pool: PoolView
