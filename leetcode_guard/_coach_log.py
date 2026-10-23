"""Read the coach's session logs for the status app's Coach tab.

The log is TODO-coach.md decision 8: one JSONL file per problem at
``~/.local/share/leetcode-coach/sessions/<date>-<slug>.jsonl``, events ``req``,
``req_check``, ``code``, ``rung``, ``reveal``, ``postmortem``, ``retest``, and
the app's ``session_start``, ``grade``, ``chat``, ``session_end``
(DOCS-coach-relay.md section 5; per-step grades in ``_coach_grades``). It
was being written in parallel with this reader, so **every field-name
assumption lives in the constants below** and nothing else guesses:

* each line is a JSON object whose ``event`` key names the event;
* ``req_check`` carries ``verdict``: ``pass`` / ``incomplete`` / ``unverified``;
* ``rung`` carries ``rung``: ``H0`` .. ``H3``;
* ``grade`` carries ``step`` (int 1-5) and ``grade`` (pass/partial/fail),
  ``chat`` a ``role`` (kuhy/coach), ``session_end`` a ``reason``;
* any event may carry ``cluster``; the first non-blank one wins.

Tolerant by contract: a JSON line that is not one of those shapes is skipped
and counted, with **one** warning per file per read -- the push runs every
minute, so a warning per line would bury the journal. A line that is not JSON
at all (a torn write) gets its own warning. ``retests_due``, ``clusters`` and
``how_to`` come from the coach itself (``_coach_view``, over
``leetcode_coach.progress`` and ``how_to``, decisions 10 and 12): deriving them
here would be a second copy of its rules. Any is ``None`` (unknown) if the
coach raises -- logged, never propagated, because this runs inside the
every-minute push. No session logs yet is not a failure: it exports empty
lists and every cluster at zero, so the Coach tab can say how to start.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import logging
from pathlib import Path
import re
from typing import TYPE_CHECKING, Any, Final

from leetcode_guard._coach_grades import grades
from leetcode_guard._coach_view import clusters_view, how_to_view, retests_view
from leetcode_guard._daycost import parse_day

if TYPE_CHECKING:
    from collections.abc import Callable

_logger: Final = logging.getLogger(__name__)

COACH_SESSIONS_DIR: Final = (
    Path.home() / ".local" / "share" / "leetcode-coach" / "sessions"
)

EVENT_KEY: Final = "event"
VERDICT_KEY: Final = "verdict"
RUNG_KEY: Final = "rung"
CLUSTER_KEY: Final = "cluster"

REQ: Final = "req"
REQ_CHECK: Final = "req_check"
CODE: Final = "code"
RUNG: Final = "rung"
REVEAL: Final = "reveal"
GRADE: Final = "grade"
CHAT: Final = "chat"
SESSION_END: Final = "session_end"
EVENTS: Final = frozenset(
    {
        *(REQ, REQ_CHECK, CODE, RUNG, REVEAL, "postmortem", "retest"),
        *("session_start", GRADE, CHAT, SESSION_END),
    }
)
VERDICTS: Final = frozenset({"pass", "incomplete", "unverified"})
RUNGS: Final = ("H0", "H1", "H2", "H3")
GRADES: Final = frozenset({"pass", "partial", "fail"})
STEPS: Final = range(1, 6)
ROLES: Final = frozenset({"kuhy", "coach"})
END_REASONS: Final = frozenset({"done", "reveal", "ended"})

_DATED_NAME: Final = re.compile(r"(?P<day>\d{4}-\d{2}-\d{2})-(?P<slug>.+)")
"""Pre-checked by shape so an undated name never logs a parse warning."""


@dataclass(frozen=True)
class CoachProblem:
    """One session file, summarised the way ``leetcode report`` reads it.

    ``req_before_code`` is ``None`` until there is a ``code`` event: before
    that the question has no answer yet.
    """

    slug: str
    cluster: str | None
    req_before_code: bool | None
    max_rung: str | None
    revealed: bool
    req_check: str | None
    day: str | None
    grades: dict[str, Any] | None = None
    accepted: bool | None = None


def _name_parts(stem: str) -> tuple[str, str | None]:
    """``2026-10-23-missing-number`` -> ``("missing-number", "2026-10-23")``."""
    match = _DATED_NAME.fullmatch(stem)
    if match is not None and parse_day(match["day"]) is not None:
        return match["slug"], match["day"]
    return stem, None


def _events(lines: list[str]) -> tuple[list[dict[str, Any]], int]:
    """The well-formed events, and how many JSON lines were not one."""
    events: list[dict[str, Any]] = []
    skipped = 0
    for number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except ValueError as exc:
            # Its own warning: a torn line is a writer that crashed mid-write,
            # worth more than a tally in the summary below.
            _logger.warning("coach session line %d is not JSON: %s", number, exc)
            continue
        if not _well_formed(event):
            skipped += 1
            continue
        events.append(event)
    return events, skipped


def _graded(event: dict[str, Any]) -> bool:
    step = event.get("step")
    whole = isinstance(step, int) and not isinstance(step, bool)
    return whole and step in STEPS and event.get(GRADE) in GRADES


_SHAPES: Final[dict[str, Callable[[dict[str, Any]], bool]]] = {
    REQ_CHECK: lambda e: e.get(VERDICT_KEY) in VERDICTS,
    RUNG: lambda e: e.get(RUNG_KEY) in RUNGS,
    GRADE: _graded,
    CHAT: lambda e: e.get("role") in ROLES,
    SESSION_END: lambda e: e.get("reason") in END_REASONS,
}
"""Each event that carries a fact the reader relies on, and its shape rule."""


def _well_formed(event: object) -> bool:
    if not isinstance(event, dict) or event.get(EVENT_KEY) not in EVENTS:
        return False
    shape = _SHAPES.get(event[EVENT_KEY])
    return shape is None or shape(event)


def _summarise(
    slug: str, day: str | None, events: list[dict[str, Any]]
) -> CoachProblem:
    seen_req = False
    req_before_code: bool | None = None
    rungs: list[int] = []
    verdict: str | None = None
    cluster: str | None = None
    for event in events:
        kind = event[EVENT_KEY]
        named = event.get(CLUSTER_KEY)
        if cluster is None and isinstance(named, str) and named.strip():
            cluster = named
        if kind == REQ:
            seen_req = True
        elif kind == CODE and req_before_code is None:
            req_before_code = seen_req
        elif kind == RUNG:
            rungs.append(RUNGS.index(event[RUNG_KEY]))
        elif kind == REQ_CHECK:
            verdict = event[VERDICT_KEY]
    by_step, accepted = grades(events)
    return CoachProblem(
        slug=slug,
        cluster=cluster,
        req_before_code=req_before_code,
        max_rung=RUNGS[max(rungs)] if rungs else None,
        revealed=any(event[EVENT_KEY] == REVEAL for event in events),
        req_check=verdict,
        day=day,
        grades=by_step,
        accepted=accepted,
    )


def read_session(path: Path) -> CoachProblem | None:
    """Summarise one session file, or ``None`` if it cannot be read."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as exc:
        _logger.warning("coach session %s is unreadable: %s", path, exc)
        return None
    events, skipped = _events(lines)
    if skipped:
        _logger.warning("coach session %s: skipped %d unknown lines", path, skipped)
    slug, day = _name_parts(path.stem)
    return _summarise(slug, day, events)


def read_coach(directory: Path | None = None) -> dict[str, Any] | None:
    """The Coach tab's data; ``None`` only when reading it failed.

    No sessions yet (the directory is missing or holds no logs) is a *known*
    state: no problems, no re-tests due, every cluster at zero. ``None`` means
    "could not be read" -- logged, never propagated, because this runs inside
    the every-minute push.
    """
    folder = COACH_SESSIONS_DIR if directory is None else directory
    try:
        problems = [
            problem
            for path in sorted(folder.glob("*.jsonl"))
            if (problem := read_session(path)) is not None
        ]
    except Exception:  # pylint: disable=broad-exception-caught
        _logger.exception("coach sessions in %s could not be read", folder)
        return None
    return {
        "problems": [asdict(problem) for problem in problems],
        "retests_due": _from_coach(retests_view, folder),
        "clusters": _from_coach(clusters_view, folder),
        "how_to": _from_coach(how_to_view, folder),
    }


def _from_coach(derive: Callable[[Path], object], folder: Path) -> object:
    """The coach's own derivation over ``folder``, or ``None`` if it raises."""
    try:
        return derive(folder)
    except Exception:  # pylint: disable=broad-exception-caught
        _logger.exception("coach derivation %r failed", derive)
        return None
