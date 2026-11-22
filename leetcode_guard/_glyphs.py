"""The lock's vocabulary: glyphs and numbers, no words (textgate, 2026-11-08).

Everything kuhy sees on the lock, the study strip and the tray tooltip is built
from these. Only Basic Multilingual Plane symbols with a *text* default
presentation are used: Tk 8.6 can crash on a colour-emoji font, so nothing
from U+1F300 upwards (the padlock is drawn on a canvas instead, ``_view_icons``).

Kept on purpose: numbers, ``%`` next to a number, clock times, problem titles
(LeetCode's content, not ours), URLs, and the break-glass command plus its key
chords -- those are typed, and settled decision 2 keeps what the user types.

No Tk here, so every surface's text is unit-testable without a window.
"""

from __future__ import annotations

from typing import Final

CREDIT: Final = "◆"
"""A banked credit; also the weight of a problem (Easy 1, Medium 2, Hard 4)."""
TODAY: Final = "☀"
"""What today costs."""
DEBT: Final = "▼"
"""Credits owed from missed days."""
OWED: Final = "○"
"""One accepted submission still needed, drawn once per solve."""
SOLVED: Final = "✓"
WATCHING: Final = "◉"
"""The poller can see LeetCode and is waiting for an Accepted."""
BLIND: Final = "⚠"
"""Something cannot be checked or went wrong; the detail is in the log."""
SICK: Final = "✚"
FOCUS: Final = "◎"
NOT_STARTED: Final = "◷"
CLOCK_BACK: Final = "◷↺"
"""The system clock moved backwards."""
SIGNED_OUT: Final = "⚿✗"
"""No usable LeetCode session: already-solved problems are not filtered."""
REFUSED: Final = "◆✗"
"""Ledger credits with a bad or foreign signature, not counted."""
UNSIGNED: Final = "◆⚠"
"""The ledger key is unreadable, so signatures are not checked."""
OFFLINE: Final = "⇅✗"
"""This machine cannot reach the network."""
SITE_DOWN: Final = "☁✗"
"""LeetCode is down while this machine is online."""
SITE_UP: Final = "☁✓"
OPEN: Final = "↗"
THEORY_PENDING: Final = "✎"
"""The tutor has not taught this problem's block yet (``_theory``)."""
ESCAPE: Final = "⎋"
LEARN: Final = "▶"
"""Start the current unit's lesson in the tutor (the theory card's button)."""
REWORK: Final = "?"
"""SOLVE row: open the tutor's rework chat about this problem."""
REVIEW: Final = "↻"
"""SOLVE while tutor cards are due: the one row that opens the review (``↻ 3``)."""
PLAN: Final = "☰"
"""Open the subject's plan: the unit's lessons are not generated yet."""
NOT_READY: Final = "◌"
"""The unit's lessons do not exist yet (a dotted, empty circle)."""
UNKNOWN: Final = "\u2013"
"""A count the tutor files could not answer; never shown as ``0``."""
RATE: Final = "→"
"""Minutes taught, the arrow, the one credit they buy."""
CLOSE: Final = "✕"
END_EVENING: Final = "☾"
"""End the evening chain (a crescent): the lock window's way out in ``--evening``."""
BACK: Final = "↩"
SUBMIT: Final = "✓"
CONSOLE: Final = "⌨"
PROMPT: Final = "▸"
RESTORE: Final = "↺"
NO_ENTRY: Final = "⊘"
ANY: Final = "\u2217"
"""Any problem (asterisk operator)."""
SEP: Final = "  │  "
TIMES: Final = "\u00d7"
"""Multiplication sign, for a count: ``○`` times 12."""
MINUTES: Final = "\u2032"
"""Prime, the minutes unit symbol after a number."""

DOT_CAP: Final = 8
"""Past this many, dots become one dot, :data:`TIMES` and the count: a debt
week can owe a dozen solves."""

_WEIGHT: Final = {"Easy": 1, "Medium": 2, "Hard": 4}


def dots(count: int, glyph: str = OWED) -> str:
    """``○○○`` for small counts, one dot and a count past :data:`DOT_CAP`."""
    if count <= 0:
        return ""
    if count > DOT_CAP:
        return f"{glyph}{TIMES}{count}"
    return glyph * count


def weight_mark(difficulty: str) -> str:
    """``◆``, ``◆◆`` or ``◆◆◆◆``: the credit an accepted submission is worth.

    The same scale ``_difficulty`` prices credits with, so the mark says both
    how hard the problem is and how much of the debt it pays.
    """
    return CREDIT * _WEIGHT.get(difficulty, 1)


def problem_mark(difficulty: str, ac_rate: float, *, waits: bool = False) -> str:
    """A row's mark: ``◆◆  48%``, led by the pencil while its theory waits."""
    mark = f"{weight_mark(difficulty)}  {ac_rate:.0f}%"
    return f"{THEORY_PENDING}  {mark}" if waits else mark
