"""Shared helpers for the ``/beat`` listener tests (not collected as tests)."""

from __future__ import annotations

from contextlib import contextmanager
import http.client
import json
import socket
from typing import TYPE_CHECKING

from leetcode_guard import _constants
from leetcode_guard._attempt_server import AttemptServer
from leetcode_guard._pool_cache import CachedPool, write_cache
from leetcode_guard._problem import Problem

if TYPE_CHECKING:
    from collections.abc import Iterator, Sequence


def write_pool(slugs: Sequence[str]) -> None:
    """Write the (test-redirected) pool cache holding ``slugs``."""
    problems = tuple(
        Problem("1", slug, slug, "Easy", 50.0, False, None) for slug in slugs
    )
    write_cache(_constants.POOL_CACHE_FILE, CachedPool(problems, 1.0, True))


def post(
    port: int,
    body: bytes | str,
    headers: dict[str, str] | None = None,
    path: str = "/beat",
    method: str = "POST",
) -> http.client.HTTPResponse:
    """One request over a fresh connection; the body is read and discarded."""
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    conn.request(method, path, body=body, headers=headers or {})
    response = conn.getresponse()
    response.read()
    conn.close()
    return response


def raw_exchange(port: int, request: bytes) -> bytes:
    """Send hand-written bytes and return the first line of the reply."""
    with socket.create_connection(("127.0.0.1", port), timeout=5) as sock:
        sock.sendall(request)
        return sock.makefile("rb").readline()


GOOD = json.dumps({"slug": "two-sum", "tab": "description"})
"""A beat the default pool accepts."""


@contextmanager
def serving(slugs: Sequence[str]) -> Iterator[int]:
    """A started listener on a free port whose pool holds ``slugs``."""
    write_pool(slugs)
    server = AttemptServer(port=0)
    assert server.start()
    assert server.port is not None
    try:
        yield server.port
    finally:
        server.stop()
