"""What to do when the lock itself is the problem.

On 2026-08-05 the gate armed correctly, demanded a fresh accepted submission,
and left no route to make one: the problems were inert text, the package could
not open a browser, and the hatch was still ten minutes away. The user got out
only because a terminal happened to already be open. Had it not been, the
options were a hard reboot or nothing.

So the recovery route is printed on the surface, always, whatever else is
wrong. This is the one exit that does not depend on the rest of this package
being correct -- it costs a label, and it is what was missing that morning.

**The wording tracks what the lock actually did.** Production disables VT
switching, so telling a trapped user to press Ctrl+Alt+F2 would send them at a
key combination this very process has turned off. Advice that does not work is
worse than none: it burns the attempt a frightened user has, and it teaches
them the screen lies. :func:`breakglass_lines` therefore reads
``resolved_disable_vt`` and says which of the two routes is actually open.

No Tk here on purpose: every sentence is a plain string so it can be asserted
verbatim, and a typo in the command is a user stuck exactly as they were.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from leetcode_guard import _glyphs as g

if TYPE_CHECKING:
    from gatelock import LockConfig

STOP_COMMAND: Final = "systemctl --user stop leetcode-guard.service"
"""The route that always works, from any shell that can reach this user's
session. Asserted verbatim in the tests."""

RESTORE_VT_COMMAND: Final = 'setxkbmap -option ""'
"""Re-enables VT switching -- and clears every other xkb option with it."""

CONSOLE_KEYS: Final = "Ctrl+Alt+F2"
DESKTOP_KEYS: Final = "Ctrl+Alt+F1"


def breakglass_lines(config: LockConfig) -> tuple[str, ...]:
    """The recovery route for the lock as it is currently configured.

    No prose (textgate): the command and the key chords are what the user
    types, so they stay verbatim; everything around them is a glyph. A chord
    this process disabled is shown struck out (``⊘``) rather than omitted, so
    the user does not burn an attempt on it -- the honesty rule above.

    Args:
        config: The live lock configuration. Read for ``resolved_disable_vt``,
            which decides whether a TTY switch is honestly on offer.

    Returns:
        Lines to render verbatim, in order.
    """
    command = f"{g.PROMPT} {STOP_COMMAND}"
    if config.resolved_disable_vt():
        return (
            f"{g.CONSOLE} {CONSOLE_KEYS} {g.NO_ENTRY}",
            command,
            f"{g.RESTORE} {RESTORE_VT_COMMAND}  {g.BLIND}",
        )
    return (
        f"{g.CONSOLE} {CONSOLE_KEYS}",
        command,
        f"{g.BACK} {DESKTOP_KEYS}",
    )
