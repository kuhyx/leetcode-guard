"""Tests for the break-glass instructions.

These assert the exact command string. A typo there is a user stuck exactly as
they were on 2026-08-05, so it is worth an ugly literal.
"""

from __future__ import annotations

from gatelock import LockConfig

from leetcode_guard._breakglass import STOP_COMMAND, breakglass_lines

_PRODUCTION = LockConfig(mode="hard")
_DEMO = LockConfig(mode="hard", disable_vt=False, grab="local")


def test_the_stop_command_is_exactly_right():
    """Spelled out rather than built up, because this is the sentence a trapped
    user retypes into a terminal by hand."""
    assert STOP_COMMAND == "systemctl --user stop leetcode-guard.service"


def test_production_does_not_send_the_user_at_a_key_it_disabled():
    """The lock runs ``setxkbmap -option srvrkeys:none``, so Ctrl+Alt+F2 is
    dead. Offering it anyway burns the one attempt a frightened user has."""
    lines = breakglass_lines(_PRODUCTION)
    text = "\n".join(lines)

    assert "will not work" in text
    assert "Ctrl+Alt+F2" in text, "say the key is dead rather than omitting it"
    assert "Switch to a console" not in text


def test_demo_offers_the_console_route_because_vt_switching_still_works():
    lines = breakglass_lines(_DEMO)
    text = "\n".join(lines)

    assert "Ctrl+Alt+F2" in text
    assert "will not work" not in text


def test_both_modes_give_the_command_that_always_works():
    for config in (_PRODUCTION, _DEMO):
        assert STOP_COMMAND in breakglass_lines(config)


def test_production_warns_that_restoring_vt_clears_other_xkb_options():
    """``setxkbmap -option ""`` clears *all* options, not just this lock's. A
    user who runs it deserves to know their compose key goes with it."""
    text = "\n".join(breakglass_lines(_PRODUCTION))

    assert 'setxkbmap -option ""' in text
    assert "xkb option" in text


def test_every_line_is_non_empty_and_renderable():
    for config in (_PRODUCTION, _DEMO):
        lines = breakglass_lines(config)
        assert lines
        assert all(line.strip() for line in lines)
