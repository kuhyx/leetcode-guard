"""The theory-first screens as data: which screen, its card or bar, how tall.

No Tk, like the rest of the view model. Everything here is derived from one
:class:`~leetcode_guard._phase_view.PhaseView` -- the rules side's verdict (SPEC
C5) -- so nothing on this path reads a file, decides a phase or mints a credit.

Three screens:

- ``theory``: a large card for the current unit leads, with the one button that
  opens the tutor on it. The unit's problems follow and Open still works: the
  lock must always offer a way to do what it demands (2026-08-05).
- ``solve``: a slim bar (check glyph, unit, solved / total) and the unit's
  problems. No theory control of any kind.
- ``none``: today's list exactly as before.

No words (textgate): glyphs, numbers, the unit id and problem titles, which are
data.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from leetcode_guard import _glyphs as g
from leetcode_guard._constants import PROBLEM_DISPLAY_LIMIT

if TYPE_CHECKING:
    from leetcode_guard._phase_view import Phase, PhaseView

PHASE_ROWS: Final = 5
"""Rows visible on a unit screen; the rest are reached by scrolling."""


@dataclass(frozen=True)
class TheoryCard:
    """The THEORY screen's lead action, ready to paint."""

    title: str
    """The pencil and the unit id."""
    ready_mark: str
    """:data:`~leetcode_guard._glyphs.NOT_READY` while no lessons exist, else ``""``."""
    counts: str
    """``taught / total`` cards, or the unknown mark for each unreadable count."""
    fraction: float | None
    """How full the bar is drawn; ``None`` draws it empty (unknown or no cards)."""
    rate: str
    """Today's taught minutes, then the minutes that buy one credit."""
    button: str
    """:data:`~leetcode_guard._glyphs.LEARN`, or the plan glyph while not ready."""
    route: str | None
    """The tutor route the button opens; ``None`` when there is no target."""


@dataclass(frozen=True)
class PhaseScreen:
    """Which screen the surface shows and what leads it."""

    phase: Phase = "none"
    unit: str = ""
    card: TheoryCard | None = None
    """THEORY only."""
    unit_bar: str = ""
    """SOLVE only: the unit and ``solved / total``; the view adds the check."""

    @property
    def unit_list(self) -> bool:
        """Whether the list is narrowed to one unit's problems."""
        return self.phase != "none" and bool(self.unit)

    @property
    def rows(self) -> int:
        """How many rows the viewport is tall."""
        return PHASE_ROWS if self.unit_list else PROBLEM_DISPLAY_LIMIT


NONE_SCREEN: Final = PhaseScreen()


def _count(value: int | None) -> str:
    return g.UNKNOWN if value is None else str(value)


def _fraction(taught: int | None, total: int | None) -> float | None:
    if taught is None or total is None or total <= 0:
        return None
    return min(1.0, max(0.0, taught / total))


def learn_route(view: PhaseView) -> str | None:
    """The tutor route the learn button opens (SPEC C4).

    Lessons ready: the next untaught card of the module. Not ready: the
    subject's plan screen, where the lessons get made.
    """
    if view.learn_target is None:
        return None
    subject, module = view.learn_target
    return f"/learn/{subject}/{module}" if view.lessons_ready else f"/plan/{subject}"


def _card(view: PhaseView) -> TheoryCard:
    minutes = view.minutes_per_credit
    return TheoryCard(
        title=f"{g.THEORY_PENDING}  {view.unit}",
        ready_mark="" if view.lessons_ready else g.NOT_READY,
        counts=f"{_count(view.cards_taught)} / {_count(view.cards_total)}",
        fraction=_fraction(view.cards_taught, view.cards_total),
        rate=(
            f"{view.theory_minutes_today}{g.MINUTES}{g.SEP}"
            f"{minutes}{g.MINUTES} {g.RATE} 1{g.CREDIT}"
        ),
        button=g.LEARN if view.lessons_ready else g.PLAN,
        route=learn_route(view),
    )


def build_phase_screen(view: PhaseView | None) -> PhaseScreen:
    """The screen for ``view``; ``None`` (no phase known) is today's list."""
    if view is None or view.phase == "none":
        return NONE_SCREEN
    if view.phase == "theory":
        return PhaseScreen(phase="theory", unit=view.unit, card=_card(view))
    return PhaseScreen(
        phase="solve",
        unit=view.unit,
        unit_bar=f"{view.unit}  {view.solved} / {view.total}",
    )
