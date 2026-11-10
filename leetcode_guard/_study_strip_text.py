"""What the study strip says, as glyphs and a clock (no Tk here).

Split out of ``_study_strip.py`` for the 250-line cap. **No countdown**: the
elapsed time only counts up, because study mode has no deadline (see
``_study_strip``).
"""

from __future__ import annotations

from dataclasses import dataclass

from leetcode_guard import _glyphs as g


@dataclass
class StripText:
    """What the strip currently says."""

    elapsed_seconds: float
    needed: int
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
        """The accent line: the verdict being checked, else elapsed time.

        The count below never moves on the browser's word alone; this line is
        the only thing a ring changes, and only for as long as the burst runs.
        """
        if self.verifying:
            return f"{g.SOLVED} …"
        return self.elapsed

    @property
    def elapsed(self) -> str:
        """``MM:SS`` -- elapsed only, never a target."""
        return g.elapsed(self.elapsed_seconds)

    @property
    def owed(self) -> str:
        """One hollow circle per accepted submission still outstanding."""
        return g.dots(self.needed) or g.SOLVED
