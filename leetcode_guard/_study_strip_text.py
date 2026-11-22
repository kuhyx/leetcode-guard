"""What the study strip says, as glyphs and dot counts (no Tk here).

Split out of ``_study_strip.py`` for the 250-line cap. **No time**: kuhy asked
for time in exactly one place, and it is not the strip. The strip has no clock
and, as study mode has no deadline, no countdown either.
"""

from __future__ import annotations

from dataclasses import dataclass

from leetcode_guard import _glyphs as g


@dataclass
class StripText:
    """What the strip currently says."""

    needed: int
    """Credits still owed: one hollow dot each."""
    earned: int | None = None
    """Credits earned today: one filled dot each. ``None`` = could not be read,
    drawn as no filled dot, never as an invented one."""
    verifying: bool = False
    """The browser reported an Accepted verdict and LeetCode is being asked."""
    fast_path_down: bool = False
    """The browser doorbell is closed: a solve waits for the regular poll."""

    @property
    def title(self) -> str:
        """The heading; it is where a dead instant check is admitted.

        ``◉`` while the browser doorbell works, ``◉ ⊘`` (and the warning
        colour, :meth:`StudyStrip.tick`) once a solve must wait for the poll.
        """
        if self.fast_path_down:
            return f"{g.WATCHING} {g.NO_ENTRY}"
        return g.WATCHING

    @property
    def headline(self) -> str:
        """The accent line: ``✓ …`` while a verdict is checked, else absent.

        The dots never move on the browser's word alone; this line is the only
        thing a ring changes, and only for as long as the burst runs. Empty
        means the line is not drawn at all, so it leaves no gap.
        """
        return f"{g.SOLVED} …" if self.verifying else ""

    @property
    def paid(self) -> bool:
        """Nothing owed: the strip shows the solved check instead of dots."""
        return self.needed <= 0

    @property
    def filled(self) -> int:
        """Filled dots: credits earned today, none while paid or unreadable."""
        return 0 if self.paid else (self.earned or 0)

    @property
    def hollow(self) -> int:
        """Hollow dots: credits still owed."""
        return 0 if self.paid else self.needed
