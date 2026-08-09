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

if TYPE_CHECKING:
    from gatelock import LockConfig

STOP_COMMAND: Final = "systemctl --user stop leetcode-guard.service"
"""The route that always works, from any shell that can reach this user's
session. Asserted verbatim in the tests."""

_RESTORE_VT_COMMAND: Final = 'setxkbmap -option ""'


def breakglass_lines(config: LockConfig) -> tuple[str, ...]:
    """The recovery instructions for the lock as it is currently configured.

    Args:
        config: The live lock configuration. Read for ``resolved_disable_vt``,
            which decides whether a TTY switch is honestly on offer.

    Returns:
        Lines to render verbatim, in order.
    """
    if config.resolved_disable_vt():
        return (
            "Stuck? This lock has disabled VT switching, so Ctrl+Alt+F2 will not work.",
            "From a terminal that is already open, or over SSH from another machine:",
            STOP_COMMAND,
            f"({_RESTORE_VT_COMMAND} restores VT switching, but clears every "
            "other xkb option.)",
        )
    return (
        "Stuck? Switch to a console with Ctrl+Alt+F2 and run:",
        STOP_COMMAND,
        "Ctrl+Alt+F1 returns to the desktop.",
    )
