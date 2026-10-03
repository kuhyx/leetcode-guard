#!/usr/bin/env python3
"""Prove the browser extension rings the lock's doorbell, and only when it should.

A unit test cannot: the extension is JavaScript inside a real Chromium, hooking
LeetCode's own fetch/XHR. So this serves a mock ``leetcode.com`` over HTTPS
(self-signed, mapped with ``--host-resolver-rules``), loads ``extension/`` into a
headless Helium with a throwaway profile, and has the mock page poll the
submission-check endpoint the way LeetCode does.

Cases: an Accepted *submission* via fetch and via XHR must ring; an Accepted
*run* (``runcode_`` id) and a Wrong Answer must not. Latency is measured from
the moment the mock served the verdict to the moment the doorbell rang.

    python3 -m scripts.verify_nudge_extension [--browser /usr/bin/helium-browser]

Never touches the user's profile or display: headless, ``--user-data-dir`` under
``~/data/claude-scratch``. Exit 0 = every case behaved.
"""

from __future__ import annotations

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import shutil
import ssl
import subprocess
import sys
import tempfile
import threading
import time
from typing import ClassVar

from leetcode_guard._nudge_server import NUDGE_PORT, NudgeServer

REPO = Path(__file__).resolve().parent.parent
EXTENSION = REPO / "extension"
SCRATCH = Path.home() / "data" / "claude-scratch" / "nudge-extension"
WAIT_SECONDS = 20.0
OPENSSL = "/usr/bin/openssl"

# (case, transport, check id, verdict, should ring)
CASES = (
    ("fetch-accepted", "fetch", "101", "Accepted", True),
    ("xhr-accepted", "xhr", "102", "Accepted", True),
    ("run-accepted", "fetch", "runcode_103", "Accepted", False),
    ("fetch-wrong", "fetch", "104", "Wrong Answer", False),
)

PAGE = """<!doctype html><title>mock</title><script>
const mode = new URLSearchParams(location.search);
const url = "/submissions/detail/" + mode.get("id") + "/check/";
if (mode.get("t") === "xhr") {
  const x = new XMLHttpRequest(); x.open("GET", url); x.send();
} else { fetch(url); }
</script>"""


class _Mock(BaseHTTPRequestHandler):
    verdicts: ClassVar[dict[str, str]] = {}
    served: ClassVar[dict[str, float]] = {}

    def do_GET(self) -> None:
        """Serve the problem page or a verdict."""
        if self.path.startswith("/problems/"):
            self._send("text/html", PAGE.encode())
            return
        if not self.path.startswith("/submissions/detail/"):
            self.send_error(404)
            return
        check_id = self.path.split("/")[3]
        verdict = self.verdicts.get(check_id, "Accepted")
        code = 10 if verdict == "Accepted" else 11
        body = {"state": "SUCCESS", "status_msg": verdict, "status_code": code}
        type(self).served[check_id] = time.monotonic()
        self._send("application/json", json.dumps(body).encode())

    def _send(self, kind: str, body: bytes) -> None:
        self.send_response(200)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt: str, /, *args: object) -> None:
        """Quiet."""


def _cert(directory: Path) -> tuple[Path, Path]:
    cert, key = directory / "cert.pem", directory / "key.pem"
    subprocess.run(
        [
            OPENSSL,
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-keyout",
            str(key),
            "-out",
            str(cert),
            "-days",
            "1",
            "-subj",
            "/CN=leetcode.com",
        ],
        check=True,
        capture_output=True,
    )
    return cert, key


def _serve_mock(directory: Path) -> ThreadingHTTPServer:
    cert, key = _cert(directory)
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Mock)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(cert, key)
    server.socket = context.wrap_socket(server.socket, server_side=True)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def _run_case(
    browser: str, mock_port: int, case: tuple[str, str, str, str, bool]
) -> bool:
    name, transport, check_id, verdict, should_ring = case
    _Mock.verdicts[check_id] = verdict
    rang: list[float] = []
    bell = NudgeServer(lambda: rang.append(time.monotonic()), port=NUDGE_PORT)
    if not bell.start():
        _say(f"FAIL {name}: port {NUDGE_PORT} is taken (is a lock running?)")
        return False
    profile = Path(tempfile.mkdtemp(dir=SCRATCH))
    url = f"https://leetcode.com/problems/two-sum/?t={transport}&id={check_id}"
    proc = subprocess.Popen(
        [
            browser,
            "--headless=new",
            "--no-first-run",
            "--disable-gpu",
            f"--user-data-dir={profile}",
            f"--load-extension={EXTENSION}",
            f"--host-resolver-rules=MAP leetcode.com 127.0.0.1:{mock_port}",
            "--ignore-certificate-errors",
            url,
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.monotonic() + (WAIT_SECONDS if should_ring else 8.0)
        while time.monotonic() < deadline and not rang:
            time.sleep(0.01)
    finally:
        proc.terminate()
        proc.wait(timeout=10)
        bell.stop()
        shutil.rmtree(profile, ignore_errors=True)
    served = _Mock.served.get(check_id)
    if served is None:
        _say(f"FAIL {name}: the mock verdict was never requested")
        return False
    if should_ring and rang:
        _say(f"PASS {name}: rang {1000 * (rang[0] - served):.1f} ms after the verdict")
        return True
    if not should_ring and not rang:
        _say(f"PASS {name}: verdict served, doorbell stayed silent")
        return True
    _say(f"FAIL {name}: should_ring={should_ring}, rang={bool(rang)}")
    return False


def _say(line: str) -> None:
    """Report one line.

    ``sys.stdout`` rather than print: ruff's T201 fixer deletes prints, and
    this output is the harness's whole interface.
    """
    sys.stdout.write(line + "\n")


def main() -> int:
    """Run every case; exit non-zero if any misbehaved."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--browser", default="/usr/bin/helium-browser")
    args = parser.parse_args()
    SCRATCH.mkdir(parents=True, exist_ok=True)
    mock = _serve_mock(Path(tempfile.mkdtemp(dir=SCRATCH)))
    port = int(mock.server_address[1])
    results = [_run_case(args.browser, port, case) for case in CASES]
    mock.shutdown()
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
