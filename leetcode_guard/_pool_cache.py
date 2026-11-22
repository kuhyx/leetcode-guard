"""On-disk mirror of the problem pool.

This is what makes the lock usable with no network. The gate can fire on a dead
connection, and a lock screen offering nothing to solve is a lock screen with
no way out.

Writes are atomic (temp file then rename) so a crash mid-write leaves the
previous cache intact rather than a truncated one.

The file carries an HMAC (``hmac``, the shared key and the ledger's scheme) over
the rest of it, written only here, after a live fetch. :attr:`CachedPool.verified`
says whether it still matches. Display reads an unverified pool as before; the
theory phase decides only on a verified, complete one (``_phase_inputs``).
"""

from __future__ import annotations

from dataclasses import dataclass, field
import logging
from typing import TYPE_CHECKING, Any, Final

from gatelock.log_integrity import compute_entry_hmac, verify_entry_hmac

from leetcode_guard._atomic_json import write_json
from leetcode_guard._problem import Problem, parse_problem
from leetcode_guard._read_json import MISSING, read_json

if TYPE_CHECKING:
    from pathlib import Path

_logger: Final = logging.getLogger(__name__)

_VERSION: Final = 1

INCOMPLETE_RETRY_SECONDS: Final = 3_600
"""How long a pool cut short by a failed page stays fresh: the phase machine
holds while it is incomplete, so it is retried hourly, not weekly."""


@dataclass(frozen=True)
class CachedPool:
    """A previously fetched pool and when it was written."""

    problems: tuple[Problem, ...]
    fetched_at: float
    """Unix seconds. Wall clock, not monotonic: it has to survive a reboot."""
    complete: bool
    verified: bool = field(default=False, compare=False)
    """Whether the file's HMAC matched when read; never set by a writer."""

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

    def is_current(self, *, now: float, ttl: float, refreshable: bool) -> bool:
        """Whether a refresher may skip its fetch.

        With a network seam (``refreshable``) an unsigned or edited cache is
        stale however new its stamp says, so the next normal refresh rewrites it
        signed, and an incomplete one is retried after
        :data:`INCOMPLETE_RETRY_SECONDS`. Without one, plain freshness: display
        reads such a cache as it always did.
        """
        if not refreshable:
            return self.is_fresh(now=now, ttl=ttl)
        limit = ttl if self.complete else min(ttl, INCOMPLETE_RETRY_SECONDS)
        return self.verified and self.is_fresh(now=now, ttl=limit)


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


def write_cache(path: Path, pool: CachedPool, *, key_file: Path | None = None) -> bool:
    """Persist a pool atomically, signed when the HMAC key can be read.

    Returns:
        Whether the write succeeded. Never raises: a cache is an optimisation,
        and failing to save one must not take down the lock.
    """
    payload: dict[str, Any] = {
        "version": _VERSION,
        "fetched_at": pool.fetched_at,
        "complete": pool.complete,
        "problems": [_to_row(problem) for problem in pool.problems],
    }
    signature = compute_entry_hmac(payload, key_file=key_file)
    if signature is None:
        _logger.warning(
            "HMAC key unreadable: pool cache at %s is written unsigned", path
        )
    else:
        payload["hmac"] = signature
    try:
        write_json(path, payload)
    except OSError as exc:
        _logger.warning("could not write pool cache to %s: %s", path, exc)
        return False
    return True


def _read_object(path: Path) -> dict[str, Any] | None:
    """The cache file's top-level JSON object, or ``None`` with a WARNING."""
    raw = read_json(path, _logger, "pool cache at %s is unreadable: %s", path)
    if raw is MISSING:
        return None
    if not isinstance(raw, dict):
        _logger.warning("pool cache at %s is not a JSON object", path)
        return None
    return raw


def _schema_fault(raw: dict[str, Any]) -> str | None:
    """Why ``raw`` is not a usable pool, or ``None`` if it is."""
    if raw.get("version") != _VERSION:
        return f"has version {raw.get('version')!r}, expected {_VERSION} -- ignoring"
    fetched_at = raw.get("fetched_at")
    if isinstance(fetched_at, bool) or not isinstance(fetched_at, (int, float)):
        return "has no usable fetched_at"
    if not isinstance(raw.get("problems"), list):
        return "has no problems array"
    return None


def read_cache(path: Path, *, key_file: Path | None = None) -> CachedPool | None:
    """Load a previously written pool, or ``None`` if there isn't a usable one.

    ``verified`` is whether the signature matches ``key_file`` (default: the
    shared key); an unsigned or edited file still loads, unverified.

    Every corruption mode returns ``None`` with a WARNING rather than raising,
    for the same reason as :func:`write_cache`.
    """
    raw = _read_object(path)
    if raw is None:
        return None
    fault = _schema_fault(raw)
    if fault is not None:
        _logger.warning("pool cache at %s %s", path, fault)
        return None
    parsed = [parse_problem(row) for row in raw["problems"]]
    problems = tuple(problem for problem in parsed if problem is not None)
    return CachedPool(
        problems=problems,
        fetched_at=float(raw["fetched_at"]),
        complete=bool(raw.get("complete", False)),
        verified=verify_entry_hmac(raw, key_file=key_file),
    )
