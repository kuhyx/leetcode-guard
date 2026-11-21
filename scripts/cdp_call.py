#!/usr/bin/env python3
"""Send one Chrome DevTools Protocol command to a page and print the reply.

A dependency-free websocket client, because the repo's pre-commit environments
do not ship a websocket package. Used by ``verify_heartbeat_extension.py``.

    python3 scripts/cdp_call.py WS_URL METHOD [PARAMS_JSON]

Exit 0 and the reply JSON on stdout, 1 on a refused upgrade or an unexpected frame.
"""

from __future__ import annotations

import json
import socket
import struct
import sys
from typing import NoReturn

# Largest payload length that fits the 7-bit field of a websocket frame header.
SHORT_FRAME_LIMIT = 126
# The RFC 6455 sample key: the server only echoes a hash of it, nothing checks it.
MIN_ARGS = 3
MAX_ARGS = 4
SAMPLE_KEY = "dGhlIHNhbXBsZSBub25jZQ=="


def _fail(message: str) -> NoReturn:
    """Report to stdout and exit 1."""
    sys.stdout.write(message + "\n")
    sys.exit(1)


def call(ws_url: str, method: str, params: dict[str, object]) -> str:
    """Return the raw reply text for one command (id 1) sent over ``ws_url``."""
    host_port, _, path = ws_url.removeprefix("ws://").partition("/")
    host, _, port = host_port.partition(":")
    with socket.create_connection((host, int(port)), timeout=10) as sock:
        stream = sock.makefile("rwb")
        stream.write(
            f"GET /{path} HTTP/1.1\r\nHost: {host_port}\r\nUpgrade: websocket\r\n"
            f"Connection: Upgrade\r\nSec-WebSocket-Key: {SAMPLE_KEY}\r\n"
            "Sec-WebSocket-Version: 13\r\n\r\n".encode()
        )
        stream.flush()
        status = stream.readline()
        while stream.readline() != b"\r\n":
            continue
        if b" 101 " not in status:
            _fail(f"websocket upgrade refused: {status!r}")
        payload = json.dumps({"id": 1, "method": method, "params": params}).encode()
        # 0x81: final text frame; 0xfe: masked, 16-bit length (payload < 64 KiB);
        # an all-zero mask key is legal and leaves the payload as it is.
        stream.write(b"\x81\xfe" + struct.pack(">H", len(payload)) + bytes(4) + payload)
        stream.flush()
        # Replies are tiny (no domain is enabled, so no event floods): one unmasked
        # frame with a 7-bit length. Anything else is a harness bug.
        _, size = stream.read(2)
        if size >= SHORT_FRAME_LIMIT:
            _fail(f"unexpected reply frame length {size}")
        reply = stream.read(size).decode()
    if json.loads(reply).get("id") != 1:
        _fail(f"unexpected reply: {reply}")
    return reply


def main(argv: list[str]) -> int:
    """Run the command named on the command line."""
    if not MIN_ARGS <= len(argv) <= MAX_ARGS:
        _fail("usage: cdp_call.py WS_URL METHOD [PARAMS_JSON]")
    params = json.loads(argv[3]) if len(argv) == MAX_ARGS else {}
    sys.stdout.write(call(argv[1], argv[2], params) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
