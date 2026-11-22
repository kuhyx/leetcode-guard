"""``/api/theory`` over a real loopback server: status, type, and the 404 text."""

from __future__ import annotations

from datetime import datetime
import http.client
import json
from threading import Thread
from typing import TYPE_CHECKING

from leetcode_guard._web_server import create_server
from leetcode_guard.tests._theory_scenario import began, states, taught, world
from leetcode_guard.tests.test_web_theory import KEYS

if TYPE_CHECKING:
    from pathlib import Path


def _fetch(path: str) -> tuple[int, str, bytes]:
    """One GET against a loopback server that answers exactly one request."""
    server = create_server("127.0.0.1", 0)
    worker = Thread(target=server.handle_request, daemon=True)
    worker.start()
    conn = http.client.HTTPConnection("127.0.0.1", int(server.server_address[1]))
    try:
        conn.request("GET", path)
        resp = conn.getresponse()
        return resp.status, resp.getheader("Content-Type") or "", resp.read()
    finally:
        conn.close()
        worker.join(timeout=5)
        server.server_close()


def test_the_route_serves_the_block_as_json(tmp_path, monkeypatch, hmac_key: Path):
    """200, ``application/json``, one ``theory`` object with the contract keys."""
    world(tmp_path, monkeypatch)
    states(hmac_key)
    began(hmac_key)
    taught(hmac_key, datetime.now().astimezone(), ("a", 7))

    status, ctype, body = _fetch("/api/theory")

    assert (status, ctype) == (200, "application/json; charset=utf-8")
    assert list(json.loads(body)) == ["theory"]
    assert tuple(json.loads(body)["theory"]) == KEYS
    assert json.loads(body)["theory"]["minutes_today"] == 7


def test_the_404_names_the_theory_route():
    """The not-found text stays truthful."""
    status, _, body = _fetch("/api/nope")

    assert status == 404
    assert b"/api/theory" in body
