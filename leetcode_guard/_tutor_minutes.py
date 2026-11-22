"""Signed tutor minutes: lesson minutes and review minutes (contract C1).

Both read the rows :func:`leetcode_guard._tutor_signed.signed_rows` verified and
share earned_time's tutor rules, copied so both readers pay the same minutes: a
positive-int ``minutes``, the local day of ``ended_at``, and an ``entry_id``
repeated by a replayed write pays once, at its smallest count.

* **Lesson minutes** (:func:`teaching_minutes`): rows with the unit's subject
  and one of its modules, inside the (since, until) window. A row tagged
  ``detail.activity == "review"`` is never one, or a review on the current
  unit would count twice.
* **Review minutes** (:func:`review_minutes`, kuhy 2026-11-22): rows tagged
  ``activity == "review"`` whose (subject, module) ANY curriculum unit maps,
  today, no window. The tutor's old review rows carry none of the three
  keys and pay nothing; each is backfilled by a re-signed twin with the same
  ``entry_id``, so a twin pays its minutes once.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Final

from leetcode_guard._tutor_signed import detail_of

if TYPE_CHECKING:
    from collections.abc import Callable, Collection
    from datetime import date

    from leetcode_guard._tutor_signed import ModuleKey, Row

REVIEW: Final = "review"
"""``detail.activity`` of a review-minute row; lesson rows have no such key."""

UNTIL_SLACK_S: Final = 2.0
"""Seconds a teaching row may end after C2's ``at`` and still count as before it.

The tutor stamps the module-state row after the credit row of the turn that
finished the module, so that turn normally ends at or before ``at``. The two
are separate writes; a reorder by a second must not drop the last turn.
``test_theory_last_turn.py`` pins it.
"""


def _minutes(detail: dict[str, object]) -> int | None:
    """``detail.minutes`` when it is a positive int (never a bool), else ``None``."""
    raw = detail.get("minutes")
    if isinstance(raw, bool) or not isinstance(raw, int) or raw < 1:
        return None
    return raw


def _ended_on(
    detail: dict[str, object], day: date, window: tuple[float | None, float | None]
) -> bool:
    """Whether ``detail.ended_at`` falls on local ``day``, inside (since, until)."""
    raw = detail.get("ended_at")
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        return False
    since, until = window
    if until is not None and raw > until + UNTIL_SLACK_S:
        return False
    if since is not None and raw < since:
        return False
    return datetime.fromtimestamp(raw).astimezone().date() == day


def _paid(
    rows: list[Row],
    qualifies: Callable[[dict[str, object]], bool],
    day: date,
    window: tuple[float | None, float | None] = (None, None),
) -> int:
    """Minutes of the credit rows ``qualifies`` accepts that ended on ``day``.

    A repeated ``entry_id`` pays once, at its smallest count, counted over the
    qualifying rows only: the untagged original of a twin is never one.
    """
    by_id: dict[object, int] = {}
    anonymous = 0
    for row in rows:
        detail = detail_of(row)
        minutes = _minutes(detail)
        if (
            row.get("kind") != "credit"
            or minutes is None
            or not qualifies(detail)
            or not _ended_on(detail, day, window)
        ):
            continue
        entry_id = row.get("entry_id")
        if entry_id is None:
            anonymous += minutes
        else:
            by_id[entry_id] = min(minutes, by_id.get(entry_id, minutes))
    return anonymous + sum(by_id.values())


def teaching_minutes(
    rows: list[Row],
    subject: str,
    modules: Collection[str],
    *,
    day: date,
    window: tuple[float | None, float | None] = (None, None),
) -> int:
    """Signed LESSON minutes on ``modules`` of ``subject`` that ended on ``day``.

    ``window`` is (``since``, ``until``) in unix seconds, ``None`` = open.
    ``until`` drops rows that ended later: the minutes taught before a unit's
    theory was done still pay once the machine is in SOLVE, the ones after it
    never do. ``since`` drops rows that ended before the unit's THEORY began
    (C3 ``theory_since``). A review-tagged row is skipped (see the module doc).
    """
    return _paid(
        rows,
        lambda d: (
            d.get("subject") == subject
            and d.get("module") in modules
            and d.get("activity") != REVIEW
        ),
        day,
        window,
    )


def review_minutes(rows: list[Row], mapped: Collection[ModuleKey], *, day: date) -> int:
    """Signed REVIEW minutes that ended on ``day`` on any card in ``mapped``."""

    def qualifies(detail: dict[str, object]) -> bool:
        subject, module = detail.get("subject"), detail.get("module")
        return (
            detail.get("activity") == REVIEW
            and isinstance(subject, str)
            and isinstance(module, str)
            and (subject, module) in mapped
        )

    return _paid(rows, qualifies, day)
