"""Timer health, read from systemd.

Split out of ``_status_extra.py`` for the 250-line cap: it is the one part of
the status snapshot that shells out, and the only one whose answer comes from
outside this process.
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
import subprocess
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from collections.abc import Callable


_logger: Final = logging.getLogger(__name__)


_TIMER_UNIT: Final = "leetcode-guard.timer"
_NEXT_ELAPSE: Final = "NextElapseUSecRealtime"
_SYSTEMCTL_TIMEOUT: Final = 5.0


@dataclass(frozen=True)
class TimerStatus:
    """Whether systemd will actually fire the gate."""

    enabled: bool
    next_fire: str
    detail: str


def gather_timer(
    *, run: Callable[[list[str]], str | None] | None = None
) -> TimerStatus:
    """Ask systemd whether the timer is armed and when it next fires.

    Shelling out rather than importing anything: the timer is a *user* unit and
    ``systemctl --user`` is the only honest source. Any failure degrades to
    "unknown" -- a status panel must never be the thing that breaks.
    """
    runner = run if run is not None else _run_systemctl
    enabled = runner(["is-enabled", _TIMER_UNIT])
    shown = runner(["show", _TIMER_UNIT, "-p", _NEXT_ELAPSE])
    if shown is None or enabled is None:
        return TimerStatus(
            enabled=False, next_fire="unknown", detail="systemctl unavailable"
        )
    # `show -p` returns "NextElapseUSecRealtime=Tue 2026-07-28 09:00:00 CEST",
    # already formatted. Parsing `list-timers` instead means splitting a
    # column-aligned table, which is how the first version ended up printing
    # the whole row -- unit names and all -- as the next fire time.
    _, _, value = shown.strip().partition("=")
    return TimerStatus(
        enabled=enabled.strip() == "enabled",
        next_fire=value.strip() or "not scheduled",
        detail=enabled.strip() or "unknown",
    )


def _run_systemctl(args: list[str]) -> str | None:
    """Run ``systemctl --user`` and return stdout, or ``None`` on any failure."""
    try:
        result = subprocess.run(
            ["/usr/bin/systemctl", "--user", *args],
            capture_output=True,
            text=True,
            timeout=_SYSTEMCTL_TIMEOUT,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        _logger.warning("could not query systemd: %s", exc)
        return None
    return result.stdout
