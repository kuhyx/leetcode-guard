"""Tests for what ``/beat`` accepts: length, body shape and the slug pool.

Every refusal must precede any store write, so each negative test also asserts
that ``attempts.json`` stayed empty.
"""

from __future__ import annotations

from http import HTTPStatus
import json
import logging
import os
import socket
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

from leetcode_guard import _constants
from leetcode_guard._attempt_store import load
from leetcode_guard._pool_cache import read_cache
from leetcode_guard.tests._attempt_server_helpers import (
    GOOD,
    post,
    raw_exchange,
    serving,
    write_pool,
)

if TYPE_CHECKING:
    from collections.abc import Iterator


@pytest.fixture(name="port")
def fixture_port() -> Iterator[int]:
    """A started listener on a free loopback port; the pool knows two-sum."""
    with serving(["two-sum", "add-two-numbers"]) as bound:
        yield bound


def test_a_missing_content_length_is_411(port: int) -> None:
    """Never read a body of unknown length."""
    reply = raw_exchange(port, b"POST /beat HTTP/1.0\r\n\r\n")

    assert b"411" in reply


def test_chunked_without_a_length_is_411(port: int) -> None:
    """Transfer-Encoding is not an escape from the cap."""
    request = b"POST /beat HTTP/1.0\r\nTransfer-Encoding: chunked\r\n\r\n0\r\n\r\n"

    assert b"411" in raw_exchange(port, request)


@pytest.mark.parametrize("length", ["abc", "-5", "1 2", "1_0", ""])
def test_a_bad_content_length_is_400(port: int, length: str) -> None:
    """Only plain ASCII digits count."""
    request = f"POST /beat HTTP/1.0\r\nContent-Length: {length}\r\n\r\n".encode()

    assert b"400" in raw_exchange(port, request)


def test_an_oversized_body_is_413_without_being_read(port: int) -> None:
    """The header alone decides: the declared bytes never have to arrive."""
    request = b"POST /beat HTTP/1.0\r\nContent-Length: 257\r\n\r\n"

    assert b"413" in raw_exchange(port, request)


def test_a_body_at_the_cap_is_read() -> None:
    """256 bytes exactly is within the cap (the JSON is then merely padded)."""
    padded = json.dumps({"slug": "two-sum", "tab": "description", "x": "y" * 200})
    body = padded.ljust(256)
    assert len(body) == 256
    with serving(["two-sum"]) as port:
        assert post(port, body).status == HTTPStatus.NO_CONTENT


def test_a_truncated_body_is_400(port: int) -> None:
    """Declared 50 bytes, sent 5, then the client half-closes."""
    with socket.create_connection(("127.0.0.1", port), timeout=5) as sock:
        sock.sendall(b'POST /beat HTTP/1.0\r\nContent-Length: 50\r\n\r\n{"a":')
        sock.shutdown(socket.SHUT_WR)
        assert b"400" in sock.makefile("rb").readline()


@pytest.mark.parametrize(
    "body",
    [
        b"not json",
        b"\xff\xfe",
        b"[]",
        b'"two-sum"',
        b"{}",
        json.dumps({"slug": "two-sum"}).encode(),
        json.dumps({"tab": "description"}).encode(),
        json.dumps({"slug": "Two-Sum", "tab": "description"}).encode(),
        json.dumps({"slug": "two-sum\n", "tab": "description"}).encode(),
        json.dumps({"slug": "two_sum", "tab": "description"}).encode(),
        json.dumps({"slug": "", "tab": "description"}).encode(),
        json.dumps({"slug": "a" * 101, "tab": "description"}).encode(),
        json.dumps({"slug": 5, "tab": "description"}).encode(),
        json.dumps({"slug": "two-sum", "tab": "other"}).encode(),
        json.dumps({"slug": "two-sum", "tab": 1}).encode(),
    ],
)
def test_a_bad_body_is_400_and_stores_nothing(port: int, body: bytes) -> None:
    """Every malformed shape is refused before the pool is even consulted."""
    assert post(port, body).status == HTTPStatus.BAD_REQUEST
    assert load() == {}


@pytest.mark.parametrize(
    "tab", ["description", "editorial", "solutions", "submissions"]
)
def test_every_known_tab_is_accepted(port: int, tab: str) -> None:
    """The four tabs the extension reports."""
    body = json.dumps({"slug": "two-sum", "tab": tab})

    assert post(port, body).status == HTTPStatus.NO_CONTENT


def test_a_100_character_slug_is_the_longest_allowed() -> None:
    """Boundary of the length rule, with a pool that knows the slug."""
    slug = "a" * 100
    body = json.dumps({"slug": slug, "tab": "editorial"})
    with serving([slug]) as port:
        assert post(port, body).status == HTTPStatus.NO_CONTENT


def test_a_slug_outside_the_pool_is_404(port: int) -> None:
    """Unknown problems are not measured."""
    body = json.dumps({"slug": "not-a-problem", "tab": "description"})

    assert post(port, body).status == HTTPStatus.NOT_FOUND
    assert load() == {}


def test_a_missing_pool_is_503_with_one_warning(
    port: int, caplog: pytest.LogCaptureFixture
) -> None:
    """No pool, no validation, no write; the warning is not repeated per beat."""
    _constants.POOL_CACHE_FILE.unlink()

    with caplog.at_level(logging.WARNING):
        assert post(port, GOOD).status == HTTPStatus.SERVICE_UNAVAILABLE
        assert post(port, GOOD).status == HTTPStatus.SERVICE_UNAVAILABLE

    assert sum("pool" in r.getMessage() for r in caplog.records) == 1
    assert load() == {}


def test_a_corrupt_pool_is_503_and_warned_once(
    port: int, caplog: pytest.LogCaptureFixture
) -> None:
    """An unreadable pool cannot validate a slug; the outage is one warning."""
    _constants.POOL_CACHE_FILE.write_text("{nope", encoding="utf-8")

    with caplog.at_level(logging.WARNING):
        assert post(port, GOOD).status == HTTPStatus.SERVICE_UNAVAILABLE
        assert post(port, GOOD).status == HTTPStatus.SERVICE_UNAVAILABLE

    assert sum("cannot be validated" in r.getMessage() for r in caplog.records) == 1


def test_the_pool_is_reloaded_only_when_its_mtime_changes(port: int) -> None:
    """Parse once per file version, and pick up a new pool when it lands."""
    path = _constants.POOL_CACHE_FILE
    body = json.dumps({"slug": "new-problem", "tab": "description"})
    assert post(port, body).status == HTTPStatus.NOT_FOUND

    write_pool(["two-sum", "new-problem"])
    stat = path.stat()
    os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 5_000_000_000))

    with patch("leetcode_guard._attempt_slugs.read_cache", wraps=read_cache) as reads:
        assert post(port, body).status == HTTPStatus.NO_CONTENT
        assert post(port, body).status == HTTPStatus.NO_CONTENT

    assert reads.call_count == 1
