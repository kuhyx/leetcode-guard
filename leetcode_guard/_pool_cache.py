"""On-disk mirror of the problem pool.

This is what makes the lock usable with no network. The gate can fire on a dead
connection, and a lock screen offering nothing to solve is a lock screen with
no way out.

Writes are atomic (temp file then rename) so a crash mid-write leaves the
previous cache intact rather than a truncated one.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import logging
import os
from pathlib import Path
import tempfile
from typing import Any, Final

from leetcode_guard._problem import Problem, parse_problem

_logger: Final = logging.getLogger(__name__)

_VERSION: Final = 1


@dataclass(frozen=True)
class CachedPool:
    """A previously fetched pool and when it was written."""

    problems: tuple[Problem, ...]
    fetched_at: float
    """Unix seconds. Wall clock, not monotonic: it has to survive a reboot."""
    complete: bool

    def age_seconds(self, now: float) -> float:
        """How old this cache is.

        A negative age means the clock moved backwards; callers treat that as
        stale rather than as infinitely fresh.
        """
        return now - self.fetched_at

    def is_fresh(self, *, now: float, ttl: float) -> bool:
        """Whether the cache is still within its time-to-live."""
        age = self.age_seconds(now)
        return 0 <= age < ttl


def _to_row(problem: Problem) -> dict[str, Any]:
    """Serialise a problem in the same shape :func:`parse_problem` expects.

    Reusing the wire format means the cache has exactly one parser, so a cached
    pool and a live pool can never disagree about how a field is read.
    """
    return {
        "frontendQuestionId": problem.frontend_id,
        "title": problem.title,
        "titleSlug": problem.title_slug,
        "difficulty": problem.difficulty,
        "acRate": problem.ac_rate,
        "paidOnly": problem.paid_only,
        "status": problem.status,
        "topicTags": [{"slug": slug} for slug in problem.topics],
    }


def write_cache(path: Path, pool: CachedPool) -> bool:
    """Persist a pool atomically.

    Returns:
        Whether the write succeeded. Never raises: a cache is an optimisation,
        and failing to save one must not take down the lock.
    """
    payload = {
        "version": _VERSION,
        "fetched_at": pool.fetched_at,
        "complete": pool.complete,
        "problems": [_to_row(problem) for problem in pool.problems],
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=str(path.parent),
            prefix=path.name,
            suffix=".tmp",
            delete=False,
        ) as handle:
            json.dump(payload, handle)
            handle.flush()
            os.fsync(handle.fileno())
            temp_name = handle.name
        Path(temp_name).replace(path)
    except OSError as exc:
        _logger.warning("could not write pool cache to %s: %s", path, exc)
        return False
    return True


def read_cache(path: Path) -> CachedPool | None:
    """Load a previously written pool, or ``None`` if there isn't a usable one.

    Every corruption mode returns ``None`` with a WARNING rather than raising,
    for the same reason as :func:`write_cache`.
    """
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        _logger.warning("pool cache at %s is unreadable: %s", path, exc)
        return None
    if not isinstance(raw, dict):
        _logger.warning("pool cache at %s is not a JSON object", path)
        return None
    if raw.get("version") != _VERSION:
        _logger.warning(
            "pool cache at %s has version %r, expected %d -- ignoring",
            path,
            raw.get("version"),
            _VERSION,
        )
        return None
    fetched_at = raw.get("fetched_at")
    if isinstance(fetched_at, bool) or not isinstance(fetched_at, (int, float)):
        _logger.warning("pool cache at %s has no usable fetched_at", path)
        return None
    rows = raw.get("problems")
    if not isinstance(rows, list):
        _logger.warning("pool cache at %s has no problems array", path)
        return None
    parsed = [parse_problem(row) for row in rows]
    problems = tuple(problem for problem in parsed if problem is not None)
    return CachedPool(
        problems=problems,
        fetched_at=float(fetched_at),
        complete=bool(raw.get("complete", False)),
    )
