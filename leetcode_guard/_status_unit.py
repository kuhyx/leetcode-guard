"""The current unit and phase for the read-only surfaces (stage 4, part F).

``--status``, the MCP server, the status snapshot and ``open_cli`` all read the
unit through :func:`gather_unit`: the lock's own view
(``_unit_view.read_unit``) plus today's theory credits from the guard ledger.
Nothing here polls, mints or writes ``theory_phase.json``; that stays
``_theory_credit.poll_theory``'s job.

"Cannot check" is never zero. The lock shows held or unreadable counts as 0;
here a held phase (``source == "held"``) has unknown solved/total, unknown
minutes are ``None``, and nothing readable at all is ``unknown``, never "every
unit is finished".

**Display-only**: it imports ``_unit_view``, which reads the tutor's unsigned
files, so nothing that decides, charges or credits may import this module
(``test_display_only_imports.py`` checks the closure).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from leetcode_guard._balance import is_trusted
from leetcode_guard._daycost import day_key
from leetcode_guard._ledger import CREDIT
from leetcode_guard._theory_credit import SOURCE_THEORY
from leetcode_guard._unit_view import read_unit
from leetcode_guard._viewmodel_phase import learn_route

if TYPE_CHECKING:
    from datetime import date
    from pathlib import Path

    from leetcode_guard._ledger_io import Ledger
    from leetcode_guard._phase_view import PhaseView
    from leetcode_guard._unit_view import Source


@dataclass(frozen=True)
class UnitStatus:
    """The lock's unit view, where it came from, and today's theory credits."""

    view: PhaseView
    source: Source
    minutes: int | None
    """Today's paying theory minutes; ``None`` = cannot check."""
    credits_today: int
    """Trusted ``theory:<today>:<n>`` credits in the guard ledger."""
    credits_total: int
    """What every trusted theory credit is worth (each prices at its amount)."""


def gather_unit(
    ledger: Ledger, ledger_path: Path, *, day: date, key_file: Path | None = None
) -> UnitStatus:
    """Read the unit for ``day``; ``ledger`` is the caller's loaded guard ledger."""
    read = read_unit(ledger_path, day=day, key_file=key_file)
    today, total = theory_credits(ledger, day=day)
    return UnitStatus(
        view=read.view,
        source=read.source,
        minutes=read.minutes,
        credits_today=today,
        credits_total=total,
    )


def theory_credits(ledger: Ledger, *, day: date) -> tuple[int, int]:
    """(today's count, all-time value) of the trusted theory credits."""
    prefix = f"theory:{day_key(day)}:"
    trusted = [
        entry
        for entry in ledger.entries.values()
        if entry.kind == CREDIT
        and entry.detail.get("source") == SOURCE_THEORY
        and is_trusted(entry, integrity_ok=ledger.integrity_ok)
    ]
    today = sum(1 for entry in trusted if entry.entry_id.startswith(prefix))
    return today, sum(entry.amount for entry in trusted)


def leads_with(status: UnitStatus) -> str:
    """What the lock's first action is: ``theory`` or ``problems``."""
    return "theory" if status.view.phase == "theory" else "problems"


def unit_dict(status: UnitStatus) -> dict[str, Any]:
    """Plain data for the snapshot and the MCP; ``None`` = unknown. No prose."""
    view, live = status.view, status.source == "live"
    return {
        "unit": view.unit,
        "phase": view.phase,
        "source": status.source,
        "leads_with": leads_with(status),
        "solved": view.solved if live else None,
        "total": view.total if live else None,
        "theory_minutes_today": status.minutes,
        "minutes_per_credit": view.minutes_per_credit,
        "theory_credits_today": status.credits_today,
        "cards_taught": view.cards_taught,
        "cards_total": view.cards_total,
        "lessons_ready": view.lessons_ready,
        "learn_target": None if view.learn_target is None else list(view.learn_target),
        "learn_route": learn_route(view),
    }


def _known(value: int | None) -> str:
    return "unknown" if value is None else str(value)


def unit_lines(status: UnitStatus) -> list[str]:
    """The ``--status`` lines (a terminal: words are free)."""
    view = status.view
    if status.source == "unknown":
        head = "unit       unknown -- could not check, and no signed phase to hold"
    elif view.phase == "none":
        head = "unit       none -- every unit is finished"
    elif status.source == "held":
        head = f"unit       {view.unit} -- {view.phase} (held: could not check), "
        head += "unknown Easy solved"
    else:
        head = f"unit       {view.unit} -- {view.phase}, "
        head += f"{view.solved} / {view.total} Easy solved"
    lines = [
        head,
        f"theory     {_known(status.minutes)} min today, "
        f"{view.minutes_per_credit} min = 1 credit, "
        f"{status.credits_today} credits minted today",
    ]
    if (route := learn_route(view)) is not None:
        lines.append(f"learn      tutor --route {route}")
    return lines


def lead_reason(status: UnitStatus) -> str:
    """Why the lock leads with theory or with problems (MCP: an agent reads it)."""
    view = status.view
    held = (
        "could not check the inputs, so this holds the last signed phase: "
        if status.source == "held"
        else ""
    )
    if status.source == "unknown":
        return (
            "could not check the inputs and no signed phase is readable: the lock "
            "shows today's problem list as before stage 4"
        )
    if view.phase == "none":
        return "every unit is finished: the lock shows today's problem list"
    if view.phase == "theory":
        return (
            f"{held}unit {view.unit}: its theory is not done, so the lock leads with "
            f"the tutor ({learn_route(view)}); teaching minutes on it pay 1 credit "
            f"per {view.minutes_per_credit}, and its problems are listed below "
            "and still pay"
        )
    left = "unknown" if held else f"{view.total - view.solved} of {view.total}"
    return (
        f"{held}unit {view.unit}: its theory is done and {left} Easy problems are "
        "unsolved, so the lock leads with them; no theory is offered or paid "
        "until they are solved"
    )
