#!/usr/bin/env python3
"""Prove the browser extension reports the open problem to the guard's listener.

Runs ``heartbeat_stub.py`` (a mock ``leetcode.com`` over HTTPS plus a stub
listener) and loads a *copy* of ``extension/`` into a headless Helium with a
throwaway profile. Port 8782 belongs to the live service, so the copy gets the
stub's ephemeral port and a 4 s beat interval instead of 60 s (not 2 s: a beat
within 3 s of ``pushState`` must be the route poll, not a tick). Each rewrite is
an exact-match replace of a named constant; one that matches nothing fails the
run, so a refactor cannot silently test the real values.

Checks: (1) first beat on load; (2) a client-side route change
(``history.pushState`` over CDP, no reload) beats within 3 s; (3) interval beats
follow; (4) every body is exactly ``{"slug", "tab"}``; (5) a backgrounded tab
sends nothing for longer than one interval and beats once visible again. The
nudge half is ``verify_nudge_extension``.

    python3 -m scripts.verify_heartbeat_extension [--browser /usr/bin/helium-browser]

Headless, muted, ``--user-data-dir`` under ``~/data/claude-scratch``; never the
user's profile or display. Exit 0 = every check held.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from typing import IO, TYPE_CHECKING, NoReturn
from urllib.request import urlopen

if TYPE_CHECKING:
    from collections.abc import Callable

HERE = Path(__file__).resolve().parent
SCRATCH = Path.home() / "data" / "claude-scratch" / "heartbeat-extension"
SLUG = "two-sum"
ROUTE_DEADLINE = 3.0
TICK_DEADLINE = 9.0
HIDDEN_SECONDS = 5.0  # longer than the rewritten 4 s interval
BEATS: list[dict[str, str]] = []  # filled by _collect from the stub's stdout

# (file, shipped text, template for the copy). Each shipped text is one named
# constant on its own line in the extension, so the match is exact.
REWRITES = (
    ("manifest.json", "http://127.0.0.1:8782/*", "http://127.0.0.1:{port}/*"),
    ("background.js", "http://127.0.0.1:8782/beat", "http://127.0.0.1:{port}/beat"),
    ("relay.js", "const BEAT_INTERVAL_MS = 60000;", "const BEAT_INTERVAL_MS = 4000;"),
)


def _say(line: str) -> None:
    """Report one line (``sys.stdout``: ruff's T201 fixer deletes prints)."""
    sys.stdout.write(line + "\n")


def _die(message: str) -> NoReturn:
    """Report a setup failure and stop."""
    _say(f"FAIL {message}")
    raise SystemExit(1)


def _bodies() -> list[dict[str, object]]:
    return [json.loads(beat["body"]) for beat in BEATS]


def _collect(stream: IO[str]) -> None:
    """Append each beat the stub reports to ``BEATS``."""
    BEATS.extend(json.loads(line) for line in stream)


def _prepare_extension(directory: Path, listener_port: int) -> Path:
    """Copy ``extension/`` and rewrite the port and interval; fail on no match."""
    copy = directory / "extension"
    shutil.copytree(HERE.parent / "extension", copy)
    for name, shipped, template in REWRITES:
        text = (copy / name).read_text()
        if shipped not in text:
            _die(f"setup: {name} has no {shipped!r}; the rewrite matched nothing")
        new = text.replace(shipped, template.format(port=listener_port))
        (copy / name).write_text(new)
    return copy


def _cdp_call(ws_url: str, method: str, params: dict[str, object]) -> None:
    """Run one CDP command through the standalone ``cdp_call.py`` helper."""
    args = [sys.executable, str(HERE / "cdp_call.py"), ws_url, method]
    result = subprocess.run(
        [*args, json.dumps(params)], check=False, capture_output=True, text=True
    )
    if result.returncode:
        _die(f"cdp: {method} failed: {result.stdout}{result.stderr}")


def _page_ws_url(profile: Path) -> str:
    """Find the page target's websocket URL via the profile's DevToolsActivePort."""
    port_file = profile / "DevToolsActivePort"
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        if port_file.exists() and port_file.read_text().strip():
            port = port_file.read_text().splitlines()[0]
            with urlopen(f"http://127.0.0.1:{port}/json/list", timeout=5) as reply:
                targets = json.load(reply)
            for target in targets:
                if target["type"] == "page" and "leetcode.com" in target["url"]:
                    return str(target["webSocketDebuggerUrl"])
        time.sleep(0.1)
    _die("cdp: no leetcode.com page target within 15 s")


def _wait_for(predicate: Callable[[], object], seconds: float) -> bool:
    """Poll until ``predicate`` is truthy or time runs out."""
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return False


def _check_first() -> list[str]:
    """Assertion 1: the load beat."""
    if not _wait_for(lambda: BEATS, 15):
        return ["1: no beat arrived within 15 s of loading the problem page"]
    beat = BEATS[0]
    origin = beat["origin"].startswith("chrome-extension://")
    got = (json.loads(beat["body"]), beat["method"], beat["path"], origin)
    want = ({"slug": SLUG, "tab": "description"}, "POST", "/beat", True)
    if got != want:
        return [f"1: first beat (body, method, path, ext-origin) {got}, want {want}"]
    return []


def _check_route_and_ticks(ws_url: str) -> list[str]:
    """Assertions 2 and 3: SPA route change, then interval beats."""
    route = f'history.pushState({{}}, "", "/problems/{SLUG}/editorial/")'
    sent = time.monotonic()
    _cdp_call(ws_url, "Runtime.evaluate", {"expression": route})
    if not _wait_for(lambda: any(b["tab"] == "editorial" for b in _bodies()), 3):
        return [f"2: no tab=editorial beat within {ROUTE_DEADLINE:.0f} s of pushState"]
    _say(f"route change beat after {time.monotonic() - sent:.2f} s")
    seen = len(BEATS)
    if not _wait_for(lambda: len(BEATS) >= seen + 2, TICK_DEADLINE):
        extra = len(BEATS) - seen
        return [f"3: only {extra} interval beat(s) in {TICK_DEADLINE:.0f} s, need 2"]
    return []


def _check_hidden(ws_url: str) -> list[str]:
    """Assertion 5: a backgrounded tab stays silent, then beats on return."""
    _cdp_call(ws_url, "Target.createTarget", {"url": "about:blank"})
    time.sleep(0.5)  # a visibilitychange beat racing the switch must not count
    quiet = len(BEATS)
    time.sleep(HIDDEN_SECONDS)
    if len(BEATS) != quiet:
        return [f"5: {len(BEATS) - quiet} beat(s) while the tab was hidden"]
    _cdp_call(ws_url, "Page.bringToFront", {})
    if not _wait_for(lambda: len(BEATS) > quiet, ROUTE_DEADLINE):
        return ["5: no beat within 3 s of the tab becoming visible again"]
    return []


def _check_shape() -> list[str]:
    """Assertion 4: every body is exactly slug + tab."""
    bad = [sorted(body) for body in _bodies() if set(body) != {"slug", "tab"}]
    return [f"4: a beat body had keys {bad[0]}, want slug and tab only"] if bad else []


def _run(browser: str, mock_port: int, extension: Path, profile: Path) -> list[str]:
    command = [
        browser,
        "--headless=new",
        "--mute-audio",
        "--no-first-run",
        "--disable-gpu",
        "--remote-debugging-port=0",
        f"--user-data-dir={profile}",
        f"--load-extension={extension}",
        f"--host-resolver-rules=MAP leetcode.com 127.0.0.1:{mock_port}",
        "--ignore-certificate-errors",
        f"https://leetcode.com/problems/{SLUG}/",
    ]
    with subprocess.Popen(
        command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    ) as proc:
        try:
            ws_url = _page_ws_url(profile)
            failures = _check_first()
            for check in (_check_route_and_ticks, _check_hidden):
                failures = failures or check(ws_url)
            return failures + _check_shape()
        finally:
            proc.terminate()
            proc.wait(timeout=10)


def main() -> int:
    """Run the checks; exit 1 if any failed."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--browser", default="/usr/bin/helium-browser")
    args = parser.parse_args()
    SCRATCH.mkdir(parents=True, exist_ok=True)
    # The browser may still be flushing its profile as the directory goes.
    with tempfile.TemporaryDirectory(dir=SCRATCH, ignore_cleanup_errors=True) as tmp:
        work = Path(tmp)
        with subprocess.Popen(
            [sys.executable, str(HERE / "heartbeat_stub.py"), tmp],
            stdout=subprocess.PIPE,
            text=True,
        ) as stub:
            if stub.stdout is None:
                _die("setup: the stub has no stdout")
            ports = json.loads(stub.stdout.readline())
            threading.Thread(target=_collect, args=(stub.stdout,), daemon=True).start()
            try:
                extension = _prepare_extension(work, ports["stub"])
                profile = work / "profile"
                failures = _run(args.browser, ports["mock"], extension, profile)
            finally:
                stub.terminate()
    for failure in failures:
        _say(f"FAIL {failure}")
    if not failures:
        _say(f"PASS {len(BEATS)} beats: load, route, interval, hidden, exact")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
