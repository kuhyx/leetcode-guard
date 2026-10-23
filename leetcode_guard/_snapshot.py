"""The status app's snapshot: schema v1 of TODO-status-app.md, as one dict.

**Display only, like** ``progress_cache.json``. The snapshot is assembled from
the same read paths the tkinter window uses and published for a read-only
app. Nothing that decides, charges or credits may read it -- the moment the
gate consulted it, editing the RTDB node would be a bypass.
``test_push_trigger.py`` walks the import graph of every deciding module to
hold that line.

**Unknown is** ``null``, **never** ``0``. A section that could not be read
(no profile fetch ever succeeded, the coach has never run, the solved counts
were never mirrored) is ``None``, and the app renders "unknown" for it.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Final

from leetcode_guard._daycost import CURRENT_BASE
from leetcode_guard._profile import streaks
from leetcode_guard._progress import DIFFICULTIES
from leetcode_guard._snapshot_projection import build_projections
from leetcode_guard._snapshot_status import status_section

if TYPE_CHECKING:
    from leetcode_guard._profile import Profile
    from leetcode_guard._progress import Progress
    from leetcode_guard._status_full import FullStatus

SCHEMA_VERSION: Final = 1


def _local_iso(seconds: float) -> str:
    """Unix seconds as a local ISO timestamp, the shape ``generated_at`` has."""
    return (
        datetime.fromtimestamp(seconds, tz=UTC)
        .astimezone()
        .isoformat(timespec="seconds")
    )


def progress_section(progress: Progress | None) -> dict[str, Any] | None:
    """Solved / total per difficulty, as last mirrored."""
    if progress is None:
        return None
    return {
        "solved": dict(progress.solved),
        "total": dict(progress.total),
        "solved_all": progress.solved_all,
        "total_all": progress.total_all,
        "fetched_at": _local_iso(progress.fetched_at),
    }


def profile_section(profile: Profile | None, *, now: datetime) -> dict[str, Any] | None:
    """The Profile tab. Streaks are counted at ``now``, in UTC like the calendar."""
    if profile is None:
        return None
    current = longest = None
    if profile.calendar is not None:
        current, longest = streaks(profile.calendar, now.astimezone(UTC).date())
    return {
        "difficulty": {
            name.lower(): [profile.solved[name], profile.total[name]]
            for name in DIFFICULTIES
        },
        "streak_current": current,
        "streak_longest": longest,
        "calendar": profile.calendar,
        "acceptance_rate": profile.acceptance_rate,
        "fetched_at": _local_iso(profile.fetched_at),
    }


def build_snapshot(
    full: FullStatus,
    *,
    progress: Progress | None,
    profile: Profile | None,
    coach: dict[str, Any] | None,
    now: datetime,
) -> dict[str, Any]:
    """Assemble the whole snapshot.

    Reads nothing beyond its arguments and the free/sick-day pools the
    projection consults.
    """
    return {
        "schema": SCHEMA_VERSION,
        "generated_at": now.astimezone().isoformat(timespec="seconds"),
        "status": status_section(full),
        "progress": progress_section(progress),
        "projection_price": CURRENT_BASE,
        "projections": build_projections(full.gate, progress),
        "profile": profile_section(profile, now=now),
        "coach": coach,
    }
