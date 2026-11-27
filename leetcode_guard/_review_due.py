"""Review first: are tutor cards of the unit's modules due (contract C4).

The tutor writes ``review_due.json``, one signed row per (subject, module),
each listing the due time of every card in that module's queue
(``DOCS-contract-review-due.md``). This module is the reader rule of that
contract and nothing else: it counts, it does not decide anything.

Three answers, never a bool (``DueStatus``): cards due, nothing due, cannot
check. "Cannot check" is not "nothing due":

* a missing, unreadable or malformed file, an unreadable key, or ANY entry
  that is not a dict, fails its HMAC or makes the check raise makes the whole
  file "cannot check" (``signed_rows(strict=True)``): skipping a bad row could
  hide the row that carries the due cards;
* a module with no row is "cannot check" too: deleting a row cannot be told
  from never written;
* rows are typed and each module's winning row picked by ``_review_due_rows``
  (shared with the review-clear credit, which may not import this module).

Display-only on purpose (``test_display_only_imports.py``): the lock uses it to
choose which rows to show. Nothing that decides, charges or credits may import
it. The one decider that reads the same file is ``_review_clear`` (a cleared
review pays 1 credit, ``DOCS-review-clear.md``); it parses through
``_review_due_rows`` and can only mint, never cost a day. It reads only
signed rows; the tutor's unsigned files are never touched here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import logging
from typing import TYPE_CHECKING, Final

from leetcode_guard._review_due_rows import REVIEW_DUE, latest_due
from leetcode_guard._tutor_signed import signed_rows

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

    from leetcode_guard._tutor_signed import ModuleKey, Row

_logger: Final = logging.getLogger(__name__)


class DueStatus(Enum):
    """What the signed file says about the unit's modules."""

    DUE = "due"
    CLEAR = "clear"
    UNKNOWN = "unknown"
    """Cannot check: never to be read as :attr:`CLEAR`."""


@dataclass(frozen=True)
class DueRead:
    """One answer: the status, and for ``DUE`` the count and the module."""

    status: DueStatus
    count: int = 0
    """Cards due in :attr:`target`; 0 unless ``DUE``."""
    target: ModuleKey | None = None
    """The first module of the unit with a card due; ``None`` unless ``DUE``."""
    reason: str = field(default="", compare=False)
    """Why it cannot be checked (``UNKNOWN`` only); for the log, never compared."""


UNKNOWN: Final = DueRead(DueStatus.UNKNOWN)
CLEAR: Final = DueRead(DueStatus.CLEAR)


def decide_due(
    rows: Sequence[Row], targets: Sequence[ModuleKey], at_ms: int
) -> DueRead:
    """The answer for ``targets`` at ``at_ms`` over already verified ``rows``.

    The first target (the unit's module order) with a card due wins. With none
    due, one module the file has no row for makes it "cannot check".
    """
    latest = latest_due(rows)
    unseen = [target for target in targets if target not in latest]
    for target in targets:
        count = sum(t <= at_ms for t in latest.get(target, ()))
        if count:
            return DueRead(DueStatus.DUE, count, target)
    if unseen or not targets:
        return DueRead(DueStatus.UNKNOWN, reason=f"no row for {unseen or 'any module'}")
    return CLEAR


def check_due(
    targets: Sequence[ModuleKey],
    at_ms: int,
    *,
    key_file: Path | None = None,
) -> DueRead:
    """Read ``review_due.json`` and answer for ``targets`` at ``at_ms`` (Unix ms).

    Logs nothing: an ``UNKNOWN`` carries its ``reason`` for the one line
    :class:`ReviewWatch` writes. An unreadable, malformed or forged file is
    ``UNKNOWN``, never a raise.
    """
    reasons: list[str] = []
    rows = signed_rows(REVIEW_DUE, key_file=key_file, strict=True, reasons=reasons)
    if rows is None:
        return DueRead(DueStatus.UNKNOWN, reason="; ".join(reasons))
    return decide_due(rows, targets, at_ms)


class ReviewWatch:
    """One lock run's reads: ``UNKNOWN`` is logged once, then every tick is quiet.

    The lock reads on each poll, so a file that stays unreadable would
    otherwise log every 30 s. The reader itself logs nothing; the first
    "cannot check" of the run is one line carrying its reason (missing, forged
    row, ...); a raise the lock catches shares it (:meth:`first_warning`).
    """

    def __init__(self, *, key_file: Path | None = None) -> None:
        """Remember the key and that nothing has been warned yet."""
        self._key_file = key_file
        self._warned = False

    def first_warning(self) -> bool:
        """Whether this is the run's first warning about the file (and mark it)."""
        first, self._warned = not self._warned, True
        return first

    def read(self, targets: Sequence[ModuleKey], at_ms: int) -> DueRead:
        """The answer now; the first ``UNKNOWN`` of the run is logged."""
        answer = check_due(targets, at_ms, key_file=self._key_file)
        if answer.status is DueStatus.UNKNOWN and self.first_warning():
            _logger.warning(
                "review due (%s) cannot be checked for %s: %s; showing the solve rows",
                REVIEW_DUE,
                list(targets),
                answer.reason,
            )
        return answer
