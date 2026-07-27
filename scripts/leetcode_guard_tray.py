#!/usr/bin/env python3
"""System tray icon for leetcode-guard status.

Uses ``Gtk.StatusIcon`` (legacy XEmbed) rather than AppIndicator3, for the same
reason screen-locker's tray does: AppIndicator is menu-only on left-click by
design, but this icon needs single-click-to-open. i3bar's systray implements
XEmbed directly and no ``org.kde.StatusNotifierWatcher`` runs on this session
bus, so a plain ``Gtk.StatusIcon`` renders identically with no bridge.

Runs under the **system** Python: PyGObject/GTK3 are system packages and are
not present in any project venv. All data comes from shelling out to the
already-tested status CLI rather than importing ``leetcode_guard``.

**Clicking toggles.** screen-locker's tray spawns a fresh window every click,
so clicking twice leaves two windows to close. Here the child process is
tracked: click opens it, click again closes it. That plus the window's own
Close button, Escape, and the WM close box.
"""

from __future__ import annotations

import logging
import subprocess

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk

STATUS_CMD = ["/usr/bin/python3", "-m", "leetcode_guard.status_view"]
REFRESH_INTERVAL_S = 60
SUBPROCESS_TIMEOUT_S = 10
TERMINATE_GRACE_S = 3

# Speech bubbles, NOT the shields the workout tray uses. Two shield icons
# side by side in the same tray are indistinguishable at 24px, which is the
# only size that matters here -- the silhouette has to differ, not just the
# colour.
#
# Verified against the live theme chain: elementary has no `user-busy`, so GTK
# falls all three back to AdwaitaLegacy *together* and they stay a consistent
# family. Checking one icon resolves is not enough; check the whole triad.
ICON_BY_STATE = {
    "ok": "user-available",
    "warn": "user-away",
    "lock": "user-busy",
}
FALLBACK_STATE = "warn"

_logger = logging.getLogger("leetcode-guard-tray")

_STATE: dict[str, subprocess.Popen[bytes] | None] = {"window": None}
"""A dict rather than a module-level name, so toggling needs no ``global``."""


def _run_status(*args: str) -> str:
    """Run the status CLI and return stripped stdout, or ''."""
    try:
        result = subprocess.run(
            [*STATUS_CMD, *args],
            capture_output=True,
            text=True,
            timeout=SUBPROCESS_TIMEOUT_S,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        _logger.warning("leetcode-guard status CLI failed: %s", exc)
        return ""
    return result.stdout.strip()


def refresh(icon: Gtk.StatusIcon) -> bool:
    """Update the icon glyph and tooltip. Reschedules itself."""
    state = _run_status("--state") or FALLBACK_STATE
    summary = _run_status("--summary") or "leetcode-guard: status unavailable"
    icon.set_from_icon_name(ICON_BY_STATE.get(state, ICON_BY_STATE[FALLBACK_STATE]))
    icon.set_tooltip_text(summary)
    return True  # keep the GLib timeout alive


def _live_window() -> subprocess.Popen[bytes] | None:
    """The running status window, or ``None`` if it has exited."""
    window = _STATE["window"]
    if window is None or window.poll() is not None:
        return None
    return window


def toggle_window(_icon: Gtk.StatusIcon) -> None:
    """Open the status window, or close it if it is already up.

    A toggle rather than a spawn: clicking twice should not leave two windows
    to dismiss.
    """
    window = _live_window()
    if window is None:
        _STATE["window"] = subprocess.Popen(STATUS_CMD, start_new_session=True)
        return
    window.terminate()
    try:
        window.wait(timeout=TERMINATE_GRACE_S)
    except subprocess.TimeoutExpired:
        _logger.warning("status window ignored SIGTERM; killing it")
        window.kill()
    _STATE["window"] = None


def show_popup_menu(icon: Gtk.StatusIcon, button: int, time: int) -> None:
    """Right-click: refresh, or quit the tray icon itself."""
    menu = Gtk.Menu()

    refresh_item = Gtk.MenuItem(label="Refresh")
    refresh_item.connect("activate", lambda _widget: refresh(icon))
    menu.append(refresh_item)

    quit_item = Gtk.MenuItem(label="Quit tray icon")
    quit_item.connect("activate", lambda _widget: Gtk.main_quit())
    menu.append(quit_item)

    menu.show_all()
    menu.popup(None, None, None, icon, button, time)


def main() -> None:
    """Create the icon, refresh once, then enter the GTK loop."""
    icon = Gtk.StatusIcon()
    icon.set_title("LeetCode Status")
    icon.connect("activate", toggle_window)
    icon.connect("popup-menu", show_popup_menu)
    refresh(icon)
    GLib.timeout_add_seconds(REFRESH_INTERVAL_S, refresh, icon)
    Gtk.main()


if __name__ == "__main__":
    main()
