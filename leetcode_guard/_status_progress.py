"""The "Progress & projection" section of the status window.

Its own module because it is the one section with controls -- a date entry and
a button -- and because ``_status_sections`` sits near the line cap. The
arithmetic and the wording live in ``_status_projection`` and
``_projection_text``; this file only lays them out.

The entry's text survives a repaint: the window rebuilds every widget on
refresh, so the value is owned by the caller and handed back in through
:class:`ProjectionControls`, never read off a widget that no longer exists.
"""

from __future__ import annotations

from dataclasses import dataclass
import tkinter as tk
from typing import TYPE_CHECKING, Final

from gatelock import ButtonStyle, make_button

from leetcode_guard._projection_text import is_count_line
from leetcode_guard._status_rows import section_heading as _heading
from leetcode_guard._status_rows import section_row as _row

if TYPE_CHECKING:
    from collections.abc import Callable

    from gatelock import LockConfig

    from leetcode_guard._status_projection import ProjectionReport

_MONO: Final = "monospace"
"""The count rows are column-aligned with spaces, so they need a fixed-pitch
face; every other line uses the type scale as-is."""

_ENTRY_WIDTH: Final = 12
"""``dd.mm.yyyy`` plus room to overtype."""

FETCHING_NOTE: Final = "Fetching today's solved counts from LeetCode..."


@dataclass(frozen=True)
class ProjectionControls:
    """What the section needs beyond the snapshot.

    Attributes:
        target_text: The entry's current value, owned by the window.
        report: The projection for that value, already computed.
        on_project: Called with the entry's text when "Project" is pressed.
        fetching: Whether a live fetch is in flight, so the section can say
            the counts shown are the cached ones for now.
    """

    target_text: str
    report: ProjectionReport
    on_project: Callable[[str], None]
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


def _entry_row(
    parent: tk.Misc, config: LockConfig, controls: ProjectionControls
) -> None:
    """The date entry and its button, on one line."""
    frame = tk.Frame(parent, bg=config.palette.bg)
    frame.pack(fill="x", padx=config.space("lg"), pady=config.space("xs"))
    tk.Label(
        frame,
        text="How many will I have solved by",
        font=config.font("label"),
        fg=config.palette.fg,
        bg=config.palette.bg,
    ).pack(side="left", padx=(0, config.space("sm")))
    entry = tk.Entry(
        frame,
        width=_ENTRY_WIDTH,
        bg=config.palette.field_bg,
        fg=config.palette.fg,
        insertbackground=config.palette.fg,
        font=config.font("label", family=_MONO),
    )
    entry.insert(0, controls.target_text)
    entry.pack(side="left", padx=(0, config.space("sm")))

    def submit(_event: object = None) -> None:
        controls.on_project(entry.get())

    entry.bind("<Return>", submit)
    make_button(
        frame, config, "Project", submit, ButtonStyle(variant="secondary")
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
        # A date that could not be used: one line, in the colour that says so.
        _row(parent, config, report.then_lines()[0], color=config.palette.danger)
        return
    _lines(parent, config, report.then_lines())
