#!/usr/bin/env python3
"""Prove that a restart does not change whether the lock is in study mode.

``verify_study_grab`` proves the grab drops. This proves it *stays* dropped
across a restart of the process, which is what ``systemctl --user restart
leetcode-guard`` does. A mocked Tk root cannot answer that (a released grab and
a held one look identical to a mock), so each lock here is a real child process
on a real X server, driven through the real ``_cli.cmd_lock`` and killed with
SIGTERM, the way systemd stops the unit::

    xvfb-run -a -s "-screen 0 1600x1200x24" python3 -m scripts.verify_restart_study

Children run in order, each judged by gatelock's public ``holds_grab()``:

1. a lock enters study mode (grab released), then gets SIGTERM;
2. the restart comes back in study mode: grab NOT held, and still not held
   after a recovery tick (a grab that returns a second later is the 2026-08-05
   bug in disguise); SIGTERM again leaves the marker;
3. a second restart resumes, then "Back to lock": grab held, marker gone;
4. control, no marker: the lock comes up LOCKED, grab held.

The locks are run by ``verify_restart_study_child`` (a separate module, started
with ``-m``, never imported). Scratch ``HOME`` and ``XDG_RUNTIME_DIR``
throughout: never the real ledger, never the real marker, never the sync, the
nudge port or display :0.
"""

from __future__ import annotations

import importlib
import json
import logging
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
from typing import Any, Final

_logger: Final = logging.getLogger(__name__)
CHILD_TIMEOUT_SECONDS: Final = 25.0
STOP_TIMEOUT_SECONDS: Final = 15
SAMPLE_AFTER_UP: Final = 3.0
MIN_SAMPLES: Final = 20
CHILD_MODULE: Final = "scripts.verify_restart_study_child"


# -- the parent: start, stop with SIGTERM, restart, judge ---------------------


def _read(status: Path) -> list[dict[str, Any]]:
    """What the child has reported so far."""
    if not status.is_file():
        return []  # not written yet; the child replaces it atomically
    data: list[dict[str, Any]] = json.loads(status.read_text(encoding="utf-8"))
    return data


def _spawn(role: str, workdir: Path) -> tuple[subprocess.Popen[bytes], Path]:
    """Start a lock process (scratch HOME, runtime dir); give it and its report."""
    status = workdir / f"status-{role}-{time.monotonic_ns()}.json"
    env = {
        **os.environ,
        "HOME": str(workdir / "home"),
        "XDG_RUNTIME_DIR": str(workdir / "run"),
        # HOME moves the user site; the editable gatelock lives in the real one.
        "PYTHONUSERBASE": str(Path.home() / ".local"),
    }
    cmd = [sys.executable, "-m", CHILD_MODULE, role, str(status)]
    return subprocess.Popen(cmd, env=env), status


def _wait_final(proc: subprocess.Popen[bytes], status: Path) -> list[dict[str, Any]]:
    """Wait for the child's final report (or its death, or the timeout)."""
    deadline = time.monotonic() + CHILD_TIMEOUT_SECONDS
    while time.monotonic() < deadline and proc.poll() is None:
        stages = _read(status)
        if stages and stages[-1]["final"]:
            break
        time.sleep(0.1)
    return _read(status)


def _stop(proc: subprocess.Popen[bytes]) -> int:
    """SIGTERM, as systemd does on stop/restart; kill if it will not go."""
    proc.send_signal(signal.SIGTERM)
    try:
        return proc.wait(timeout=STOP_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        _logger.warning("a lock did not stop on SIGTERM; killing it")
        proc.kill()
        return -9


def _run(role: str, workdir: Path) -> tuple[list[dict[str, Any]], int]:
    """One lock process: wait for its final report, then SIGTERM it."""
    proc, status = _spawn(role, workdir)
    with proc:
        stages = _wait_final(proc, status)
        return stages, _stop(proc)


class _GrabProbe:
    """Asks X whether some client holds the keyboard grab (python-xlib)."""

    def __init__(self) -> None:
        self._x = importlib.import_module("Xlib.X")
        self._dpy = importlib.import_module("Xlib.display").Display()

    def held(self) -> bool:
        """Take the grab if it is free and give it straight back."""
        owner_events = True
        got = self._dpy.screen().root.grab_keyboard(
            owner_events,
            self._x.GrabModeAsync,
            self._x.GrabModeAsync,
            self._x.CurrentTime,
        )
        self._dpy.sync()
        if got == self._x.GrabSuccess:
            self._dpy.ungrab_keyboard(self._x.CurrentTime)
            self._dpy.sync()
            return False
        return True


def _handoff(workdir: Path) -> tuple[int, int, bool]:
    """SIGTERM a lock in study mode, start its successor, sample the grab.

    Samples every 50 ms from the SIGTERM until 3 s after the successor is up.

    Returns:
        (samples taken, samples with the grab held, successor came back in study).
    """
    probe = _GrabProbe()
    old, old_status = _spawn("resume", workdir)
    with old:
        _wait_final(old, old_status)
        old.send_signal(signal.SIGTERM)
        new: subprocess.Popen[bytes] | None = None
        new_status = workdir / "unset"
        up_at: float | None = None
        samples = held = 0
        deadline = time.monotonic() + CHILD_TIMEOUT_SECONDS
        while time.monotonic() < deadline:
            samples += 1
            held += probe.held()
            if new is None and old.poll() is not None:
                new, new_status = _spawn("resume", workdir)
            if up_at is None and any(s["stage"] == "start" for s in _read(new_status)):
                up_at = time.monotonic()
            if up_at is not None and time.monotonic() - up_at > SAMPLE_AFTER_UP:
                break
            time.sleep(0.05)
    if new is None:
        return samples, held, False
    with new:
        studying = _seen(_read(new_status), "start", "studying") is True
        _stop(new)
    return samples, held, studying


def _seen(stages: list[dict[str, Any]], stage: str, key: str) -> object:
    """What the child reported for ``key`` at ``stage``; ``None`` if never."""
    return next((s[key] for s in stages if s["stage"] == stage), None)


def _claims(workdir: Path) -> list[tuple[str, bool]]:
    """Run the four lock processes in order; each claim is judged as it is made."""
    marker = workdir / "run" / "leetcode-guard" / "study.json"
    enter, code = _run("enter", workdir)
    claims = [
        ("first lock: grab held before study", _seen(enter, "start", "held") is True),
        (
            "first lock: Open released the grab",
            _seen(enter, "after-open", "held") is False,
        ),
        ("first lock: SIGTERM exits cleanly", code == 0),
        ("SIGTERM left the study marker in place", marker.is_file()),
    ]
    samples, held, studying = _handoff(workdir)
    claims += [
        ("restart: came back in study", studying),
        (f"restart: {held} of {samples} 50 ms samples held the grab", held == 0),
        ("restart: enough samples to mean something", samples >= MIN_SAMPLES),
        ("the second SIGTERM left the marker too", marker.is_file()),
    ]
    back, _ = _run("back", workdir)
    claims += [
        ("2nd restart: also in study", _seen(back, "start", "studying") is True),
        ("Back to lock: the grab is held", _seen(back, "back", "held") is True),
        ("Back to lock: the marker is gone", not marker.exists()),
    ]
    control, _ = _run("control", workdir)
    claims += [
        ("control, no marker: locked", _seen(control, "start", "studying") is False),
        ("control: the grab is held", _seen(control, "start", "held") is True),
        ("control: still held after a tick", _seen(control, "settled", "held") is True),
    ]
    return claims


def main() -> int:
    """Print one verdict per claim and a total."""
    if os.environ.get("DISPLAY", ":0") == ":0":
        print("refusing to run on display :0; use xvfb-run")
        return 2
    print("Verifying that a restart keeps study mode (real X, real SIGTERM):")
    workdir = Path(tempfile.mkdtemp(prefix="lg-restart-check-"))
    for sub in ("home", "run"):
        (workdir / sub).mkdir(mode=0o700)
    claims = _claims(workdir)
    for label, ok in claims:
        print(f"  [{'PASS' if ok else 'FAIL'}] {label}")
    failed, total = sum(not ok for _, ok in claims), len(claims)
    print(
        f"\nFAILED: {failed} of {total} checks failed."
        if failed
        else f"\nOK: {total} checks passed."
    )
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
