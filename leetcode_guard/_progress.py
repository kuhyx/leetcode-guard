"""How many problems are solved, per difficulty, as LeetCode's profile says.

Fetched from the public profile query and mirrored to
:data:`~leetcode_guard._constants.PROGRESS_CACHE_FILE` so the status window can
show a number before -- or without -- a network round trip.

Three things are deliberate:

* **Three-valued, like every other probe here.** A fetch either yields a
  :class:`Progress` or ``None``; it never yields zeros. A wrong username, an
  expired-session-style null payload and a transport failure all look the same
  from the caller's side -- "could not check" -- and none of them may be
  rendered as ``0 / 4055 (0 %)``.
* **Display only.** Nothing that decides, charges or credits reads this file.
  The moment the gate consulted it, editing the JSON would be a bypass, which
  is the asymmetry ``_balance`` exists to protect.
* **A stale cache beats no cache**, and it says how stale it is. The window
  renders whatever is on disk first, labelled with its date, and replaces it
  when the live fetch lands.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import logging
from typing import TYPE_CHECKING, Any, Final

from leetcode_guard._atomic_json import write_json
from leetcode_guard._queries import PROGRESS_QUERY, progress_variables

if TYPE_CHECKING:
    from pathlib import Path

    from leetcode_guard._leetcode import PostFn

_logger: Final = logging.getLogger(__name__)

_VERSION: Final = 1

DIFFICULTIES: Final = ("Easy", "Medium", "Hard")
"""In the order the lock feeds them, which is also the order they are listed."""


@dataclass(frozen=True)
class Progress:
    """Solved and total counts, per difficulty and overall.

    Attributes:
        solved: ``{"Easy": n, "Medium": n, "Hard": n}``.
        total: Same keys; LeetCode's own denominator, premium problems
            included -- the number the profile page shows.
        fetched_at: Unix seconds of the fetch this came from.
    """

    solved: dict[str, int]
    total: dict[str, int]
    fetched_at: float

    @property
    def solved_all(self) -> int:
        """Distinct problems solved, all difficulties."""
        return sum(self.solved[name] for name in DIFFICULTIES)

    @property
    def total_all(self) -> int:
        """Every problem on the site, all difficulties."""
        return sum(self.total[name] for name in DIFFICULTIES)

    def remaining(self, difficulty: str) -> int:
        """How many of ``difficulty`` are still unsolved. Never negative."""
        return max(0, self.total[difficulty] - self.solved[difficulty])


def _counts_by_difficulty(rows: object) -> dict[str, int] | None:
    """Turn ``[{"difficulty": "Easy", "count": 3}, ...]`` into a dict.

    ``None`` if any of the three difficulties is missing or malformed: a
    partial answer would render as a wrong percentage, not a missing one.
    """
    if not isinstance(rows, list):
        return None
    counts: dict[str, int] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        name, count = row.get("difficulty"), row.get("count")
        if (
            name in DIFFICULTIES
            and isinstance(count, int)
            and not isinstance(count, bool)
        ):
            counts[name] = count
    if any(name not in counts for name in DIFFICULTIES):
        return None
    return counts


def parse_progress(data: object, *, fetched_at: float) -> Progress | None:
    """Read a :data:`~leetcode_guard._queries.PROGRESS_QUERY` payload.

    Args:
        data: The ``data`` object of the response.
        fetched_at: When it was fetched, in Unix seconds.

    Returns:
        The counts, or ``None`` when either half is unreadable. ``matchedUser``
        is ``null`` for an unknown handle while ``allQuestionsCount`` is still
        complete, and that combination is a failure, not "nothing solved".
    """
    if not isinstance(data, dict):
        return None
    total = _counts_by_difficulty(data.get("allQuestionsCount"))
    user = data.get("matchedUser")
    stats = user.get("submitStatsGlobal") if isinstance(user, dict) else None
    solved = _counts_by_difficulty(
        stats.get("acSubmissionNum") if isinstance(stats, dict) else None
    )
    if total is None or solved is None:
        return None
    return Progress(solved=solved, total=total, fetched_at=fetched_at)


def fetch_progress(post: PostFn, username: str, *, now: float) -> Progress | None:
    """Ask LeetCode for the profile counts. ``None`` on any failure, logged."""
    result = post(PROGRESS_QUERY, progress_variables(username))
    if not result.ok:
        _logger.warning(
            "could not fetch solve progress for %r: %s",
            username,
            result.transport_error or ", ".join(result.errors) or "null payload",
        )
        return None
    progress = parse_progress(result.data, fetched_at=now)
    if progress is None:
        _logger.warning("solve progress for %r came back unreadable", username)
    return progress


def write_progress_cache(path: Path, progress: Progress) -> bool:
    """Persist the counts atomically. Never raises -- this is a mirror."""
    payload: dict[str, Any] = {
        "version": _VERSION,
        "fetched_at": progress.fetched_at,
        "solved": progress.solved,
        "total": progress.total,
    }
    try:
        write_json(path, payload)
    except OSError as exc:
        _logger.warning("could not write progress cache to %s: %s", path, exc)
        return False
    return True


def read_progress_cache(path: Path) -> Progress | None:
    """Load the mirrored counts, or ``None`` if there is no usable file."""
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        _logger.warning("progress cache at %s is unreadable: %s", path, exc)
        return None
    if not isinstance(raw, dict) or raw.get("version") != _VERSION:
        _logger.warning(
            "progress cache at %s is not a version-%d object", path, _VERSION
        )
        return None
    fetched_at = raw.get("fetched_at")
    if isinstance(fetched_at, bool) or not isinstance(fetched_at, (int, float)):
        _logger.warning("progress cache at %s has no usable fetched_at", path)
        return None
    solved = _as_counts(raw.get("solved"))
    total = _as_counts(raw.get("total"))
    if solved is None or total is None:
        _logger.warning("progress cache at %s has malformed counts", path)
        return None
    return Progress(solved=solved, total=total, fetched_at=float(fetched_at))


def _as_counts(raw: object) -> dict[str, int] | None:
    """Validate a cached ``{"Easy": n, ...}`` mapping."""
    if not isinstance(raw, dict):
        return None
    counts: dict[str, int] = {}
    for name in DIFFICULTIES:
        value = raw.get(name)
        if isinstance(value, bool) or not isinstance(value, int):
            return None
        counts[name] = value
    return counts


def refresh_progress(
    post: PostFn, username: str, path: Path, *, now: float
) -> Progress | None:
    """Fetch and mirror; on failure fall back to whatever is already on disk.

    The fallback is what lets a status window opened offline still show a
    figure -- dated, so it is never mistaken for today's.
    """
    fresh = fetch_progress(post, username, now=now)
    if fresh is None:
        return read_progress_cache(path)
    write_progress_cache(path, fresh)
    return fresh
