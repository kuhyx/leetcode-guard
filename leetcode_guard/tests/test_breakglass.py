"""Tests for the break-glass instructions.

These assert the exact command string. A typo there is a user stuck exactly as
they were on 2026-08-05, so it is worth an ugly literal.
"""

from __future__ import annotations

from gatelock import GrabPolicy, LockConfig

from leetcode_guard import _glyphs as g
from leetcode_guard._breakglass import (
    CONSOLE_KEYS,
    DESKTOP_KEYS,
    RESTORE_VT_COMMAND,
    STOP_COMMAND,
    breakglass_lines,
)

_PRODUCTION = LockConfig(mode="hard")
_DEMO = LockConfig(mode="hard", grab=GrabPolicy(kind="local", disable_vt=False))


def test_the_stop_command_is_exactly_right():
    """Spelled out rather than built up, because this is the sentence a trapped
    user retypes into a terminal by hand."""
    assert STOP_COMMAND == "systemctl --user stop leetcode-guard.service"


def test_production_does_not_send_the_user_at_a_key_it_disabled():
    """The lock runs ``setxkbmap -option srvrkeys:none``, so Ctrl+Alt+F2 is
    dead. Offering it anyway burns the one attempt a frightened user has."""
    lines = breakglass_lines(_PRODUCTION)
    text = "\n".join(lines)

    assert f"{CONSOLE_KEYS} {g.NO_ENTRY}" in text, "mark the key dead, do not omit it"
    assert DESKTOP_KEYS not in text


def test_demo_offers_the_console_route_because_vt_switching_still_works():
    """Demo mode keeps VT switching, so it offers the Ctrl+Alt+F2 console route."""
    lines = breakglass_lines(_DEMO)
    text = "\n".join(lines)

    assert CONSOLE_KEYS in text
    assert g.NO_ENTRY not in text
    assert DESKTOP_KEYS in text


def test_both_modes_give_the_command_that_always_works():
    """Both production and demo list the always-working stop command."""
    for config in (_PRODUCTION, _DEMO):
        assert f"{g.PROMPT} {STOP_COMMAND}" in breakglass_lines(config)


def test_production_warns_that_restoring_vt_clears_other_xkb_options():
    """``setxkbmap -option ""`` clears *all* options, not just this lock's. A
    user who runs it deserves to know their compose key goes with it -- a
    warning mark beside the command, since a sentence is not allowed."""
    text = "\n".join(breakglass_lines(_PRODUCTION))

    assert f"{RESTORE_VT_COMMAND}  {g.BLIND}" in text


def test_every_line_is_non_empty_and_renderable():
    """Every break-glass line in both modes has visible text."""
    for config in (_PRODUCTION, _DEMO):
        lines = breakglass_lines(config)
        assert lines
        assert all(line.strip() for line in lines)
