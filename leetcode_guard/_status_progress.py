"""The "Progress & projection" section of the status window.

Its own module because it is the one section with controls -- a price entry,
three goal entries, a date entry and a button -- and because
``_status_sections`` sits near the line cap. The arithmetic and the wording
live in ``_status_projection``, ``_projection_text`` and ``_scenario_text``;
this file only lays them out.

The entries' text survives a repaint: the window rebuilds every widget on
refresh, so the values are owned by the caller and handed back in through
:class:`ProjectionControls`, never read off a widget that no longer exists.
"""

from __future__ import annotations

from dataclasses import dataclass
import tkinter as tk
from typing import TYPE_CHECKING, Final

from gatelock import ButtonStyle, make_button

from leetcode_guard._progress import DIFFICULTIES
from leetcode_guard._projection_text import is_count_line
from leetcode_guard._status_projection import ProjectionInputs
from leetcode_guard._status_rows import section_heading as _heading
from leetcode_guard._status_rows import section_row as _row

if TYPE_CHECKING:
    from collections.abc import Callable

    from gatelock import LockConfig

    from leetcode_guard._status_projection import ProjectionReport

_MONO: Final = "monospace"
"""The count rows are column-aligned with spaces, so they need a fixed-pitch
face; every other line uses the type scale as-is."""

_DATE_WIDTH: Final = 12
"""``dd.mm.yyyy`` plus room to overtype."""

_COUNT_WIDTH: Final = 5
"""A price or a goal: four digits at most, plus the cursor."""

FETCHING_NOTE: Final = "Fetching today's solved counts from LeetCode..."


@dataclass(frozen=True)
class ProjectionControls:
    """What the section needs beyond the snapshot.

    Attributes:
        inputs: The entries' current values, owned by the window.
        report: The projection for those values, already computed.
        on_project: Called with the entries' text when "Project" is pressed.
        fetching: Whether a live fetch is in flight, so the section can say
            the counts shown are the cached ones for now.
    """

    inputs: ProjectionInputs
    report: ProjectionReport
    on_project: Callable[[ProjectionInputs], None]
    fetching: bool = False


def _lines(parent: tk.Misc, config: LockConfig, lines: list[str]) -> None:
    """Draw formatter output, count rows in monospace, the rest as captions."""
    for line in lines:
        if is_count_line(line):
            tk.Label(
                parent,
                text=line,
                font=config.font("caption", family=_MONO),
                fg=config.palette.fg,
                bg=config.palette.bg,
                anchor="w",
            ).pack(fill="x", padx=config.space("lg"))
        else:
            _row(parent, config, line, color=config.palette.muted, role="caption")


def _label(frame: tk.Misc, config: LockConfig, text: str) -> None:
    tk.Label(
        frame,
        text=text,
        font=config.font("label"),
        fg=config.palette.fg,
        bg=config.palette.bg,
    ).pack(side="left", padx=(0, config.space("sm")))


def _entry(frame: tk.Misc, config: LockConfig, text: str, width: int) -> tk.Entry:
    entry = tk.Entry(
        frame,
        width=width,
        bg=config.palette.field_bg,
        fg=config.palette.fg,
        insertbackground=config.palette.fg,
        font=config.font("label", family=_MONO),
    )
    entry.insert(0, text)
    entry.pack(side="left", padx=(0, config.space("sm")))
    return entry


def _input_frame(parent: tk.Misc, config: LockConfig) -> tk.Frame:
    frame = tk.Frame(parent, bg=config.palette.bg)
    frame.pack(fill="x", padx=config.space("lg"), pady=config.space("xs"))
    return frame


def _entry_row(
    parent: tk.Misc, config: LockConfig, controls: ProjectionControls
) -> None:
    """Price and the three goals on one line; the date and the button on the next.

    Two lines because Tk clips rather than wraps: on one line the button sat
    off the right edge at the window's minimum width. Reads the entries only
    inside ``submit``, at the moment they still exist.
    """
    inputs = controls.inputs
    first = _input_frame(parent, config)
    _label(first, config, "Tue-Thu price")
    price = _entry(first, config, inputs.price_text, _COUNT_WIDTH)
    _label(first, config, "goal")
    goals = {}
    for name in DIFFICULTIES:
        _label(first, config, name)
        goals[name] = _entry(
            first, config, inputs.goal_texts.get(name, ""), _COUNT_WIDTH
        )
    second = _input_frame(parent, config)
    _label(second, config, "by")
    target = _entry(second, config, inputs.target_text, _DATE_WIDTH)

    def submit(_event: object = None) -> None:
        controls.on_project(
            ProjectionInputs(
                target_text=target.get(),
                price_text=price.get(),
                goal_texts={name: entry.get() for name, entry in goals.items()},
            )
        )

    for entry in (price, *goals.values(), target):
        entry.bind("<Return>", submit)
    make_button(
        second, config, "Project", submit, ButtonStyle(variant="secondary")
    ).pack(side="left")


def section_progress(
    parent: tk.Misc, config: LockConfig, controls: ProjectionControls
) -> None:
    """Solved counts now, the date control, and the counts on that date."""
    _heading(parent, config, "Progress & projection")
    report = controls.report
    if controls.fetching:
        _row(
            parent, config, FETCHING_NOTE, color=config.palette.warning, role="caption"
        )
    _lines(parent, config, report.now_lines())
    _entry_row(parent, config, controls)
    if report.projection is None:
        # A date or price that could not be used: one line, in the colour
        # that says so.
        _row(parent, config, report.then_lines()[0], color=config.palette.danger)
        return
    _lines(parent, config, report.then_lines())
    if report.goal_problem is not None:
        _row(parent, config, report.goal_problem, color=config.palette.danger)
        return
    _lines(parent, config, report.goal_lines())
