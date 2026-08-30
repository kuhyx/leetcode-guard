"""Whether a LeetCode problem was solved today, for other programs to read.

Public on purpose: this is a cross-repo contract, like :mod:`status_view`.
``steam-backlog-enforcer`` grants an extra hour of gaming budget on a day with
a solve, and asks this question through the endpoint in
:mod:`leetcode_guard._web_server`.

Three things here are easy to get wrong and are pinned deliberately.

**Only ``credit`` entries count.** A ``seen`` entry is first-run seeding worth
zero, and a ``charge`` proves only that the day was *settled* -- which happens
from banked credit, from the escape hatch, and from a classified outage.
``detail["source"]`` does not discriminate those either, so a charge can never
stand in for a solve.

**The solve time is ``detail["submitted_at"]``, not ``day``.** ``day`` is
stamped from the *harvesting* run's today (``_ledger_entries.credit_entry``),
and harvesting only happens inside a lock window. A problem solved at 23:50 and
harvested at 09:00 the next morning carries the next day's ``day`` key.
``_status_extra.gather_ledger_stats`` counts ``day`` and inherits that skew;
this module deliberately does not.

**"Cannot check" is not "not solved".** An unreadable ledger, unparsable JSON
or an unusable integrity key all yield ``checked=False``, never a confident
``solved=False``. The caller fails closed either way, but only one of the two
is worth waking the user about.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time
import json
import logging
from typing import TYPE_CHECKING, Final

from gatelock.log_integrity import DEFAULT_HMAC_KEY_FILE, verify_entry_hmac

from leetcode_guard._constants import LEDGER_FILE
from leetcode_guard._daycost import local_now, local_today, parse_day
from leetcode_guard._ledger import CREDIT

if TYPE_CHECKING:
    from pathlib import Path

_logger: Final = logging.getLogger(__name__)


@dataclass(frozen=True)
class SolvedToday:
    """The answer, and whether it can be believed.

    Attributes:
        checked: Whether the ledger could be read and verified at all. When
            this is False every other field is meaningless -- it must never be
            collapsed into "nothing was solved".
        solved: Whether at least one accepted submission landed today.
        count: How many accepted submissions landed today.
        reason: A human-readable account, for logs and the status payload.
    """

    checked: bool
    solved: bool
    count: int
    reason: str


def _unchecked(reason: str) -> SolvedToday:
    """Build the "we could not look" answer.

    Args:
        reason: What stopped us looking.

    Returns:
        A :class:`SolvedToday` with ``checked`` false.
    """
    return SolvedToday(checked=False, solved=False, count=0, reason=reason)


def _read_entries(ledger_path: Path) -> list[object] | str:
    """Read the ledger's entry list, or describe why it could not be read.

    Args:
        ledger_path: The real ledger. Never the demo ledger, which is wiped and
            re-seeded on every demo run.

    Returns:
        The raw entry list, or a string explaining the failure.
    """
    try:
        raw = json.loads(ledger_path.read_text(encoding="utf-8"))
    except OSError as exc:
        _logger.warning("Cannot read the ledger at %s (%s)", ledger_path, exc)
        return f"cannot read the ledger at {ledger_path}: {exc}"
    except ValueError as exc:
        _logger.warning("Ledger at %s is not valid JSON (%s)", ledger_path, exc)
        return f"ledger at {ledger_path} is not valid JSON: {exc}"

    rows = raw.get("entries") if isinstance(raw, dict) else None
    if not isinstance(rows, list):
        _logger.warning("Ledger at %s has no entries array", ledger_path)
        return f"ledger at {ledger_path} has no entries array"
    return rows


def _landed_today(
    entry: dict[str, object],
    *,
    window: tuple[float, float],
    today_key: str,
) -> bool:
    """Whether this credit's accepted submission happened today, locally.

    Args:
        entry: One ledger entry, already known to be a verified credit.
        window: Local midnight and now, as unix seconds.
        today_key: Today's local ``YYYY-MM-DD``, used only by the fallback.

    Returns:
        Whether the solve falls inside today.
    """
    detail = entry.get("detail")
    raw = detail.get("submitted_at") if isinstance(detail, dict) else None
    if raw is not None:
        try:
            stamp = float(str(raw))
        except ValueError:
            _logger.warning(
                "Credit %r has an unparsable submitted_at (%r) -- falling back "
                "to its day key",
                entry.get("entry_id"),
                raw,
            )
        else:
            start, end = window
            return start <= stamp <= end

    # No usable submission time: fall back to the harvest day. That key is
    # skewed late but never early, so it can miss a late-night solve and can
    # never invent one.
    day = entry.get("day")
    return isinstance(day, str) and day == today_key and parse_day(day) is not None


def solved_today(
    *,
    now: datetime | None = None,
    ledger_path: Path | None = None,
    key_file: Path | None = None,
) -> SolvedToday:
    """Whether an accepted LeetCode submission landed today, locally.

    Args:
        now: Stand-in for the current local time, for tests.
        ledger_path: The real ledger file. None resolves ``LEDGER_FILE`` at
            call time -- never as a default argument, which would bind the real
            path at import and sail straight past the suite's path redirect.
        key_file: Where the shared HMAC key lives. None reads gatelock's
            default, which is what every locker signs with.

    Returns:
        The answer, with ``checked`` false whenever it could not be obtained.
    """
    target = LEDGER_FILE if ledger_path is None else ledger_path
    target_key = DEFAULT_HMAC_KEY_FILE if key_file is None else key_file
    if not _key_usable(target_key):
        return _unchecked(f"integrity key at {target_key} is unreadable")

    rows = _read_entries(target)
    if isinstance(rows, str):
        return _unchecked(rows)

    moment = local_now(now=now)
    midnight = datetime.combine(local_today(now=moment), time.min, moment.tzinfo)
    window_start = midnight.timestamp()
    window_end = moment.timestamp()
    today_key = local_today(now=moment).isoformat()

    count = 0
    forged = 0
    for row in rows:
        if not isinstance(row, dict) or row.get("kind") != CREDIT:
            continue
        if not verify_entry_hmac(row, key_file=target_key):
            forged += 1
            continue
        if _landed_today(row, window=(window_start, window_end), today_key=today_key):
            count += 1

    if forged:
        # Loud, but not fatal: a forged credit is simply not counted, exactly
        # as the balance table treats it.
        _logger.error(
            "%d ledger credit(s) failed their signature check and were ignored",
            forged,
        )

    plural = "" if count == 1 else "s"
    return SolvedToday(
        checked=True,
        solved=count > 0,
        count=count,
        reason=(
            f"{count} accepted submission{plural} today"
            if count
            else "no accepted submission recorded today"
        ),
    )


def _key_usable(key_file: Path) -> bool:
    """Whether the shared HMAC key can be read.

    Args:
        key_file: The key path to probe.

    Returns:
        Whether it is readable. Unreadable means credits cannot be verified,
        and an unverified credit is worth an hour of gaming budget -- so this
        is a "cannot check", not a "nothing solved".
    """
    try:
        return bool(key_file.read_bytes().strip())
    except OSError as exc:
        _logger.warning("Cannot read the integrity key at %s (%s)", key_file, exc)
        return False
