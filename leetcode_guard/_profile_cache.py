"""The profile mirror, and when it is allowed to ask LeetCode again.

The snapshot is pushed every minute, but the profile is fetched at most every
:data:`PROFILE_TTL_SECONDS` -- or at once when the gate's credit count moved,
so a solve reaches the Profile tab within the minute. That limit protects the
gate, not the app: LeetCode answers a rate limit with the same HTTP 200 and
null payload as an expired session, so a fetch per push could make the
harvest's own probe report "could not check".

A failed refresh serves the dated mirror (the app shows its ``fetched_at``);
only a profile never fetched at all is ``None``. Display only, like
``progress_cache.json``: nothing that decides, charges or credits reads it.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any, Final, TypeIs

from leetcode_guard._atomic_json import write_json
from leetcode_guard._constants import DATA_DIR, PROGRESS_CACHE_FILE
from leetcode_guard._profile import Profile, parse_profile
from leetcode_guard._profile_query import PROFILE_QUERY, profile_variables
from leetcode_guard._progress import DIFFICULTIES, parse_progress, write_progress_cache
from leetcode_guard._settings import build_client

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from leetcode_guard._settings import Client

_logger: Final = logging.getLogger(__name__)

PROFILE_CACHE_FILE: Final = DATA_DIR / "profile_cache.json"
"""Here rather than in ``_constants``, which is at the line cap."""

PROFILE_TTL_SECONDS: Final = 15 * 60

_VERSION: Final = 1


def write_profile_cache(path: Path, profile: Profile) -> bool:
    """Persist one fetch atomically. Never raises -- this is a mirror."""
    payload: dict[str, Any] = {
        "version": _VERSION,
        "fetched_at": profile.fetched_at,
        "credits": profile.credit_count,
        "solved": profile.solved,
        "total": profile.total,
        "calendar": profile.calendar,
        "acceptance_rate": profile.acceptance_rate,
    }
    try:
        write_json(path, payload)
    except OSError as exc:
        _logger.warning("could not write profile cache to %s: %s", path, exc)
        return False
    return True


def _is_int(value: object) -> TypeIs[int]:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_number(value: object) -> TypeIs[int | float]:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _is_rate(value: object) -> TypeIs[float | None]:
    """A percentage as written: a float, or ``None`` for "no submissions"."""
    return value is None or isinstance(value, float)


def _counts(raw: object) -> dict[str, int] | None:
    if not isinstance(raw, dict) or not all(
        _is_int(raw.get(name)) for name in DIFFICULTIES
    ):
        return None
    return {name: raw[name] for name in DIFFICULTIES}


def _calendar(raw: object) -> tuple[bool, dict[str, int] | None]:
    """``(valid, calendar)``: ``None`` is a valid calendar, ``[]`` is not."""
    if raw is None:
        return True, None
    if not isinstance(raw, dict) or not all(_is_int(v) for v in raw.values()):
        return False, None
    return True, {str(day): count for day, count in raw.items()}


def _profile_from(raw: dict[str, Any]) -> Profile | None:
    fetched_at, credit_count, rate = (
        raw.get("fetched_at"),
        raw.get("credits"),
        raw.get("acceptance_rate"),
    )
    solved, total = _counts(raw.get("solved")), _counts(raw.get("total"))
    valid, calendar = _calendar(raw.get("calendar"))
    if not (_is_number(fetched_at) and _is_int(credit_count) and _is_rate(rate)):
        return None
    if solved is None or total is None or not valid:
        return None
    return Profile(
        solved=solved,
        total=total,
        calendar=calendar,
        acceptance_rate=rate,
        fetched_at=float(fetched_at),
        credit_count=credit_count,
    )


def read_profile_cache(path: Path) -> Profile | None:
    """Load the mirror, or ``None`` if there is no usable file."""
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        _logger.warning("profile cache at %s is unreadable: %s", path, exc)
        return None
    profile = (
        _profile_from(raw)
        if isinstance(raw, dict) and raw.get("version") == _VERSION
        else None
    )
    if profile is None:
        _logger.warning(
            "profile cache at %s is not a usable version-%d object", path, _VERSION
        )
    return profile


def _is_fresh(cached: Profile, *, now: float, credit_count: int) -> bool:
    age = now - cached.fetched_at
    return cached.credit_count == credit_count and 0 <= age < PROFILE_TTL_SECONDS


def refresh_profile(
    *,
    now: float,
    credit_count: int,
    build: Callable[[], Client] | None = None,
    cache_path: Path | None = None,
) -> Profile | None:
    """The profile to publish: the mirror if fresh, else one fetch.

    A successful fetch rewrites both mirrors -- this one and
    ``progress_cache.json``, which the same payload answers.
    """
    path = PROFILE_CACHE_FILE if cache_path is None else cache_path
    cached = read_profile_cache(path)
    if cached is not None and _is_fresh(cached, now=now, credit_count=credit_count):
        return cached
    client = (build_client if build is None else build)()
    result = client.post(PROFILE_QUERY, profile_variables(client.username))
    fresh = (
        parse_profile(result.data, fetched_at=now, credit_count=credit_count)
        if result.ok
        else None
    )
    progress = parse_progress(result.data, fetched_at=now)
    if fresh is None or progress is None:
        _logger.warning(
            "could not refresh the LeetCode profile for %r (%s); serving %s",
            client.username,
            result.transport_error or ", ".join(result.errors) or "unreadable payload",
            "nothing" if cached is None else "the dated mirror",
        )
        return cached
    write_profile_cache(path, fresh)
    write_progress_cache(PROGRESS_CACHE_FILE, progress)
    return fresh
