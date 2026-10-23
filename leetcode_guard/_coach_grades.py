"""The app's step grades for the Coach-tab history (DOCS-coach-relay.md 5).

The relay logs one ``grade`` event per graded try (``step`` 1-5, ``grade``
pass/partial/fail, ``forced``, ``via``). A file can hold several sessions,
each opened by a ``session_start``; the history shows the latest one. A
CLI-only file has no ``session_start`` and so no grades: ``None`` (unknown),
which the app shows as unknown, never as zero.

Step 4 is never graded by kuhy: its one ``grade`` is the relay noticing a
LeetCode Accepted, so it becomes ``accepted`` rather than a row.
"""

from __future__ import annotations

from typing import Any, Final

GRADE_STEPS: Final = {1: "constraint", 2: "requirements", 3: "toolbox", 5: "postmortem"}
ACCEPTED_STEP: Final = 4


def _row(events: list[dict[str, Any]]) -> dict[str, Any] | None:
    """The last grade of one step, how many tries it took, and any force."""
    if not events:
        return None
    # A force is its own event (kuhy chose to continue), not another try.
    tried = [e for e in events if e.get("forced") is not True] or events
    last = tried[-1]
    return {
        "grade": last["grade"],
        "attempts": sum(1 for e in events if e.get("forced") is not True),
        "forced": any(e.get("forced") is True for e in events),
        "via": last.get("via"),
    }


def grades(
    events: list[dict[str, Any]],
) -> tuple[dict[str, Any] | None, bool | None]:
    """``(grades by step name, accepted)`` of the latest app session.

    `events` must already be well-formed (``_coach_log._well_formed``).
    """
    starts = [i for i, e in enumerate(events) if e["event"] == "session_start"]
    if not starts:
        return None, None
    session = [e for e in events[starts[-1] :] if e["event"] == "grade"]
    rows = {
        name: _row([e for e in session if e["step"] == step])
        for step, name in GRADE_STEPS.items()
    }
    accepted = any(e["step"] == ACCEPTED_STEP and e["grade"] == "pass" for e in session)
    return rows, accepted
