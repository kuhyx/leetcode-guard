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

**Clicking opens the status app** (``app/``, the Flutter app that replaced the
tkinter window) through its launcher, ``app/tool/leetcode_guard_app.sh``. The
app's window closes itself; there is no toggle any more, because a Chrome
``--app`` window is not a child this process could close. If the launcher is
missing -- the app not checked out or not built yet -- the click logs a
warning and shows the ``--summary`` line as a desktop notification instead,
so a click is never silently dead.
"""

from __future__ import annotations

import logging
from pathlib import Path
import subprocess

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk

STATUS_CMD = ["/usr/bin/python3", "-m", "leetcode_guard.status_cli"]
DEFAULT_APP_LAUNCHER = (
    Path.home() / "src" / "leetcode-guard" / "app" / "tool" / "leetcode_guard_app.sh"
)
"""Absolute, because this file runs from ``~/.config/i3/scripts``, not from the
repo; the repo deploys from its working tree at this path."""
APP_LAUNCHER = DEFAULT_APP_LAUNCHER
NOTIFY_SEND = "/usr/bin/notify-send"
NOTIFY_TITLE = "LeetCode Status"
UNAVAILABLE = "leetcode-guard: status unavailable"
REFRESH_INTERVAL_S = 60
SUBPROCESS_TIMEOUT_S = 10

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
    summary = _run_status("--summary") or UNAVAILABLE
    icon.set_from_icon_name(ICON_BY_STATE.get(state, ICON_BY_STATE[FALLBACK_STATE]))
    icon.set_tooltip_text(summary)
    return True  # keep the GLib timeout alive


def _notify(text: str) -> None:
    """Show ``text`` as a desktop notification; a failure is only logged."""
    try:
        subprocess.run(
            [NOTIFY_SEND, "--app-name=leetcode-guard", NOTIFY_TITLE, text],
            capture_output=True,
            timeout=SUBPROCESS_TIMEOUT_S,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        _logger.warning("could not show the status notification: %s", exc)


def _launch_app() -> bool:
    """Start the status app detached; ``False``, with a warning, if it cannot."""
    if not APP_LAUNCHER.is_file():
        _logger.warning(
            "status app launcher %s is missing; showing the summary instead",
            APP_LAUNCHER,
        )
        return False
    try:
        # Through bash, so a launcher checked out without its exec bit runs.
        subprocess.Popen(["/bin/bash", str(APP_LAUNCHER)], start_new_session=True)
    except OSError as exc:
        _logger.warning("could not start the status app %s: %s", APP_LAUNCHER, exc)
        return False
    return True


def open_app(_icon: Gtk.StatusIcon) -> None:
    """Left-click: open the status app, else notify the one-line summary."""
    if not _launch_app():
        _notify(_run_status("--summary") or UNAVAILABLE)


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
    logging.basicConfig(level=logging.INFO)
    icon = Gtk.StatusIcon()
    icon.set_title(NOTIFY_TITLE)
    icon.connect("activate", open_app)
    icon.connect("popup-menu", show_popup_menu)
    refresh(icon)
    GLib.timeout_add_seconds(REFRESH_INTERVAL_S, refresh, icon)
    Gtk.main()


if __name__ == "__main__":
    main()
