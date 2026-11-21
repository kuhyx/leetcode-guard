#!/usr/bin/env python3
"""Prove an upgraded extension's heartbeat reaches the guard from an OLD profile.

``verify_heartbeat_extension`` starts from a fresh profile, so it cannot see this:
Chromium keeps the cached service worker script of an unpacked extension across a
manifest bump and a browser restart when the worker's file name is unchanged. The
guard then ran version 1.0.0's worker (nudge only), which ignores ``{"type":"beat"}``,
and no heartbeat ever arrived (diagnosed 2026-11-21 on the real profile).

This check seeds a throwaway profile by running the shipped 1.0.0 extension
(``scripts/fixtures/extension_1_0_0/``, verbatim from commit 290d0f2) until its
worker is registered, stops the browser, swaps the SAME extension directory (an
unpacked extension's id derives from its path) for the current ``extension/`` and
starts the browser on the SAME profile. A beat must reach the stub listener.

    python3 -m scripts.verify_heartbeat_upgrade [--browser /usr/bin/helium-browser]

Headless, muted, ``--user-data-dir`` under ``~/data/claude-scratch``; never the
user's profile or display. Exit 0 = the beat arrived after the upgrade.
"""

from __future__ import annotations

import argparse
import contextlib
import json
from pathlib import Path
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from typing import IO, TYPE_CHECKING, NoReturn

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

HERE = Path(__file__).resolve().parent
SCRATCH = Path.home() / "data" / "claude-scratch" / "heartbeat-extension"
OLD_EXTENSION = HERE / "fixtures" / "extension_1_0_0"
WAIT_SECONDS = 15


def _fail(message: str) -> NoReturn:
    """Report a setup failure and stop."""
    sys.stdout.write(f"FAIL {message}\n")
    raise SystemExit(1)


def _pump(stream: IO[str], beats: queue.Queue[str]) -> None:
    """Queue each beat line the stub prints."""
    for line in stream:
        beats.put(line)


def _poll(predicate: Callable[[], object]) -> bool:
    """Poll until ``predicate`` is truthy; False after ``WAIT_SECONDS``."""
    end = time.monotonic() + WAIT_SECONDS
    while time.monotonic() < end:
        if predicate():
            return True
        time.sleep(0.05)
    return False


def _rewrites(port: int) -> dict[str, tuple[str, str]]:
    """Per file: shipped text -> text aimed at the stub (8782 is the live service's).

    Same intent as ``verify_heartbeat_extension.REWRITES``, which scripts must not
    import: keep the two in step. A shipped text that matches nothing fails the run.
    """
    return {
        "manifest.json": ("http://127.0.0.1:8782/*", f"http://127.0.0.1:{port}/*"),
        "sw.js": ("http://127.0.0.1:8782/beat", f"http://127.0.0.1:{port}/beat"),
        "relay.js": (
            "const BEAT_INTERVAL_MS = 60000;",
            "const BEAT_INTERVAL_MS = 4000;",
        ),
    }


def _install_current(target: Path, listener_port: int) -> None:
    """Replace ``target`` with a copy of ``extension/`` aimed at the stub."""
    shutil.rmtree(target)
    shutil.copytree(HERE.parent / "extension", target)
    for name, (shipped, replacement) in _rewrites(listener_port).items():
        text = (target / name).read_text()
        if shipped not in text:
            _fail(f"setup: {name} has no {shipped!r}; the rewrite matched nothing")
        (target / name).write_text(text.replace(shipped, replacement))


def _script_cache(profile: Path) -> list[str]:
    """Names of the cached service worker scripts in the profile."""
    cache = profile / "Default" / "Service Worker" / "ScriptCache"
    return sorted(p.name for p in cache.iterdir()) if cache.is_dir() else []


def _registered_version(profile: Path, extension: Path) -> str:
    """Version the profile's prefs record for the extension's worker, or ``""``.

    Chromium writes ``service_worker_registration_info`` only once the worker is
    registered, and flushes prefs lazily, so a seed stopped before this shows up
    leaves no stale registration to test against.
    """
    prefs_file = profile / "Default" / "Preferences"  # replaced atomically
    if not prefs_file.exists():
        return ""
    prefs = json.loads(prefs_file.read_text())
    for entry in prefs.get("extensions", {}).get("settings", {}).values():
        if entry.get("path") == str(extension):
            info = entry.get("service_worker_registration_info") or {}
            return str(info.get("version", ""))
    return ""


def _browse(
    browser: str, profile: Path, extension: Path, mock_port: int, done: Callable
) -> bool:
    """Run the headless browser until ``done()`` is truthy, then stop it."""
    command = [
        browser,
        f"--user-data-dir={profile}",
        "--headless=new",
        "--mute-audio",
        "--disable-gpu",
        "--no-first-run",
        f"--load-extension={extension}",
        "--ignore-certificate-errors",
        f"--host-resolver-rules=MAP leetcode.com 127.0.0.1:{mock_port}",
        "https://leetcode.com/problems/two-sum/",
    ]
    out = subprocess.DEVNULL
    with subprocess.Popen(command, stdout=out, stderr=out) as proc:
        try:
            return _poll(done)
        finally:
            proc.terminate()
            proc.wait(timeout=10)


def _upgrade(
    browser: str, work: Path, ports: dict[str, int], beats: queue.Queue[str]
) -> bool:
    """Seed with 1.0.0, swap in the current extension, expect a beat."""
    extension, profile = work / "extension", work / "profile"
    shutil.copytree(OLD_EXTENSION, extension)

    def registered() -> bool:
        return bool(_script_cache(profile) and _registered_version(profile, extension))

    if not _browse(browser, profile, extension, ports["mock"], registered):
        _fail("seed: 1.0.0's worker was not registered in the profile in time")
    seeded = f"{_registered_version(profile, extension)} {_script_cache(profile)}"
    _install_current(extension, ports["stub"])
    got = _browse(browser, profile, extension, ports["mock"], lambda: not beats.empty())
    after = f"{_registered_version(profile, extension)} {_script_cache(profile)}"
    sys.stdout.write(f"seeded   {seeded}\nupgraded {after}\n")
    return got


@contextlib.contextmanager
def _stub(work: Path) -> Iterator[tuple[dict[str, int], queue.Queue[str]]]:
    """Run ``heartbeat_stub.py``: yield its ports and a queue of the beats."""
    command = [sys.executable, str(HERE / "heartbeat_stub.py"), str(work)]
    with subprocess.Popen(command, stdout=subprocess.PIPE, text=True) as proc:
        if proc.stdout is None:
            _fail("setup: the stub has no stdout")
        beats: queue.Queue[str] = queue.Queue()
        ports = json.loads(proc.stdout.readline())
        threading.Thread(target=_pump, args=(proc.stdout, beats), daemon=True).start()
        try:
            yield ports, beats
        finally:
            proc.terminate()


def main() -> int:
    """Run the check; exit 1 if no beat arrived after the upgrade."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--browser", default="/usr/bin/helium-browser")
    browser = parser.parse_args().browser
    SCRATCH.mkdir(parents=True, exist_ok=True)
    # The browser may still be flushing its profile as the directory goes.
    with (
        tempfile.TemporaryDirectory(dir=SCRATCH, ignore_cleanup_errors=True) as tmp,
        _stub(Path(tmp)) as (ports, beats),
    ):
        got = _upgrade(browser, Path(tmp), ports, beats)
    if got:
        sys.stdout.write("PASS a beat arrived after upgrading a 1.0.0 profile\n")
    else:
        sys.stdout.write(f"FAIL no beat within {WAIT_SECONDS} s of the upgrade\n")
    return 0 if got else 1


if __name__ == "__main__":
    sys.exit(main())
