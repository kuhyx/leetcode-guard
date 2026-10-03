"""Tests for the loopback doorbell the browser extension rings.

Real sockets on port 0: the property worth testing is what actually crosses
HTTP -- a POST rings, nothing else does, and the preflight headers a page-side
caller needs are present.
"""

from __future__ import annotations

from http import HTTPStatus
import http.client
import socket
from typing import TYPE_CHECKING

import pytest

from leetcode_guard._nudge_server import NUDGE_PATH, NudgeServer

if TYPE_CHECKING:
    from collections.abc import Iterator


@pytest.fixture
def bell() -> Iterator[tuple[NudgeServer, list[int]]]:
    rings: list[int] = []
    server = NudgeServer(lambda: rings.append(1), port=0)
    assert server.start()
    yield server, rings
    server.stop()


def _request(port: int, method: str, path: str) -> http.client.HTTPResponse:
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    conn.request(method, path, body=b"ignored")
    response = conn.getresponse()
    response.read()
    conn.close()
    return response


def test_a_post_to_the_bell_rings_it(bell: tuple[NudgeServer, list[int]]) -> None:
    server, rings = bell
    assert server.port is not None

    response = _request(server.port, "POST", NUDGE_PATH)

    assert response.status == HTTPStatus.NO_CONTENT
    assert rings == [1]
    assert response.getheader("Access-Control-Allow-Origin") == "*"


def test_any_other_path_is_a_404_and_rings_nothing(
    bell: tuple[NudgeServer, list[int]],
) -> None:
    server, rings = bell
    assert server.port is not None

    response = _request(server.port, "POST", "/unlock")

    assert response.status == HTTPStatus.NOT_FOUND
    assert rings == []


def test_the_preflight_allows_a_private_network_caller(
    bell: tuple[NudgeServer, list[int]],
) -> None:
    server, rings = bell
    assert server.port is not None

    response = _request(server.port, "OPTIONS", NUDGE_PATH)

    assert response.status == HTTPStatus.NO_CONTENT
    assert response.getheader("Access-Control-Allow-Private-Network") == "true"
    assert rings == []


def test_a_taken_port_is_survived_not_raised(caplog: pytest.LogCaptureFixture) -> None:
    with socket.socket() as squatter:
        squatter.bind(("127.0.0.1", 0))
        squatter.listen()
        port = squatter.getsockname()[1]
        server = NudgeServer(lambda: None, port=port)

        assert not server.start()

    assert server.port is None
    assert "regular poll only" in caplog.text


def test_stop_is_idempotent_and_closes_the_port() -> None:
    server = NudgeServer(lambda: None, port=0)
    server.stop()
    assert server.start()

    server.stop()
    server.stop()

    assert server.port is None
