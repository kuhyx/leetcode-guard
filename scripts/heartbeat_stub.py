#!/usr/bin/env python3
"""Serve a mock leetcode.com and a stub heartbeat listener; report every beat.

Helper of ``verify_heartbeat_extension.py``, which runs it as a subprocess.

    python3 scripts/heartbeat_stub.py CERT_DIR

First stdout line: ``{"mock": PORT, "stub": PORT}``. Then one JSON line per POST
the stub receives: ``{"method", "path", "origin", "body"}`` (body as text). The
mock answers every GET with one small HTML page over TLS (self-signed cert made
in CERT_DIR, CN leetcode.com). Runs until the parent terminates it.
"""

from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import ssl
import subprocess
import sys
import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import socket

PAGE = b"<!doctype html><title>mock</title><p>mock problem page</p>"
OPENSSL = "/usr/bin/openssl"
ARGC = 2


def _emit(line: object) -> None:
    """Write one JSON line to stdout and flush, so the parent sees it at once."""
    sys.stdout.write(json.dumps(line) + "\n")
    sys.stdout.flush()


class _Handler(BaseHTTPRequestHandler):
    """GET: the mock page. POST: report method, path, Origin and body."""

    def do_GET(self) -> None:
        """Serve the same page for every problem URL."""
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(PAGE)

    def do_POST(self) -> None:
        """Report the request, answer 204."""
        raw = self.rfile.read(int(self.headers.get("Content-Length", "0")))
        _emit(
            {
                "method": self.command,
                "path": self.path,
                "origin": self.headers.get("Origin", ""),
                "body": raw.decode(errors="replace"),
            }
        )
        self.send_response(204)
        self.end_headers()

    def log_message(self, fmt: str, /, *args: object) -> None:
        """Quiet."""


class _Server(ThreadingHTTPServer):
    """Wraps each accepted connection in TLS when ``context`` is set."""

    context: ssl.SSLContext | None = None

    def get_request(self) -> tuple[socket.socket, tuple[str, int]]:
        """Accept; the handshake runs lazily, in the handler's thread."""
        conn, address = super().get_request()
        if self.context is not None:
            conn = self.context.wrap_socket(
                conn, server_side=True, do_handshake_on_connect=False
            )
        return conn, address


def _tls_context(cert_dir: Path) -> ssl.SSLContext:
    """A server context with a fresh self-signed cert for ``leetcode.com``."""
    cert, key = cert_dir / "cert.pem", cert_dir / "key.pem"
    subprocess.run(
        [
            *(OPENSSL, "req", "-x509", "-newkey", "rsa:2048", "-nodes"),
            *("-keyout", str(key), "-out", str(cert), "-subj", "/CN=leetcode.com"),
        ],
        check=True,
        capture_output=True,
    )
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(cert, key)
    return context


def _serve(cert_dir: Path | None = None) -> ThreadingHTTPServer:
    """Start a server on a free port; with ``cert_dir``, over TLS as leetcode.com."""
    server = _Server(("127.0.0.1", 0), _Handler)
    if cert_dir:
        server.context = _tls_context(cert_dir)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def main(argv: list[str]) -> int:
    """Start both servers, announce their ports, then wait to be terminated."""
    if len(argv) != ARGC:
        sys.stdout.write("usage: heartbeat_stub.py CERT_DIR\n")
        return 1
    mock, stub = _serve(Path(argv[1])), _serve()
    _emit({"mock": mock.server_address[1], "stub": stub.server_address[1]})
    threading.Event().wait()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
