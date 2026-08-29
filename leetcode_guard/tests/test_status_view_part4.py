"""Continued from :mod:`leetcode_guard.tests.test_status_view_part3`, split for the 250-line cap."""

from __future__ import annotations

from typing import TYPE_CHECKING

from leetcode_guard import status_view
from leetcode_guard._status_full import explain_not_triggered
from leetcode_guard._status_sections import render_sections

if TYPE_CHECKING:
    from pathlib import Path

from leetcode_guard.tests.test_status_view_part3 import (
    a_root,
    full_for,
)


def test_the_canvas_window_tracks_the_canvas_width(
    data_dir: Path, hmac_key: Path, tk_mock
):
    """Without this the inner frame keeps its natural width and the panel
    never actually fills the window."""
    status_view.StatusWindow(
        a_root(tk_mock),
        full_for(data_dir, hmac_key),
        on_refresh=lambda: None,
        on_close=lambda: None,
    )
    canvas = tk_mock.Canvas.return_value
    configure_cb = next(
        call.args[1]
        for call in canvas.bind.call_args_list
        if call.args[0] == "<Configure>"
    )

    event = tk_mock.Event()
    event.width = 777
    configure_cb(event)

    canvas.itemconfigure.assert_called()


def test_main_opens_a_window_and_wires_every_exit(monkeypatch, data_dir: Path, tk_mock):
    """Close button, Escape, and the WM close box -- all three, every time."""
    root = a_root(tk_mock)
    monkeypatch.setattr(status_view.tk, "Tk", lambda: root)

    assert status_view.main([]) == 0

    root.mainloop.assert_called_once()
    protocols = [call.args[0] for call in root.protocol.call_args_list]
    binds = [call.args[0] for call in root.bind.call_args_list]
    assert "WM_DELETE_WINDOW" in protocols
    assert "<Escape>" in binds
    # And each wired callback actually destroys the window.
    for call in root.protocol.call_args_list:
        call.args[1]()
    root.destroy.assert_called()


def test_run_systemctl_reports_failure_as_none(monkeypatch, caplog):
    import logging

    from leetcode_guard import _status_extra

    def explode(*_args, **_kwargs):
        message = "no systemctl"
        raise OSError(message)

    monkeypatch.setattr(_status_extra.subprocess, "run", explode)

    with caplog.at_level(logging.WARNING):
        assert _status_extra._run_systemctl(["is-enabled", "x.timer"]) is None

    assert any("could not query systemd" in r.message for r in caplog.records)


def test_run_systemctl_returns_stdout(monkeypatch):
    from types import SimpleNamespace

    from leetcode_guard import _status_extra

    monkeypatch.setattr(
        _status_extra.subprocess,
        "run",
        lambda *a, **k: SimpleNamespace(stdout="enabled\n"),
    )

    assert _status_extra._run_systemctl(["is-enabled", "x.timer"]) == "enabled\n"


def test_the_refresh_callback_rerenders(monkeypatch, data_dir: Path, tk_mock):
    """The Refresh button is wired to a real re-read, not a no-op."""
    root = a_root(tk_mock)
    monkeypatch.setattr(status_view.tk, "Tk", lambda: root)
    calls: list[int] = []
    real = status_view.StatusWindow.render

    def counting_render(self, snapshot):
        calls.append(1)
        real(self, snapshot)

    monkeypatch.setattr(status_view.StatusWindow, "render", counting_render)

    status_view.main([])
    button_commands = [
        call.kwargs["command"]
        for call in tk_mock.Button.call_args_list
        if "command" in call.kwargs
    ]
    before = len(calls)
    button_commands[0]()  # Refresh

    assert len(calls) > before


def test_the_verdict_is_amber_with_nothing_banked(data_dir: Path, hmac_key: Path):
    from leetcode_guard._status_sections import _verdict_color

    colors = status_view._COLORS
    full = full_for(data_dir, hmac_key)
    gate = type(full.gate)(**{**vars(full.gate), "locked": False, "available": 0})
    combined = type(full)(**{**vars(full), "gate": gate})

    assert _verdict_color(colors, combined) == colors.warning


def test_an_empty_explanation_still_renders_a_line(
    data_dir: Path, hmac_key: Path, tk_mock
):
    """A blank "why" section would read as a rendering failure."""
    from leetcode_guard import _status_sections

    tk_mock.reset_mock()
    _status_sections.explain_not_triggered = lambda _full: []
    try:
        render_sections(
            tk_mock.Frame(), status_view._COLORS, full_for(data_dir, hmac_key)
        )
    finally:
        from leetcode_guard._status_full import explain_not_triggered as real

        _status_sections.explain_not_triggered = real

    captions = [str(c.kwargs.get("text", "")) for c in tk_mock.Label.call_args_list]
    assert any("No blocking condition recorded" in c for c in captions)


def test_the_not_in_force_line_suppresses_the_duplicate_reason(
    data_dir: Path, hmac_key: Path
):
    """Both would otherwise say "does not start until", reading as two causes."""
    full = full_for(data_dir, hmac_key)
    gate = type(full.gate)(
        **{**vars(full.gate), "state": "not-started", "locked": False, "reason": "dupe"}
    )
    combined = type(full)(**{**vars(full), "gate": gate, "in_force": False})

    reasons = explain_not_triggered(combined)

    assert "dupe" not in reasons
    assert any("not in force" in line for line in reasons)


def test_an_enabled_timer_adds_no_line(data_dir: Path, hmac_key: Path):
    """The counterpart to the disabled-timer test.

    Without this, the enabled branch was covered only because the developer
    machine happened to have the timer installed -- ambient state, not a test.
    CI has no systemd user timer, so it caught the gap on its first run.
    """
    full = full_for(data_dir, hmac_key)
    on = type(full.timer)(enabled=True, next_fire="Tue 09:00", detail="enabled")
    combined = type(full)(**{**vars(full), "timer": on})

    reasons = explain_not_triggered(combined)

    assert not any("timer is NOT enabled" in line for line in reasons)
